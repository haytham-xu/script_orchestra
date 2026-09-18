"""Knowledge Vault — REST controller (blueprint prefix /knowledge-vault)."""
from flask_restx import Namespace, Resource
from flask import request

from . import repository, settings_manager, query_service, ai_client
from .entity import RawFragment, FragmentGroup, _blocks_to_storage, _blocks_to_plain, _parse_blocks
import threading
import json


def _build_index_text(frag) -> str:
    """Build rich index text for a fragment: header + note + label names + all block subtitles + bodies."""
    parts = []
    if frag.header:
        parts.append(frag.header)
    if frag.note:
        parts.append(frag.note)
    # resolve label names
    if frag.label_ids:
        all_labels = {l["id"]: l["name"] for l in repository.get_labels()}
        label_names = [all_labels[lid] for lid in frag.label_ids if lid in all_labels]
        if label_names:
            parts.append(" ".join(label_names))
    # blocks: subtitle + body
    for blk in (frag.blocks or []):
        if blk.get("subtitle"):
            parts.append(blk["subtitle"])
        if blk.get("body"):
            parts.append(blk["body"])
    return "\n".join(parts)

ns = Namespace("")

_reindex_status = {"running": False, "total": 0, "indexed": 0}


def _blocks_from_request(data: dict):
    """Extract and normalise blocks from a request payload.
    Accepts either:
      - {"blocks": [{type, body, lang?, subtitle?}, ...]}
      - {"content": "plain text"}  (legacy / batch-chat compat → single text block)
    Returns a list of block dicts.
    """
    if isinstance(data.get("blocks"), list) and data["blocks"]:
        result = []
        for b in data["blocks"]:
            block = {"type": b.get("type", "text"), "body": b.get("body", "")}
            if b.get("lang"):
                block["lang"] = b["lang"]
            if b.get("subtitle"):
                block["subtitle"] = b["subtitle"]
            result.append(block)
        return result
    content = (data.get("content") or "").strip()
    return [{"type": "text", "body": content}]


@ns.route("/fragments")
class FragmentsResource(Resource):
    def get(self):
        ungrouped_only = request.args.get("ungrouped_only") == "1"
        archived_only = request.args.get("archived") == "1"
        frags = repository.get_fragments(
            archived_only=archived_only, ungrouped_only=ungrouped_only)
        return {"fragments": [f.to_dict() for f in frags]}, 200

    def post(self):
        data = request.json or {}
        blocks = _blocks_from_request(data)
        plain = _blocks_to_plain(blocks)
        if not plain.strip():
            return {"error": "at least one block with content is required"}, 400
        frag = RawFragment.new_instance(
            blocks=blocks,
            note=(data.get("note") or "").strip(),
            raw_text=plain,
            kind=(data.get("kind") or "").strip(),
            header=(data.get("header") or "").strip(),
        )
        repository.insert_fragment(frag)
        if isinstance(data.get("label_ids"), list):
            frag.label_ids = [int(x) for x in data["label_ids"]]
            repository.set_fragment_labels(frag.id, frag.label_ids)

        def _post_ingest():
            try:
                query_service.index_fragment(frag.id, _build_index_text(frag))
            except Exception as exc:
                print(f"[knowledge_vault] embed on ingest failed: {exc}")

        threading.Thread(target=_post_ingest, daemon=True).start()
        return {"fragment": frag.to_dict()}, 201


@ns.route("/fragments/<int:fid>")
class FragmentResource(Resource):
    def get(self, fid):
        frag = repository.get_fragment(fid)
        if frag is None:
            return {"error": "fragment not found"}, 404
        repository.touch_fragment(fid)
        return {"fragment": frag.to_dict()}, 200

    def put(self, fid):
        """Edit blocks/note/header and label assignments (user-initiated)."""
        if repository.get_fragment(fid) is None:
            return {"error": "fragment not found"}, 404
        data = request.json or {}
        note = data.get("note")
        header = data.get("header")
        new_content = None
        if "blocks" in data or "content" in data:
            blocks = _blocks_from_request(data)
            new_content = _blocks_to_storage(blocks)
        repository.update_fragment(
            fid,
            content=new_content,
            note=note.strip() if isinstance(note, str) else None,
            header=header.strip() if isinstance(header, str) else None,
        )
        if isinstance(data.get("label_ids"), list):
            repository.set_fragment_labels(fid, [int(x) for x in data["label_ids"]])
        updated = repository.get_fragment(fid)
        threading.Thread(
            target=lambda: _safe_index(fid, _build_index_text(updated)),
            daemon=True).start()
        return {"fragment": updated.to_dict()}, 200

    def delete(self, fid):
        if repository.get_fragment(fid) is None:
            return {"error": "fragment not found"}, 404
        repository.delete_fragment(fid)
        return {"message": "deleted"}, 200


