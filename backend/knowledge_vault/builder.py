"""Knowledge Vault — knowledge-network builder (the AI core).

Rebuilds the derived network from the append-only raw layer. Vector recall
narrows candidates cheaply; Claude is only asked to judge dedup + relations on
those candidates (keeps token cost bounded). The raw layer is never modified.

Build is expensive/slow by design; query is not. This runs on explicit
"Rebuild" or, if auto_build is on, incrementally after ingest.
"""
import json
from datetime import datetime

from . import repository, embedder, lifecycle, settings_manager, ai_client
from .entity import KnowledgeNode, Edge
from .vector_store import get_store

_status = {"running": False, "phase": "idle", "nodes": 0, "edges": 0, "last_run": None}


def get_status() -> dict:
    return dict(_status)


def rebuild(use_ai: bool = True) -> dict:
    """Full rebuild of the knowledge network from raw fragments.

    use_ai=False → build nodes 1:1 from fragments + vector-similarity edges only
    (no token cost). use_ai=True → Claude refines dedup grouping + relation labels.
    """
    _status.update(running=True, phase="embedding", nodes=0, edges=0)
    try:
        frags = [f for f in repository.get_fragments() if not f.archived]
        # (Re)embed everything so vectors match current raw content.
        store = get_store()
        for f in frags:
            store.add(f.id, embedder.embed(f"{f.content}\n{f.note}"))

        repository.clear_network()
        settings = settings_manager.load_settings()
        top_k = settings.get("relate_top_k", 5)

        # ---- nodes: one per fragment, optionally deduped by AI --------
        _status["phase"] = "dedup"
        # Group fragments that are near-duplicates. Start each in its own group.
        frag_ids = [f.id for f in frags]
        group_of = {fid: fid for fid in frag_ids}   # union-find-ish (representative)

        def rep(x):
            while group_of[x] != x:
                group_of[x] = group_of[group_of[x]]
                x = group_of[x]
            return x

        vecs = {fid: v for fid, v in repository.get_all_vectors()}
        frag_by_id = {f.id: f for f in frags}
        for f in frags:
            if f.id not in vecs:
                continue
            cands = store.search(vecs[f.id], top_k + 1)
            for cand_id, sim in cands:
                if cand_id == f.id or cand_id not in frag_by_id:
                    continue
                if sim < 0.80:
                    continue  # only strong candidates are dedup-considered
                if rep(cand_id) == rep(f.id):
                    continue
                is_dup = sim >= 0.97  # near-identical → auto group
                if not is_dup and use_ai:
                    is_dup = _ai_is_duplicate(f, frag_by_id[cand_id])
                if is_dup:
                    group_of[rep(cand_id)] = rep(f.id)

        # Materialize nodes from groups.
        _status["phase"] = "nodes"
        node_id_by_group = {}
        for f in frags:
            r = rep(f.id)
            group_id = node_id_by_group.get(r)
            if group_id is None:
                members = [g for g in frag_ids if rep(g) == r]
                node = _make_node(members, frag_by_id, use_ai)
                node = repository.insert_node(node)
                node_id_by_group[r] = node.id
        _status["nodes"] = len(node_id_by_group)

        # ---- edges: relate nodes by fragment similarity --------------
        _status["phase"] = "edges"
        node_of_frag = {}
        for r, nid in node_id_by_group.items():
            for g in frag_ids:
                if rep(g) == r:
                    node_of_frag[g] = nid
        seen_pairs = set()
        edge_count = 0
        for f in frags:
            if f.id not in vecs:
                continue
            src_node = node_of_frag.get(f.id)
            for cand_id, sim in store.search(vecs[f.id], top_k + 1):
                if cand_id == f.id or cand_id not in node_of_frag:
                    continue
                tgt_node = node_of_frag[cand_id]
                if tgt_node == src_node:
                    continue
                if 0.55 <= sim < 0.97:
                    pair = tuple(sorted((src_node, tgt_node)))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    relation = "related"
                    if use_ai and sim < 0.85:
                        relation = _ai_relation(frag_by_id[f.id], frag_by_id[cand_id]) or "related"
                    repository.insert_edge(Edge(None, src_node, tgt_node, relation, round(sim, 3)))
                    edge_count += 1
        _status["edges"] = edge_count

        _status["phase"] = "lifecycle"
        lifecycle.recompute_freshness()

        _status.update(running=False, phase="done", last_run=datetime.now().isoformat())
        return get_status()
    except Exception as exc:
        _status.update(running=False, phase=f"error: {exc}")
        raise


def _make_node(member_ids, frag_by_id, use_ai) -> KnowledgeNode:
    members = [frag_by_id[m] for m in member_ids if m in frag_by_id]
    primary = members[0]
    title = (primary.note or primary.content)[:80]
    summary = primary.content
    kind = primary.kind
    if use_ai and len(members) > 1:
        # Let AI title/summarize a merged (deduped) node.
        merged = _ai_merge_title(members)
        if merged:
            title = merged.get("title", title)[:120]
            summary = merged.get("summary", summary)
    return KnowledgeNode(None, title=title, summary=summary, kind=kind,
                         fragment_ids=json.dumps(member_ids), freshness="fresh",
                         updated_at=datetime.now().isoformat())


def _ai_is_duplicate(a, b) -> bool:
    prompt = (
        "Are these two knowledge fragments duplicates (same underlying item, "
        "just worded differently)? Answer JSON {\"duplicate\": true|false}.\n\n"
        f"A: {a.content} | note: {a.note}\nB: {b.content} | note: {b.note}"
    )
    try:
        res = ai_client.ask_json(prompt, max_tokens=64)
    except Exception as exc:
        print(f"[knowledge_vault] AI dedup failed, falling back to vector: {exc}")
        return False
    return bool(res and res.get("duplicate"))


def _ai_relation(a, b) -> str:
    prompt = (
        "Classify the relationship between fragment A and B with one of: "
        "same-topic, prereq, alternative, related. JSON {\"relation\": \"...\"}.\n\n"
        f"A: {a.content} | {a.note}\nB: {b.content} | {b.note}"
    )
    try:
        res = ai_client.ask_json(prompt, max_tokens=64)
    except Exception as exc:
        print(f"[knowledge_vault] AI relation failed, defaulting to 'related': {exc}")
        return "related"
    rel = (res or {}).get("relation", "related")
    return rel if rel in ("same-topic", "prereq", "alternative", "related") else "related"


def _ai_merge_title(members) -> dict:
    lines = "\n".join(f"- {m.content} | {m.note}" for m in members)
    prompt = (
        "These fragments were judged duplicates. Give a concise merged title and "
        "summary. JSON {\"title\": \"...\", \"summary\": \"...\"}.\n\n" + lines
    )
    try:
        return ai_client.ask_json(prompt, max_tokens=256) or {}
    except Exception as exc:
        print(f"[knowledge_vault] AI merge-title failed: {exc}")
        return {}
