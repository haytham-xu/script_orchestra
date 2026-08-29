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

# Cap AI calls per build so it can't run away: each call is a serial CLI spawn
# (seconds), so dozens of them turn a build into minutes. Beyond the budget we
# fall back to vector-only heuristics. Tune via KV_AI_BUDGET.
import os as _os
_AI_BUDGET = int(_os.environ.get("KV_AI_BUDGET", "30"))
_AI_DEDUP = _os.environ.get("KV_AI_DEDUP", "0") == "1"   # AI dedup off by default (slow, low value)
# Token-cost guards for the classify phase: batch N nodes per AI call, and cap
# each item's text length so long fragments can't blow up the prompt.
_CLASSIFY_BATCH = int(_os.environ.get("KV_CLASSIFY_BATCH", "20"))
_ITEM_TEXT_MAX = int(_os.environ.get("KV_ITEM_TEXT_MAX", "400"))


def get_status() -> dict:
    return dict(_status)


def rebuild(use_ai: bool = True) -> dict:
    """Full rebuild of the knowledge network from raw fragments.

    use_ai=False → build nodes 1:1 from fragments + vector-similarity edges only
    (no token cost). use_ai=True → Claude refines dedup grouping + node titles,
    up to a bounded number of calls (_AI_BUDGET) so the build stays responsive.
    """
    _status.update(running=True, phase="embedding", nodes=0, edges=0)
    # Mutable budget shared by the AI helpers this run.
    ai_budget = [_AI_BUDGET if use_ai else 0]
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
                # AI dedup on the fuzzy 0.80–0.97 band is the lowest-value AI
                # use (vector already auto-groups the near-identical) and it's
                # what made builds crawl. Off by default; opt in via env.
                if not is_dup and _AI_DEDUP and ai_budget[0] > 0:
                    ai_budget[0] -= 1
                    is_dup = _ai_is_duplicate(f, frag_by_id[cand_id])
                if is_dup:
                    group_of[rep(cand_id)] = rep(f.id)

        # Materialize nodes from groups.
        _status["phase"] = "nodes"
        # Build every node with the fast heuristic first (instant), so nodes
        # exist immediately. AI enrichment (better titles/summaries) happens in
        # ONE batched call below — not one CLI spawn per node, which was the
        # slow part that made the build appear to hang.
        node_id_by_group = {}
        rep_of_node = {}
        for f in frags:
            r = rep(f.id)
            if r not in node_id_by_group:
                members = [g for g in frag_ids if rep(g) == r]
                node = _make_node(members, frag_by_id, use_ai=False)
                node = repository.insert_node(node)
                node_id_by_group[r] = node.id
                rep_of_node[node.id] = (r, members)
        _status["nodes"] = len(node_id_by_group)

        if use_ai and node_id_by_group:
            _status["phase"] = "classify"
            _ai_enrich_nodes(rep_of_node, frag_by_id)

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
                    # Relation label from similarity — cheap and instant. We do
                    # NOT call the AI per edge here: with N nodes that is dozens
                    # of serial CLI calls, each seconds long, which made the
                    # build crawl (and appear to hang). The edge itself carries
                    # the signal; the label is a nicety.
                    relation = "same-topic" if sim >= 0.75 else "related"
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
    # kind is inferred (users no longer type it): heuristic first, AI refines.
    kind = primary.kind or _guess_kind(primary.content)
    if use_ai:
        info = _ai_classify(members)
        if info:
            title = (info.get("title") or title)[:120]
            summary = info.get("summary") or summary
            if info.get("kind"):
                kind = info["kind"]
    return KnowledgeNode(None, title=title, summary=summary, kind=kind,
                         fragment_ids=json.dumps(member_ids), freshness="fresh",
                         updated_at=datetime.now().isoformat())


def _guess_kind(content: str) -> str:
    c = (content or "").strip().lower()
    if c.startswith("http://") or c.startswith("https://"):
        return "url"
    if c.startswith(("kubectl", "az ", "aws ", "docker", "git ", "npm ", "pip ", "curl ", "ssh ")):
        return "command"
    if "\n" in c or c.startswith(("#!/", "def ", "function ", "import ")):
        return "script"
    return "note"


def _ai_is_duplicate(a, b) -> bool:
    prompt = (
        "Are these two knowledge fragments duplicates (same underlying item, "
        "just worded differently)? Answer JSON {\"duplicate\": true|false}.\n\n"
        f"A: {a.content} | note: {a.note}\nB: {b.content} | note: {b.note}"
    )
    try:
        res = ai_client.ask_json(prompt, max_tokens=64, timeout=25)
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


def _ai_enrich_nodes(rep_of_node: dict, frag_by_id: dict) -> None:
    """Enrich node titles/summaries/kinds via batched AI calls.

    To keep token cost bounded (and avoid context overflow when the vault is
    large or fragments are long), we chunk nodes into batches and hard-truncate
    each item's text. Falls back silently to the heuristic values already stored
    if a call fails. rep_of_node: {node_id: (group_rep, [member_frag_ids])}.
    """
    all_items = []
    for node_id, (_r, member_ids) in rep_of_node.items():
        members = [frag_by_id[m] for m in member_ids if m in frag_by_id]
        joined = " ; ".join(f"{m.content} ({m.note})" if m.note else m.content for m in members)
        all_items.append({"id": node_id, "text": joined[:_ITEM_TEXT_MAX]})

    for start in range(0, len(all_items), _CLASSIFY_BATCH):
        batch = all_items[start:start + _CLASSIFY_BATCH]
        _status["phase"] = f"classify {start + 1}-{start + len(batch)}/{len(all_items)}"
        prompt = (
            "For each knowledge item below, produce a concise title, a one-line "
            "summary, and a kind (one of: url, command, script, note). Return STRICT "
            'JSON: {"nodes":[{"id":<id>,"title":"...","summary":"...","kind":"..."}]}.'
            "\n\nITEMS:\n" + json.dumps(batch, ensure_ascii=False)
        )
        try:
            res = ai_client.ask_json(prompt, max_tokens=4096, timeout=90) or {}
        except Exception as exc:
            print(f"[knowledge_vault] batch classify failed, keeping heuristics: {exc}")
            continue
        for n in (res.get("nodes") or []):
            try:
                nid = int(n.get("id"))
            except (TypeError, ValueError):
                continue
            if nid not in rep_of_node:
                continue
            title = str(n.get("title") or "").strip()[:120]
            summary = str(n.get("summary") or "").strip()
            kind = str(n.get("kind") or "").strip()
            if title or summary or kind:
                repository.update_node_meta(nid, title or "(untitled)", summary, kind or "note")


def _ai_classify(members) -> dict:
    lines = "\n".join(f"- {m.content} | {m.note}" for m in members)
    plural = "these fragments (they were judged duplicates)" if len(members) > 1 else "this fragment"
    prompt = (
        f"Classify and summarize {plural}. Return JSON "
        "{\"title\": \"...\", \"summary\": \"...\", \"kind\": \"url|command|script|link|doc|note\"}.\n\n"
        + lines
    )
    try:
        return ai_client.ask_json(prompt, max_tokens=256, timeout=25) or {}
    except Exception as exc:
        print(f"[knowledge_vault] AI classify failed: {exc}")
        return {}