@ns.route("/fragments/<int:fid>/archive")
class FragmentArchiveResource(Resource):
    def put(self, fid):
        if repository.get_fragment(fid) is None:
            return {"error": "fragment not found"}, 404
        repository.archive_fragment(fid)
        return {"fragment": repository.get_fragment(fid).to_dict()}, 200

    def delete(self, fid):
        """Unarchive (restore) a fragment."""
        if repository.get_fragment(fid) is None:
            return {"error": "fragment not found"}, 404
        repository.unarchive_fragment(fid)
        return {"fragment": repository.get_fragment(fid).to_dict()}, 200


def _safe_index(fid, text):
    try:
        query_service.index_fragment(fid, text)
    except Exception as exc:
        print(f"[knowledge_vault] re-index failed: {exc}")


def _sanitize_fragments(frags) -> list:
    """Keep only well-formed {content, note, kind} rows."""
    clean = []
    if isinstance(frags, list):
        for f in frags:
            if isinstance(f, dict) and (f.get("content") or "").strip():
                clean.append({
                    "content": str(f.get("content", "")).strip(),
                    "note": str(f.get("note", "")).strip(),
                    "kind": str(f.get("kind", "")).strip(),
                })
    return clean


@ns.route("/fragments/batch-chat")
class BatchChatResource(Resource):
    def post(self):
        """Conversational batch import (stateless). Nothing is written until /fragments/batch.

        Body: {"messages":[{"role":"user"|"assistant","content":"..."}],
               "current_fragments":[{content,note,kind}]}
        Returns: {"reply":"...", "fragments":[{content,note,kind}]}
        """
        data = request.json or {}
        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            return {"error": "messages (non-empty list) is required"}, 400
        current = _sanitize_fragments(data.get("current_fragments"))

        convo = "\n".join(
            f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content','')}"
            for m in messages if isinstance(m, dict)
        )
        prompt = (
            "You help organize scattered technical knowledge into discrete "
            "fragments through conversation. Each fragment has: content (the core "
            "knowledge — a URL, command, snippet, or fact), note (a short human "
            "label), and kind (one of: url, command, script, note).\n\n"
            "Given the conversation and the current draft list, apply the user's "
            "latest request and regenerate the FULL updated draft. Do not invent "
            "knowledge that never appeared in the conversation. Also suggest a few "
            "(0–5) short lowercase labels/tags that would group this batch well "
            "(e.g. kubernetes, azure, networking).\n\n"
            "Reply with STRICT JSON only:\n"
            '{"reply":"<one short sentence to the user about what you changed>",'
            '"fragments":[{"content":"...","note":"...","kind":"..."}],'
            '"suggested_labels":["...","..."]}\n\n'
            f"CURRENT DRAFT:\n{json.dumps(current, ensure_ascii=False)}\n\n"
            f"CONVERSATION:\n{convo}"
        )
        try:
            parsed = ai_client.ask_json(prompt, max_tokens=4096) or {}
        except Exception as exc:
            return {"error": f"AI chat failed: {exc}"}, 502
        if not isinstance(parsed, dict):
            return {"error": "AI did not return a valid response"}, 502
        labels = parsed.get("suggested_labels")
        suggested = []
        if isinstance(labels, list):
            for l in labels[:8]:
                name = str(l).strip().lower()
                if name and name not in suggested:
                    suggested.append(name)
        return {
            "reply": str(parsed.get("reply", "")).strip(),
            "fragments": _sanitize_fragments(parsed.get("fragments")),
            "suggested_labels": suggested,
        }, 200


