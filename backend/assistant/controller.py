"""
Assistant Controller

REST endpoints for the assistant tool. Non-streaming for Step 1.1 — a
streaming path will be added later on top of the same DB and service.
"""
import json

from flask import Response, request, send_file, stream_with_context
from flask_restx import Namespace, Resource, fields

from . import attachments as att_service
from . import db, service
from .config import (
    DEFAULT_MODEL_ALIAS,
    DEFAULT_SYSTEM_PROMPT,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_MESSAGE,
    MODEL_ALIAS,
)
from .voice import asr as voice_asr
from .voice import tts as voice_tts
from .voice.config import (
    MAX_AUDIO_BYTES,
    TTS_ENGINES,
    WHISPER_MODELS,
    load_config as load_voice_config,
    save_config as save_voice_config,
)

ns = Namespace("assistant", description="AI chat assistant operations")


# ── Models ────────────────────────────────────────────────

conversation_create_model = ns.model('AssistantConversationCreate', {
    'title': fields.String(required=False, description='Conversation title'),
    'system_prompt': fields.String(required=False,
                                   description='Optional system prompt override'),
    'model_alias': fields.String(required=False,
                                 description='auto | haiku | sonnet | opus'),
})

conversation_update_model = ns.model('AssistantConversationUpdate', {
    'title': fields.String(required=False),
    'system_prompt': fields.String(required=False),
    'model_alias': fields.String(required=False,
                                 description='auto | haiku | sonnet | opus'),
    'kb_enabled': fields.Boolean(required=False,
                                 description='Enable knowledge-base retrieval for this conversation'),
    'pinned': fields.Boolean(required=False),
    'archived': fields.Boolean(required=False),
})

chat_input_model = ns.model('AssistantChatInput', {
    'content': fields.String(required=True, description='User message text'),
    'attachment_ids': fields.List(
        fields.String,
        required=False,
        description='IDs previously returned by /attachments/upload',
    ),
})

conversation_summary_model = ns.model('AssistantConversationSummary', {
    'id': fields.String,
    'title': fields.String,
    'model_alias': fields.String,
    'kb_enabled': fields.Boolean,
    'pinned': fields.Boolean,
    'archived': fields.Boolean,
    'created_at': fields.String,
    'updated_at': fields.String,
})

conversation_full_model = ns.model('AssistantConversationFull', {
    'id': fields.String,
    'title': fields.String,
    'system_prompt': fields.String,
    'model_alias': fields.String,
    'kb_enabled': fields.Boolean,
    'pinned': fields.Boolean,
    'archived': fields.Boolean,
    'created_at': fields.String,
    'updated_at': fields.String,
})

message_model = ns.model('AssistantMessage', {
    'id': fields.Integer,
    'conversation_id': fields.String,
    'role': fields.String,
    'content': fields.String,
    'model': fields.String,
    'complexity': fields.String,
    'input_tokens': fields.Integer,
    'output_tokens': fields.Integer,
    'created_at': fields.String,
})

chat_reply_model = ns.model('AssistantChatReply', {
    'message': fields.Nested(message_model),
    'model': fields.String,
    'complexity': fields.String,
    'input_tokens': fields.Integer,
    'output_tokens': fields.Integer,
})


# ── Helpers ───────────────────────────────────────────────

def _validate_alias(alias: str) -> str:
    alias = (alias or DEFAULT_MODEL_ALIAS).lower()
    if alias not in MODEL_ALIAS:
        ns.abort(400, f"model_alias must be one of {list(MODEL_ALIAS.keys())}")
    return alias


# ── Conversations ─────────────────────────────────────────

@ns.route('/conversations')
class ConversationCollection(Resource):
    @ns.marshal_list_with(conversation_summary_model)
    def get(self):
        """List all conversations, most recently updated first."""
        return db.list_conversations()

    @ns.expect(conversation_create_model)
    @ns.marshal_with(conversation_full_model)
    def post(self):
        """Create a new conversation."""
        data = request.get_json(silent=True) or {}
        title = data.get('title') or 'New chat'
        system_prompt = data.get('system_prompt') or DEFAULT_SYSTEM_PROMPT
        alias = _validate_alias(data.get('model_alias', DEFAULT_MODEL_ALIAS))
        conv = db.create_conversation(
            title=title,
            system_prompt=system_prompt,
            model_alias=alias,
        )
        return conv, 201


