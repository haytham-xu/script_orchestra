"""Knowledge Vault — REST controller (blueprint prefix /knowledge-vault).

Stage 1: raw fragment ingest + listing. Query / build / lifecycle endpoints
are added in later stages.
"""
from flask_restx import Namespace, Resource
from flask import request

from . import repository, settings_manager, query_service
from . import builder, lifecycle, ai_client, backup
from .entity import RawFragment
import threading

ns = Namespace("")


@ns.route("/fragments")
class FragmentsResource(Resource):
    def get(self):
        include_archived = request.args.get("archived") == "1"
        frags = repository.get_fragments(include_archived=include_archived)
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

    def delete(self, fid):
        # Hard delete (user-initiated). The AI never deletes; only the user can.
        if repository.get_fragment(fid) is None:
            return {"error": "fragment not found"}, 404
        repository.delete_fragment(fid)
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
        try:
            status = builder.rebuild(use_ai=bool(use_ai))
        except Exception as exc:
            return {"error": f"build failed: {exc}"}, 500
        return status, 200


@ns.route("/build/status")
class BuildStatusResource(Resource):
    def get(self):
        return builder.get_status(), 200


@ns.route("/nodes")
class NodesResource(Resource):
    def get(self):
        return {"nodes": [n.to_dict() for n in repository.get_nodes()]}, 200


@ns.route("/edges")
class EdgesResource(Resource):
    def get(self):
        return {"edges": [e.to_dict() for e in repository.get_edges()]}, 200


@ns.route("/lifecycle/stale")
class StaleResource(Resource):
    def get(self):
        return {"stale": lifecycle.stale_nodes()}, 200


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