@ns.route("/fragments/batch")
class BatchCommitResource(Resource):
    def post(self):
        """Insert a confirmed list of fragments (from the batch-analyze preview)."""
        data = request.json or {}
        items = data.get("fragments")
        if not isinstance(items, list) or not items:
            return {"error": "fragments (non-empty list) is required"}, 400
        label_ids = [int(x) for x in data.get("label_ids", []) if str(x).strip()]
        created = []
        for it in items:
            content = (it.get("content") or "").strip()
            if not content:
                continue
            blocks = [{"type": "text", "body": content}]
            frag = RawFragment.new_instance(
                blocks=blocks,
                note=(it.get("note") or "").strip(),
                raw_text=content,
                kind=(it.get("kind") or "").strip(),
                header=(it.get("header") or "").strip(),
            )
            repository.insert_fragment(frag)
            if label_ids:
                repository.set_fragment_labels(frag.id, label_ids)
            created.append(frag)
        ids_texts = [(f.id, f"{f.raw_text}\n{f.note}") for f in created]

        def _index_all():
            for fid, text in ids_texts:
                _safe_index(fid, text)
        threading.Thread(target=_index_all, daemon=True).start()
        return {"created": [f.to_dict() for f in created], "count": len(created)}, 201


@ns.route("/labels")
class LabelsResource(Resource):
    def get(self):
        return {"labels": repository.get_labels()}, 200

    def post(self):
        data = request.json or {}
        name = (data.get("name") or "").strip()
        if not name:
            return {"error": "name is required"}, 400
        color = (data.get("color") or "#8e8e93").strip()
        result = repository.create_label(name, color)
        if result.pop("existing", False):
            return {"error": f"Label '{result['name']}' already exists (case-insensitive match)", "label": result}, 409
        return {"label": result}, 201


@ns.route("/labels/rebuild")
class LabelsRebuildResource(Resource):
    def post(self):
        """Ask AI to suggest missing label assignments across all fragments."""
        labels = repository.get_labels()
        if not labels:
            return {"error": "No labels defined yet"}, 400
        fragments = repository.get_fragments()
        if not fragments:
            return {"suggestions": []}, 200

        label_names = [l["name"] for l in labels]
        label_by_name = {l["name"].lower(): l["id"] for l in labels}

        frag_lines = []
        for f in fragments[:200]:
            current = [l["name"] for l in labels if l["id"] in (f.label_ids or [])]
            frag_lines.append(
                f'  {{"id":{f.id},"content":{json.dumps(f.raw_text[:120], ensure_ascii=False)},'
                f'"note":{json.dumps((f.note or "")[:60], ensure_ascii=False)},'
                f'"current_labels":{json.dumps(current)}}}'
            )

        prompt = (
            "You are a knowledge organizer. Given a list of fragments and an existing label vocabulary, "
            "suggest which additional labels from the vocabulary should be applied to each fragment. "
            "Only use labels from the provided vocabulary — do not invent new ones. "
            "Only return fragments that need at least one new label added. "
            "Skip fragments whose current labels are already complete.\n\n"
            f"Label vocabulary: {json.dumps(label_names)}\n\n"
            "Fragments:\n[\n" + ",\n".join(frag_lines) + "\n]\n\n"
            "Reply with STRICT JSON only — an array of objects, each with fragment id and labels to ADD:\n"
            '[{"id": <int>, "add_labels": ["<label_name>", ...]}, ...]'
        )

        try:
            result = ai_client.ask_json(prompt, max_tokens=4096, timeout=180)
        except Exception as exc:
            return {"error": f"AI call failed: {exc}"}, 502

        if not isinstance(result, list):
            if isinstance(result, dict) and "assignments" in result:
                result = result["assignments"]
            else:
                return {"error": "AI returned unexpected format"}, 502

        frag_map = {f.id: f for f in fragments}
        suggestions = []
        for item in result:
            if not isinstance(item, dict):
                continue
            fid = item.get("id")
            add_names = item.get("add_labels") or []
            if not fid or not isinstance(add_names, list):
                continue
            valid_names = [n for n in add_names if n.lower() in label_by_name]
            if not valid_names:
                continue
            frag = frag_map.get(fid)
            if not frag:
                continue
            suggestions.append({
                "id": fid,
                "content": frag.raw_text[:120],
                "note": frag.note or "",
                "add_labels": valid_names,
            })

        return {"suggestions": suggestions}, 200


