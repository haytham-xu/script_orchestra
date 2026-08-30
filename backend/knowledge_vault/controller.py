"""Knowledge Vault — REST controller (blueprint prefix /knowledge-vault).

Stage 1: raw fragment ingest + listing. Query / build / lifecycle endpoints
are added in later stages.
"""
from flask_restx import Namespace, Resource
from flask import request

from . import repository, settings_manager, query_service
from . import builder, lifecycle, ai_client, backup, link_checker, dedup
from .entity import RawFragment
import threading
import json

ns = Namespace("")


@ns.route("/fragments")
class FragmentsResource(Resource):
    def get(self):
        include_archived = request.args.get("archived") == "1"
        frags = repository.get_fragments(include_archived=include_archived)
        stale_days = settings_manager.load_settings().get("stale_days", 90)
        for f in frags:
            f.freshness = lifecycle.freshness_for(f.kind, f.last_accessed, f.created_at, stale_days)
        return {"fragments": [f.to_dict() for f in frags]}, 200

    def post(self):
        data = request.json or {}
        content = (data.get("content") or "").strip()
        raw_text = (data.get("raw_text") or "").strip()
        # Accept either an explicit content field or a raw blob to store as-is.
        if not content and not raw_text:
            return {"error": "content or raw_text is required"}, 400
        frag = RawFragment.new_instance(
            content=content or raw_text,
            note=(data.get("note") or "").strip(),
            raw_text=raw_text or content,
            kind=(data.get("kind") or "").strip(),
        )
        repository.insert_fragment(frag)
        if isinstance(data.get("label_ids"), list):
            frag.label_ids = [int(x) for x in data["label_ids"]]
            repository.set_fragment_labels(frag.id, frag.label_ids)
        # Snapshot after every new fragment — the raw layer must never be lost.
        backup.snapshot()
        # Embed off the request path: the first call lazy-loads the
        # sentence-transformers model (can take tens of seconds), which would
        # otherwise block Save. Ingest must feel instant; the raw layer is
        # already persisted, and build/query will re-index if this hasn't run.
        def _post_ingest():
            try:
                query_service.index_fragment(frag.id, f"{frag.content}\n{frag.note}")
            except Exception as exc:
                print(f"[knowledge_vault] embed on ingest failed: {exc}")
            if settings_manager.load_settings().get("auto_build"):
                try:
                    builder.rebuild(use_ai=True)
                except Exception as exc:
                    print(f"[knowledge_vault] auto-build failed: {exc}")

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
        """Edit content/note and label assignments (user-initiated)."""
        if repository.get_fragment(fid) is None:
            return {"error": "fragment not found"}, 404
        data = request.json or {}
        content = data.get("content")
        note = data.get("note")
        repository.update_fragment(
            fid,
            content=content.strip() if isinstance(content, str) else None,
            note=note.strip() if isinstance(note, str) else None,
        )
        if isinstance(data.get("label_ids"), list):
            repository.set_fragment_labels(fid, [int(x) for x in data["label_ids"]])
        backup.snapshot()
        updated = repository.get_fragment(fid)
        # Re-index vector off the request path (content/note may have changed).
        threading.Thread(
            target=lambda: _safe_index(fid, f"{updated.content}\n{updated.note}"),
            daemon=True).start()
        return {"fragment": updated.to_dict()}, 200

    def delete(self, fid):
        # Hard delete (user-initiated). The AI never deletes; only the user can.
        if repository.get_fragment(fid) is None:
            return {"error": "fragment not found"}, 404
        repository.delete_fragment(fid)
        return {"message": "deleted"}, 200


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
        """Conversational batch import (stateless). The client sends the full
        conversation plus the current draft; Claude replies AND regenerates the
        draft. Nothing is written until /fragments/batch is called.

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
            frag = RawFragment.new_instance(
                content=content,
                note=(it.get("note") or "").strip(),
                raw_text=content,
                kind=(it.get("kind") or "").strip(),
            )
            repository.insert_fragment(frag)
            if label_ids:
                repository.set_fragment_labels(frag.id, label_ids)
            created.append(frag)
        backup.snapshot(tag="batch")
        # Embed all newly-created fragments off the request path.
        ids_texts = [(f.id, f"{f.content}\n{f.note}") for f in created]

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
        return {"label": repository.create_label(name, color)}, 201


@ns.route("/labels/<int:label_id>")
class LabelResource(Resource):
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


@ns.route("/query/ai")
class AiQueryResource(Resource):
    def post(self):
        """Optional AI deep-answer: recall fragments, then let Claude answer."""
        data = request.json or {}
        q = (data.get("q") or "").strip()
        if not q:
            return {"error": "q is required"}, 400
        hits = query_service.search(q, top_k=int(data.get("top_k", 8)))
        context = "\n".join(f"- {h['content']} ({h['note']})" for h in hits)
        prompt = (
            "Answer the question using these knowledge fragments. If none apply, "
            f"say so.\n\nQuestion: {q}\n\nFragments:\n{context}"
        )
        try:
            answer = ai_client.ask_text(prompt, max_tokens=512)
        except Exception as exc:
            return {"error": f"AI query failed: {exc}"}, 502
        return {"answer": answer, "used": hits}, 200


@ns.route("/build")
class BuildResource(Resource):
    def post(self):
        data = request.json or {}
        use_ai = data.get("use_ai", True)
        # Don't start a second build on top of a running one.
        if builder.get_status().get("running"):
            return builder.get_status(), 202
        # Run in the background and return immediately; the client polls
        # /build/status. A synchronous build can take minutes, which would spin
        # the UI button the whole time.
        def _run():
            try:
                builder.rebuild(use_ai=bool(use_ai))
            except Exception as exc:
                print(f"[knowledge_vault] build failed: {exc}")
        threading.Thread(target=_run, daemon=True).start()
        return builder.get_status(), 202


@ns.route("/build/status")
class BuildStatusResource(Resource):
    def get(self):
        return builder.get_status(), 200


@ns.route("/nodes")
class NodesResource(Resource):
    def get(self):
        # A node's labels = union of its source fragments' labels (labels live on
        # the raw layer). Aggregated here so the graph can filter by label.
        labels_by_frag = {f.id: f.label_ids for f in repository.get_fragments(include_archived=True)}
        out = []
        for n in repository.get_nodes():
            d = n.to_dict()
            lids = set()
            for fid in d.get("fragment_ids", []):
                lids.update(labels_by_frag.get(fid, []))
            d["label_ids"] = sorted(lids)
            out.append(d)
        return {"nodes": out}, 200


@ns.route("/edges")
class EdgesResource(Resource):
    def get(self):
        return {"edges": [e.to_dict() for e in repository.get_edges()]}, 200


@ns.route("/lifecycle/stale")
class StaleResource(Resource):
    def get(self):
        return {"stale": lifecycle.stale_nodes()}, 200


def _node_fragment_ids(node_id):
    """Source fragment ids of a node, or None if the node doesn't exist.

    Stale review acts on the raw layer (the source of truth); the node is
    derived and rebuildable, so touching/archiving a node's freshness directly
    would be lost on the next rebuild.
    """
    for n in repository.get_nodes():
        if n.id == node_id:
            import json
            return json.loads(n.fragment_ids or "[]")
    return None


@ns.route("/lifecycle/stale/<int:node_id>/reviewed")
class StaleReviewedResource(Resource):
    def post(self, node_id):
        """Mark a stale node still valid: refresh its source fragments' access time."""
        fids = _node_fragment_ids(node_id)
        if fids is None:
            return {"error": "node not found"}, 404
        for fid in fids:
            repository.touch_fragment(fid)
        lifecycle.recompute_freshness()
        return {"stale": lifecycle.stale_nodes()}, 200