@ns.route('/conversations/<string:conv_id>')
class ConversationItem(Resource):
    @ns.marshal_with(conversation_full_model)
    def get(self, conv_id):
        conv = db.get_conversation(conv_id)
        if conv is None:
            ns.abort(404, f"Conversation {conv_id} not found")
        return conv

    @ns.expect(conversation_update_model)
    @ns.marshal_with(conversation_full_model)
    def patch(self, conv_id):
        data = request.get_json(silent=True) or {}
        if 'model_alias' in data:
            _validate_alias(data['model_alias'])
        conv = db.update_conversation(
            conv_id,
            title=data.get('title'),
            system_prompt=data.get('system_prompt'),
            model_alias=data.get('model_alias'),
            kb_enabled=data.get('kb_enabled'),
            pinned=data.get('pinned'),
            archived=data.get('archived'),
        )
        if conv is None:
            ns.abort(404, f"Conversation {conv_id} not found")
        return conv

    def delete(self, conv_id):
        ok = db.delete_conversation(conv_id)
        if not ok:
            ns.abort(404, f"Conversation {conv_id} not found")
        return {"message": "deleted"}, 200


# ── Messages ──────────────────────────────────────────────

@ns.route('/conversations/<string:conv_id>/messages')
class MessageCollection(Resource):
    def get(self, conv_id):
        """Return all messages in a conversation, with any attachments."""
        conv = db.get_conversation(conv_id)
        if conv is None:
            ns.abort(404, f"Conversation {conv_id} not found")
        msgs = db.list_messages(conv_id)
        # Fold attachments into each user message so the UI can render
        # inline previews without an extra round-trip.
        for m in msgs:
            atts = db.list_attachments_for_message(m['id'])
            m['attachments'] = [
                {
                    'id': a['id'],
                    'kind': a['kind'],
                    'mime_type': a['mime_type'],
                    'filename': a['filename'],
                    'byte_size': a['byte_size'],
                }
                for a in atts
            ]
        return msgs


message_edit_model = ns.model('AssistantMessageEdit', {
    'content': fields.String(required=True,
                             description='New content for the user message'),
})


@ns.route('/conversations/<string:conv_id>/messages/<int:message_id>/edit')
class MessageEditResource(Resource):
    @ns.expect(message_edit_model)
    def post(self, conv_id, message_id):
        """
        Rewrite a user message and drop every subsequent message so the
        model can regenerate from the edited turn. Only user messages can
        be edited — assistant replies are historical artifacts.
        """
        data = request.get_json(silent=True) or {}
        content = data.get('content', '')
        try:
            row = db.edit_user_message_and_truncate(conv_id, message_id, content)
        except ValueError as exc:
            ns.abort(400, str(exc))
        if row is None:
            ns.abort(404, "user message not found in this conversation")
        return row


@ns.route('/conversations/<string:conv_id>/regenerate/stream')
@ns.doc(description="SSE regenerate — takes the current tail as-is (no new "
                    "user message) and streams a fresh assistant reply. If "
                    "the last row is already an assistant reply, it gets "
                    "replaced.")
class RegenerateStreamResource(Resource):
    def post(self, conv_id):
        def event_generator():
            for evt in service.stream_regenerate(conv_id):
                yield f"event: {evt['type']}\ndata: {json.dumps(evt)}\n\n"

        resp = Response(
            stream_with_context(event_generator()),
            mimetype='text/event-stream',
        )
        resp.headers['Cache-Control'] = 'no-cache'
        resp.headers['X-Accel-Buffering'] = 'no'
        return resp