@ns.route("/labels/rebuild/apply")
class LabelsRebuildApplyResource(Resource):
    def post(self):
        """Apply a user-confirmed subset of label suggestions."""
        data = request.get_json(force=True) or {}
        items = data.get("assignments") or []
        if not isinstance(items, list):
            return {"error": "assignments must be a list"}, 400

        labels = repository.get_labels()
        label_by_name = {l["name"].lower(): l["id"] for l in labels}
        fragments = repository.get_fragments()
        frag_map = {f.id: f for f in fragments}

        updated = 0
        for item in items:
            fid = item.get("id")
            add_names = item.get("add_labels") or []
            if not fid or not add_names:
                continue
            frag = frag_map.get(int(fid))
            if not frag:
                continue
            new_ids = [label_by_name[n.lower()] for n in add_names if n.lower() in label_by_name]
            if not new_ids:
                continue
            merged = list(set((frag.label_ids or []) + new_ids))
            repository.set_fragment_labels(frag.id, merged)
            updated += 1

        return {"updated": updated}, 200


@ns.route("/labels/<int:label_id>")
class LabelResource(Resource):
    def put(self, label_id):
        data = request.json or {}
        name = (data.get("name") or "").strip()
        color = data.get("color")
        if not name:
            return {"error": "name is required"}, 400
        result = repository.update_label(label_id, name=name, color=color)
        if not result:
            return {"error": "Label not found"}, 404
        return {"label": result}, 200

    def delete(self, label_id):
        repository.delete_label(label_id)
        return {"message": "deleted"}, 200


@ns.route("/query")
class QueryResource(Resource):
    def get(self):
        q = request.args.get("q", "")
        try:
            top_k = int(request.args.get("top_k", 10))
        except ValueError:
            top_k = 10
        return {"results": query_service.search(q, top_k)}, 200


@ns.route("/query/reindex")
class ReindexResource(Resource):
    def post(self):
        """Re-index all non-archived fragments with the full rich index text."""
        frags = repository.get_fragments(include_archived=False)
        _reindex_status.update({"running": True, "total": len(frags), "indexed": 0})

        def _do_reindex():
            for frag in frags:
                _safe_index(frag.id, _build_index_text(frag))
                _reindex_status["indexed"] += 1
            _reindex_status["running"] = False

        threading.Thread(target=_do_reindex, daemon=True).start()
        return {"message": f"Re-indexing {len(frags)} fragments in background"}, 202


@ns.route("/query/reindex/status")
class ReindexStatusResource(Resource):
    def get(self):
        return dict(_reindex_status), 200


@ns.route("/duplicates")
class DuplicatesResource(Resource):
    def get(self):
        """Near-duplicate fragment pairs from stored vectors. Zero token cost."""
        def _f(name):
            v = request.args.get(name)
            try:
                return float(v) if v is not None else None
            except ValueError:
                return None
        return query_service.find_duplicate_pairs(high=_f("high"), fuzzy_low=_f("fuzzy_low")), 200


@ns.route("/duplicates/resolve")
class DuplicatesResolveResource(Resource):
    def post(self):
        """Resolve one duplicate pair: keep one fragment, archive the other."""
        data = request.json or {}
        try:
            keep_id = int(data.get("keep_id"))
            drop_id = int(data.get("drop_id"))
        except (TypeError, ValueError):
            return {"error": "keep_id and drop_id must be integers"}, 400
        if keep_id == drop_id:
            return {"error": "keep_id and drop_id must differ"}, 400
        if repository.get_fragment(drop_id) is None:
            return {"error": "drop fragment not found"}, 404
        repository.archive_fragment(drop_id)
        return query_service.find_duplicate_pairs(), 200


@ns.route("/settings")
class SettingsResource(Resource):
    def get(self):
        return {"settings": settings_manager.load_settings()}, 200

    def put(self):
        data = request.json or {}
        if not isinstance(data, dict):
            return {"error": "Body must be a JSON object"}, 400
        try:
            updated = settings_manager.validate_and_normalize(
                data, settings_manager.load_settings())
            settings_manager.save_settings(updated)
            return {"settings": updated, "message": "Settings updated"}, 200
        except ValueError as e:
            return {"error": str(e)}, 400


# ---- fragment groups --------------------------------------------------

def _aggregate_labels(groups, all_frags):
    """Build a map of group_id -> aggregated label_ids from all descendants."""
    # Build fragment membership map: group_id -> [fragment]
    frag_by_group = {}
    for f in all_frags:
        if f.group_id is not None:
            frag_by_group.setdefault(f.group_id, []).append(f)

    # Build children map: parent_id -> [group]
    children_map = {}
    for g in groups:
        if g.parent_id is not None:
            children_map.setdefault(g.parent_id, []).append(g)

    def _collect_label_ids(gid):
        ids = set()
        for f in frag_by_group.get(gid, []):
            ids.update(f.label_ids or [])
        for child in children_map.get(gid, []):
            ids.update(_collect_label_ids(child.id))
        return ids

    return {g.id: sorted(_collect_label_ids(g.id)) for g in groups}