@ns.route("/lifecycle/stale/<int:node_id>/archive")
class StaleArchiveResource(Resource):
    def post(self, node_id):
        """Archive a stale node: soft-remove its source fragments (raw is never hard-deleted)."""
        fids = _node_fragment_ids(node_id)
        if fids is None:
            return {"error": "node not found"}, 404
        for fid in fids:
            repository.archive_fragment(fid)
        backup.snapshot()
        lifecycle.recompute_freshness()
        return {"stale": lifecycle.stale_nodes()}, 200


@ns.route("/lifecycle/check-links")
class CheckLinksResource(Resource):
    def post(self):
        """Probe url-kind fragments over HTTP; flag nodes with dead links stale.

        Opt-in (settings.link_check_enabled) and user-triggered only — this makes
        outbound requests to the saved URLs' hosts. Dead links are a stronger
        signal than time-decay, so we mark the owning node stale directly.
        """
        if not settings_manager.load_settings().get("link_check_enabled"):
            return {"error": "Link checking is off. Enable it in Settings first."}, 403

        frags = [f for f in repository.get_fragments() if (f.kind or "") == "url"]
        # url -> fragment ids (a url may appear in more than one fragment)
        frag_ids_by_url = {}
        for f in frags:
            frag_ids_by_url.setdefault(f.content.strip(), []).append(f.id)

        results = link_checker.check_urls(list(frag_ids_by_url.keys()))
        dead_frag_ids = set()
        for r in results:
            if r.get("alive") is False:   # alive is None = skipped/undetermined → ignore
                dead_frag_ids.update(frag_ids_by_url.get(r["url"], []))

        # Map dead fragments → their nodes, mark those nodes stale.
        flagged = 0
        if dead_frag_ids:
            for n in repository.get_nodes():
                if set(json.loads(n.fragment_ids or "[]")) & dead_frag_ids:
                    repository.set_node_freshness(n.id, "stale")
                    flagged += 1

        checked = len(results)
        dead = sum(1 for r in results if r.get("alive") is False)
        return {
            "checked": checked,
            "dead": dead,
            "flagged_nodes": flagged,
            "results": results,
            "stale": lifecycle.stale_nodes(),
        }, 200