@ns.route('/conversations/<string:conv_id>/chat')
class ChatResource(Resource):
    @ns.expect(chat_input_model)
    @ns.marshal_with(chat_reply_model)
    def post(self, conv_id):
        """Send a user message and get the assistant's reply."""
        data = request.get_json(silent=True) or {}
        content = data.get('content', '')
        attachment_ids = data.get('attachment_ids') or []
        if not content.strip() and not attachment_ids:
            ns.abort(400, "content or attachment_ids required")
        if len(attachment_ids) > MAX_ATTACHMENTS_PER_MESSAGE:
            ns.abort(400,
                     f"too many attachments (max {MAX_ATTACHMENTS_PER_MESSAGE})")

        try:
            result = service.send_message(conv_id, content, attachment_ids)
        except LookupError as exc:
            ns.abort(404, str(exc))
        except PermissionError as exc:
            ns.abort(403, str(exc))
        except ValueError as exc:
            ns.abort(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            ns.abort(500, f"Assistant error: {exc}")
        return result


@ns.route('/conversations/<string:conv_id>/chat/stream')
@ns.doc(description="Server-Sent Events chat stream. "
                    "Events: start, delta, done, error.")
class ChatStreamResource(Resource):
    def post(self, conv_id):
        """Streaming variant of /chat. Response is `text/event-stream`."""
        data = request.get_json(silent=True) or {}
        content = data.get('content', '')
        attachment_ids = data.get('attachment_ids') or []
        if not content.strip() and not attachment_ids:
            ns.abort(400, "content or attachment_ids required")
        if len(attachment_ids) > MAX_ATTACHMENTS_PER_MESSAGE:
            ns.abort(400,
                     f"too many attachments (max {MAX_ATTACHMENTS_PER_MESSAGE})")

        def event_generator():
            for evt in service.stream_message(conv_id, content, attachment_ids):
                yield f"event: {evt['type']}\ndata: {json.dumps(evt)}\n\n"

        resp = Response(
            stream_with_context(event_generator()),
            mimetype='text/event-stream',
        )
        # Disable proxy buffering so tokens surface immediately.
        resp.headers['Cache-Control'] = 'no-cache'
        resp.headers['X-Accel-Buffering'] = 'no'
        return resp


# ── Attachments ───────────────────────────────────────────

attachment_model = ns.model('AssistantAttachment', {
    'id': fields.String,
    'conversation_id': fields.String,
    'message_id': fields.Integer,
    'kind': fields.String,
    'mime_type': fields.String,
    'filename': fields.String,
    'byte_size': fields.Integer,
    'sha256': fields.String,
    'created_at': fields.String,
})


@ns.route('/conversations/<string:conv_id>/attachments')
class AttachmentUploadResource(Resource):
    @ns.marshal_with(attachment_model)
    def post(self, conv_id):
        """Upload a file for later use in a chat message. Multipart form."""
        if 'file' not in request.files:
            ns.abort(400, "field `file` is required (multipart/form-data)")
        file = request.files['file']
        raw = file.read()
        if not raw:
            ns.abort(400, "uploaded file is empty")
        if len(raw) > MAX_ATTACHMENT_BYTES:
            ns.abort(413,
                     f"file too large (max {MAX_ATTACHMENT_BYTES} bytes)")
        mime = file.mimetype or 'application/octet-stream'
        try:
            row = att_service.store_attachment(
                conv_id, raw, filename=file.filename or 'upload',
                mime_type=mime,
            )
        except LookupError as exc:
            ns.abort(404, str(exc))
        except ValueError as exc:
            ns.abort(400, str(exc))
        return row, 201

    @ns.marshal_list_with(attachment_model)
    def get(self, conv_id):
        """List every attachment ever uploaded to this conversation."""
        if db.get_conversation(conv_id) is None:
            ns.abort(404, f"Conversation {conv_id} not found")
        return db.list_attachments_for_conversation(conv_id)


@ns.route('/attachments/<string:attachment_id>/raw')
class AttachmentRawResource(Resource):
    def get(self, attachment_id):
        """Serve the raw bytes of an attachment (for inline preview)."""
        row = db.get_attachment(attachment_id)
        if row is None:
            ns.abort(404, f"Attachment {attachment_id} not found")
        try:
            data = att_service.read_attachment_bytes(row)
        except FileNotFoundError:
            ns.abort(410, "attachment bytes are gone")
        resp = Response(data, mimetype=row['mime_type'])
        resp.headers['Cache-Control'] = 'private, max-age=3600'
        resp.headers['Content-Disposition'] = (
            f'inline; filename="{row["filename"]}"'
        )
        return resp


@ns.route('/models')
class ModelsResource(Resource):
    def get(self):
        """Return the list of model aliases the UI can pick from."""
        return {
            "default": DEFAULT_MODEL_ALIAS,
            "aliases": list(MODEL_ALIAS.keys()),
        }


# ── Usage stats ───────────────────────────────────────────

@ns.route('/stats/usage')
class UsageStatsResource(Resource):
    def get(self):
        """Aggregate token usage across all conversations."""
        return db.usage_totals()


# ── Search ────────────────────────────────────────────────

@ns.route('/search')
class SearchResource(Resource):
    def get(self):
        """
        Full-text search across every message. Query param `q`; optional
        `limit` (default 30, max 100).
        """
        q = request.args.get('q', '').strip()
        limit = request.args.get('limit', default=30, type=int)
        limit = max(1, min(limit, 100))
        if not q:
            return {"query": q, "hits": []}
        hits = db.search_messages(q, limit=limit)
        return {"query": q, "hits": hits}


# ── Knowledge base ────────────────────────────────────────

from .knowledge import service as kb_service  # noqa: E402
from .wake import service as wake_service  # noqa: E402

kb_source_model = ns.model('AssistantKbSource', {
    'id': fields.String,
    'name': fields.String,
    'path': fields.String,
    'enabled': fields.Integer,
    'last_scanned_at': fields.String,
    'file_count': fields.Integer,
    'chunk_count': fields.Integer,
    'created_at': fields.String,
})

kb_source_create_model = ns.model('AssistantKbSourceCreate', {
    'name': fields.String(required=False),
    'path': fields.String(required=True,
                          description='Absolute directory path to index'),
})

kb_source_update_model = ns.model('AssistantKbSourceUpdate', {
    'name': fields.String(required=False),
    'enabled': fields.Boolean(required=False),
})


@ns.route('/kb/sources')
class KbSourcesCollection(Resource):
    @ns.marshal_list_with(kb_source_model)
    def get(self):
        """List all registered knowledge sources."""
        return kb_service.list_sources()

    @ns.expect(kb_source_create_model)
    @ns.marshal_with(kb_source_model)
    def post(self):
        """Register a new folder as a knowledge source."""
        data = request.get_json(silent=True) or {}
        path = (data.get('path') or '').strip()
        if not path:
            ns.abort(400, "path is required")
        try:
            src = kb_service.create_source(
                name=(data.get('name') or '').strip(),
                path=path,
            )
        except ValueError as exc:
            ns.abort(400, str(exc))
        return src, 201


@ns.route('/kb/sources/<string:source_id>')
class KbSourceItem(Resource):
    @ns.marshal_with(kb_source_model)
    def get(self, source_id):
        src = kb_service.get_source(source_id)
        if src is None:
            ns.abort(404, "source not found")
        return src

    @ns.expect(kb_source_update_model)
    @ns.marshal_with(kb_source_model)
    def patch(self, source_id):
        data = request.get_json(silent=True) or {}
        src = kb_service.update_source(source_id, **data)
        if src is None:
            ns.abort(404, "source not found")
        return src

    def delete(self, source_id):
        ok = kb_service.delete_source(source_id)
        if not ok:
            ns.abort(404, "source not found")
        return {"message": "deleted"}, 200


@ns.route('/kb/sources/<string:source_id>/refresh')
class KbSourceRefresh(Resource):
    def post(self, source_id):
        """Rescan the folder + (re)embed changed files."""
        try:
            summary = kb_service.refresh_source(source_id)
        except LookupError as exc:
            ns.abort(404, str(exc))
        except FileNotFoundError as exc:
            ns.abort(410, str(exc))
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            ns.abort(500, f"refresh failed: {exc}")
        return summary


@ns.route('/kb/query')
class KbQueryResource(Resource):
    def get(self):
        """Preview retrieval for a given query without going through Claude."""
        q = request.args.get('q', '').strip()
        top_k = request.args.get('top_k', default=5, type=int)
        if not q:
            return {"query": q, "hits": []}
        return {"query": q, "hits": kb_service.retrieve(q, top_k=top_k)}


# ── Wake word ─────────────────────────────────────────────

wake_start_model = ns.model('AssistantWakeStart', {
    'keyword': fields.String(required=False),
    'threshold': fields.Float(required=False),
})


@ns.route('/wake/status')
class WakeStatusResource(Resource):
    def get(self):
        return wake_service.get_service().get_status()


@ns.route('/wake/start')
class WakeStartResource(Resource):
    @ns.expect(wake_start_model)
    def post(self):
        data = request.get_json(silent=True) or {}
        try:
            return wake_service.get_service().start(
                keyword=data.get('keyword'),
                threshold=data.get('threshold'),
            )
        except ValueError as exc:
            ns.abort(400, str(exc))
        except RuntimeError as exc:
            ns.abort(409, str(exc))


@ns.route('/wake/stop')
class WakeStopResource(Resource):
    def post(self):
        return wake_service.get_service().stop()


# ── Fork ──────────────────────────────────────────────────

fork_input_model = ns.model('AssistantForkInput', {
    'message_id': fields.Integer(required=True,
                                 description='Anchor message ID'),
    'mode': fields.String(
        required=False,
        description='"up-to" copies through this message; '
                    '"before" copies up to but not including it.',
    ),
    'title': fields.String(required=False,
                           description='Optional title override.'),
})


@ns.route('/conversations/<string:conv_id>/summarize')
class ConversationSummarizeResource(Resource):
    def post(self, conv_id):
        """Manually trigger the rolling summarizer for this conversation."""
        from . import summarizer
        text = summarizer.maybe_summarize(conv_id)
        conv = db.get_conversation(conv_id)
        return {
            "summary_updated": text is not None,
            "summary": conv.get("summary") if conv else None,
            "summary_up_to_id": conv.get("summary_up_to_id") if conv else None,
        }


@ns.route('/conversations/<string:conv_id>/fork')
class ConversationForkResource(Resource):
    @ns.expect(fork_input_model)
    @ns.marshal_with(conversation_full_model)
    def post(self, conv_id):
        """Duplicate a conversation up to (or before) a given message."""
        data = request.get_json(silent=True) or {}
        try:
            message_id = int(data.get('message_id'))
        except (TypeError, ValueError):
            ns.abort(400, "message_id is required and must be an integer")
        mode = (data.get('mode') or 'up-to').lower()
        if mode not in ('up-to', 'before'):
            ns.abort(400, "mode must be 'up-to' or 'before'")
        include_target = mode == 'up-to'
        title = data.get('title')

        new_conv = db.fork_conversation(
            source_conv_id=conv_id,
            up_to_message_id=message_id,
            include_target=include_target,
            new_title=title,
        )
        if new_conv is None:
            ns.abort(404, "conversation or message not found")
        return new_conv, 201


@ns.route('/conversations/<string:conv_id>/stats/usage')
class ConversationUsageStatsResource(Resource):
    def get(self, conv_id):
        """Token usage for one conversation."""
        if db.get_conversation(conv_id) is None:
            ns.abort(404, f"Conversation {conv_id} not found")
        return db.usage_for_conversation(conv_id)


# ── Export ────────────────────────────────────────────────

def _md_escape(text: str) -> str:
    # Minimal escape: only leading > and # that would collide with block
    # syntax. Everything else in user/assistant messages stays as-is so
    # code blocks and markdown formatting survive the round trip.
    return text


@ns.route('/conversations/<string:conv_id>/export')
class ConversationExportResource(Resource):
    def get(self, conv_id):
        """Return the whole conversation as a Markdown transcript."""
        conv = db.get_conversation(conv_id)
        if conv is None:
            ns.abort(404, f"Conversation {conv_id} not found")

        msgs = db.list_messages(conv_id)
        lines = [
            f"# {conv['title']}",
            "",
            f"- Created: {conv['created_at']}",
            f"- Updated: {conv['updated_at']}",
            f"- Model routing: `{conv['model_alias']}`",
        ]
        if conv.get('system_prompt'):
            lines += [
                "",
                "## System prompt",
                "",
                "```",
                conv['system_prompt'],
                "```",
            ]

        lines += ["", "---", ""]
        for m in msgs:
            role_label = 'You' if m['role'] == 'user' else 'Assistant'
            meta_bits = [f"_{m['created_at']}_"]
            if m['role'] == 'assistant':
                if m.get('model'):
                    meta_bits.append(f"model: `{m['model']}`")
                if m.get('complexity'):
                    meta_bits.append(f"complexity: `{m['complexity']}`")
                if m.get('output_tokens') is not None:
                    meta_bits.append(
                        f"tokens: {m.get('input_tokens', 0)}→{m['output_tokens']}"
                    )
            lines.append(f"## {role_label}")
            lines.append("")
            lines.append(" · ".join(meta_bits))
            lines.append("")

            atts = db.list_attachments_for_message(m['id'])
            for a in atts:
                lines.append(
                    f"> _attachment_: `{a['filename']}` "
                    f"({a['mime_type']}, {a['byte_size']} B)"
                )
            if atts:
                lines.append("")

            lines.append(_md_escape(m['content']))
            lines.append("")

        markdown = "\n".join(lines).rstrip() + "\n"

        safe_title = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in conv['title']
        ).strip("_") or "conversation"
        filename = f"{safe_title}.md"

        resp = Response(markdown, mimetype='text/markdown; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename="{filename}"'
        )
        return resp