@ns.route("/fragment-groups")
class FragmentGroupsResource(Resource):
    def get(self):
        groups = repository.get_groups()
        all_frags = repository.get_fragments()
        agg = _aggregate_labels(groups, all_frags)
        result = []
        for g in groups:
            d = g.to_dict()
            d["label_ids"] = agg.get(g.id, [])
            result.append(d)
        return {"groups": result}, 200

    def post(self):
        data = request.json or {}
        name = (data.get("name") or "").strip()
        if not name:
            return {"error": "name is required"}, 400
        note = (data.get("note") or "").strip()
        parent_id = data.get("parent_id")
        if parent_id is not None:
            try:
                parent_id = int(parent_id)
            except (TypeError, ValueError):
                return {"error": "parent_id must be an integer"}, 400
            if repository.get_group(parent_id) is None:
                return {"error": "parent group not found"}, 404
        g = FragmentGroup.new_instance(name=name, note=note, parent_id=parent_id)
        repository.insert_group(g)
        d = g.to_dict()
        d["label_ids"] = []
        return {"group": d}, 201


@ns.route("/fragment-groups/<int:gid>")
class FragmentGroupResource(Resource):
    def get(self, gid):
        g = repository.get_group(gid)
        if g is None:
            return {"error": "group not found"}, 404
        all_frags = repository.get_fragments()
        all_groups = repository.get_groups()
        agg = _aggregate_labels(all_groups, all_frags)
        d = g.to_dict()
        d["label_ids"] = agg.get(gid, [])
        return {"group": d}, 200

    def put(self, gid):
        if repository.get_group(gid) is None:
            return {"error": "group not found"}, 404
        data = request.json or {}
        name = data.get("name")
        note = data.get("note")
        _missing = object()
        raw_parent = data.get("parent_id", _missing)
        if raw_parent is _missing:
            # parent_id not in payload — leave it unchanged
            new_parent = repository._UNSET
        elif raw_parent is None:
            new_parent = None
        else:
            try:
                new_parent = int(raw_parent)
            except (TypeError, ValueError):
                return {"error": "parent_id must be an integer or null"}, 400
            if new_parent == gid:
                return {"error": "group cannot be its own parent"}, 400
            if repository.get_group(new_parent) is None:
                return {"error": "parent group not found"}, 404
        repository.update_group(
            gid,
            name=name.strip() if isinstance(name, str) else None,
            note=note.strip() if isinstance(note, str) else None,
            parent_id=new_parent,
        )
        g = repository.get_group(gid)
        all_frags = repository.get_fragments()
        all_groups = repository.get_groups()
        agg = _aggregate_labels(all_groups, all_frags)
        d = g.to_dict()
        d["label_ids"] = agg.get(gid, [])
        return {"group": d}, 200

    def delete(self, gid):
        if repository.get_group(gid) is None:
            return {"error": "group not found"}, 404
        members = repository.get_group_members(gid)
        if members:
            return {"error": f"Group has {len(members)} member(s). Move or remove them first."}, 409
        # Also check for sub-groups
        all_groups = repository.get_groups()
        children = [g for g in all_groups if g.parent_id == gid]
        if children:
            return {"error": f"Group has {len(children)} sub-group(s). Delete them first."}, 409
        repository.delete_group(gid)
        return {"message": "deleted"}, 200

@ns.route("/fragment-groups/<int:gid>/members")
class FragmentGroupMembersResource(Resource):
    def get(self, gid):
        if repository.get_group(gid) is None:
            return {"error": "group not found"}, 404
        return {"fragment_ids": repository.get_group_members(gid)}, 200

    def put(self, gid):
        """Set the complete member list for this group."""
        if repository.get_group(gid) is None:
            return {"error": "group not found"}, 404
        data = request.json or {}
        fragment_ids = data.get("fragment_ids")
        if not isinstance(fragment_ids, list):
            return {"error": "fragment_ids must be a list"}, 400
        try:
            fids = [int(x) for x in fragment_ids]
        except (TypeError, ValueError):
            return {"error": "fragment_ids must be a list of integers"}, 400
        repository.set_group_members(gid, fids)
        return {"fragment_ids": repository.get_group_members(gid)}, 200