@ns.route("/duplicates")
class DuplicatesResource(Resource):
    def get(self):
        """Near-duplicate fragment pairs from stored vectors. Zero token cost.

        Optional query params `high` / `fuzzy_low` override the similarity tiers.
        """
        def _f(name):
            v = request.args.get(name)
            try:
                return float(v) if v is not None else None
            except ValueError:
                return None
        return dedup.find_duplicate_pairs(high=_f("high"), fuzzy_low=_f("fuzzy_low")), 200


@ns.route("/duplicates/ai-check")
class DuplicatesAiCheckResource(Resource):
    def post(self):
        """Ask the AI to judge fuzzy-band pairs — the only token-spending step.

        Body: {"pairs": [[a_id, b_id], ...]} (typically the current fuzzy pairs).
        Returns {"duplicates": [[a_id, b_id], ...]} — the subset judged duplicates.
        Batched + budget-capped (KV_AI_BUDGET) via builder._ai_dedup_batch.
        """
        data = request.json or {}
        raw_pairs = data.get("pairs") or []
        pairs = []
        for p in raw_pairs:
            try:
                a, b = int(p[0]), int(p[1])
            except (TypeError, ValueError, IndexError):
                continue
            pairs.append((a, b))
        if not pairs:
            return {"duplicates": []}, 200
        frag_by_id = {f.id: f for f in repository.get_fragments()}
        budget = [builder._AI_BUDGET]
        dups = builder._ai_dedup_batch(pairs, frag_by_id, budget)
        return {"duplicates": [list(p) for p in dups]}, 200


@ns.route("/duplicates/resolve")
class DuplicatesResolveResource(Resource):
    def post(self):
        """Resolve one duplicate pair: keep one fragment, archive the other.

        Body: {"keep_id": int, "drop_id": int}. Archive is a soft-delete (raw is
        never hard-deleted; recoverable). Returns the refreshed duplicate lists.
        """
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
        backup.snapshot()
        return dedup.find_duplicate_pairs(), 200


@ns.route("/backups")
class BackupsResource(Resource):
    def get(self):
        import os
        return {"backups": [os.path.basename(b) for b in backup.list_backups()]}, 200

    def post(self):
        """Force a manual backup snapshot now."""
        path = backup.snapshot(tag="manual")
        import os
        return {"backup": os.path.basename(path) if path else None}, 200


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