# ── Voice ─────────────────────────────────────────────────

@ns.route('/voice/config')
class VoiceConfigResource(Resource):
    def get(self):
        """Return current voice settings + catalogs the UI renders."""
        cfg = load_voice_config()
        return {
            **cfg,
            "whisper_models": WHISPER_MODELS,
            "tts_engines": TTS_ENGINES,
        }

    def put(self):
        """Update the persisted voice settings."""
        data = request.get_json(silent=True) or {}
        try:
            cfg = save_voice_config(data)
        except ValueError as exc:
            ns.abort(400, str(exc))
        return cfg


@ns.route('/voice/transcribe')
class VoiceTranscribeResource(Resource):
    def post(self):
        """
        Transcribe an uploaded audio blob.

        Accepts either:
          - multipart/form-data with a file field named `audio`
          - application/octet-stream (raw bytes; filename from
            `X-Filename` header if present)

        Optional query params:
          - language: BCP-47 tag or "auto"
        """
        language = request.args.get("language") or request.form.get("language")

        audio_bytes = b""
        filename_hint = "audio.webm"
        if 'audio' in request.files:
            file = request.files['audio']
            audio_bytes = file.read()
            filename_hint = file.filename or filename_hint
        else:
            audio_bytes = request.get_data(cache=False)
            filename_hint = request.headers.get('X-Filename', filename_hint)

        if not audio_bytes:
            ns.abort(400, "audio payload is empty")
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            ns.abort(413, f"audio too large (max {MAX_AUDIO_BYTES} bytes)")

        try:
            result = voice_asr.transcribe(
                audio_bytes, filename_hint=filename_hint, language=language
            )
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            ns.abort(500, f"transcription failed: {exc}")
        return result


@ns.route('/voice/tts')
class VoiceTTSResource(Resource):
    def post(self):
        """Synthesize speech from text using the configured engine."""
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        engine = data.get("engine")  # optional override
        if not text:
            ns.abort(400, "text is required")

        try:
            audio_bytes, mime = voice_tts.synthesize(text, engine=engine)
        except voice_tts.TTSError as exc:
            ns.abort(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            ns.abort(500, f"tts failed: {exc}")

        resp = Response(audio_bytes, mimetype=mime)
        resp.headers['Cache-Control'] = 'no-cache'
        return resp
