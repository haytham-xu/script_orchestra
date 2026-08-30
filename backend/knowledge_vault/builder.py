"""Knowledge Vault — knowledge-network builder (the AI core).

Rebuilds the derived network from the append-only raw layer. Vector recall
narrows candidates cheaply; Claude is only asked to judge dedup + relations on
those candidates (keeps token cost bounded). The raw layer is never modified.

Build is expensive/slow by design; query is not. This runs on explicit
"Rebuild" or, if auto_build is on, incrementally after ingest.
"""
import json
import hashlib
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
# AI dedup (opt-in) judges candidate pairs in batches of this many per call, so
# the fuzzy-dedup phase stays a handful of CLI spawns rather than one-per-pair.
_DEDUP_BATCH = int(_os.environ.get("KV_DEDUP_BATCH", "10"))
# AI edge-relation labelling (opt-in). Off by default: the similarity heuristic
# (same-topic/related) is instant and good enough; richer labels (prereq/
# alternative) need AI, but ONLY batched — per-edge CLI calls made builds crawl.
_AI_RELATIONS = _os.environ.get("KV_AI_RELATIONS", "0") == "1"
_RELATION_BATCH = int(_os.environ.get("KV_RELATION_BATCH", "10"))


def get_status() -> dict:
    return dict(_status)


def _content_hash(content: str, note: str) -> str:
    """Stable hash of a fragment's embedded text, for incremental re-embedding."""
    return hashlib.sha256(f"{content or ''}\n{note or ''}".encode("utf-8")).hexdigest()


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
        # Incremental embedding: re-embed only fragments whose content changed
        # (hash mismatch) or that were never embedded. Unchanged fragments keep
        # their stored vector — embedding dominates build time on a large vault,
        # and it's a pure function of (content, note), so this is safe. The
        # network itself is still rebuilt in full below (no partial-graph state).
        store = get_store()
        prev_hashes = repository.get_vector_hashes()
        reembedded = 0
        for f in frags:
            h = _content_hash(f.content, f.note)
            if prev_hashes.get(f.id) == h:
                continue  # unchanged → reuse existing vector
            vec = embedder.embed(f"{f.content}\n{f.note}")
            repository.save_vector(f.id, vec, h)
            reembedded += 1
        _status["reembedded"] = reembedded

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
        # First pass: auto-group the near-identical (sim>=0.97, zero AI) and
        # collect the fuzzy 0.80-0.97 candidate pairs for a possible batched AI
        # judgement. We do NOT call the AI per pair here — dozens of serial CLI
        # spawns are exactly what made builds crawl. See _ai_dedup_batch below.
        fuzzy_pairs = []          # [(a_id, b_id)] awaiting AI judgement
        seen_fuzzy = set()
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
                if sim >= 0.97:  # near-identical → auto group, no AI
                    group_of[rep(cand_id)] = rep(f.id)
                elif _AI_DEDUP:
                    key = tuple(sorted((f.id, cand_id)))
                    if key not in seen_fuzzy:
                        seen_fuzzy.add(key)
                        fuzzy_pairs.append(key)

        # Second pass: batched AI dedup on the fuzzy band (opt-in, budget-capped).
        # One prompt judges many pairs, so the whole phase is a handful of CLI
        # calls instead of one-per-pair.
        if _AI_DEDUP and fuzzy_pairs and ai_budget[0] > 0:
            for a_id, b_id in _ai_dedup_batch(fuzzy_pairs, frag_by_id, ai_budget):
                if rep(a_id) != rep(b_id):
                    group_of[rep(b_id)] = rep(a_id)

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
                node = _make_node(members, frag_by_id)
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
        inserted_edges = []   # (edge, src_node_id, tgt_node_id) for optional AI relabel
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
                    # the signal; the label is a nicety. Optionally, one BATCHED
                    # AI pass below refines these into richer relations.
                    relation = "same-topic" if sim >= 0.75 else "related"
                    edge = repository.insert_edge(Edge(None, src_node, tgt_node, relation, round(sim, 3)))
                    inserted_edges.append(edge)
                    edge_count += 1
        _status["edges"] = edge_count

        # Optional: refine relation labels in batched AI calls (opt-in, budget-capped).
        if use_ai and _AI_RELATIONS and inserted_edges and ai_budget[0] > 0:
            _status["phase"] = "relations"
            node_by_id = {n.id: n for n in repository.get_nodes()}
            _ai_relabel_edges(inserted_edges, node_by_id, ai_budget)

        _status["phase"] = "lifecycle"
        lifecycle.recompute_freshness()

        _status.update(running=False, phase="done", last_run=datetime.now().isoformat())
        return get_status()
    except Exception as exc:
        _status.update(running=False, phase=f"error: {exc}")
        raise


def _make_node(member_ids, frag_by_id) -> KnowledgeNode:
    """Build a node from its member fragments with fast heuristics only.

    Titles/summaries/kinds are refined afterwards in one batched AI call
    (_ai_enrich_nodes) rather than per node, so this stays instant.
    """
    members = [frag_by_id[m] for m in member_ids if m in frag_by_id]
    primary = members[0]
    title = (primary.note or primary.content)[:80]
    summary = primary.content
    # kind is inferred (users no longer type it): heuristic here, AI refines later.
    kind = primary.kind or _guess_kind(primary.content)
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


def _ai_dedup_batch(pairs, frag_by_id, ai_budget) -> list:
    """Judge many candidate duplicate pairs with as few AI calls as possible.

    pairs: [(a_id, b_id)] in the fuzzy similarity band. Chunks them into batches
    (KV_DEDUP_BATCH pairs per prompt) and asks Claude for a verdict on each in a
    single JSON reply — so the phase costs a handful of CLI spawns, not one per
    pair (per-pair spawning is what made builds crawl). Each batch decrements the
    shared ai_budget; once exhausted the remaining pairs are left un-merged
    (vector already auto-grouped the near-identical, so this only skips fuzzy
    merges). Returns the subset of pairs judged duplicates.
    """
    dups = []
    for start in range(0, len(pairs), _DEDUP_BATCH):
        if ai_budget[0] <= 0:
            break
        ai_budget[0] -= 1
        batch = pairs[start:start + _DEDUP_BATCH]
        items = []
        for i, (a_id, b_id) in enumerate(batch):
            a, b = frag_by_id.get(a_id), frag_by_id.get(b_id)
            if not a or not b:
                continue
            items.append({
                "i": i,
                "a": f"{a.content} | {a.note}"[:_ITEM_TEXT_MAX],
                "b": f"{b.content} | {b.note}"[:_ITEM_TEXT_MAX],
            })
        if not items:
            continue
        prompt = (
            "For each pair below, decide if A and B are duplicates (the same "
            "underlying item, just worded differently). Return STRICT JSON: "
            '{"pairs":[{"i":<i>,"duplicate":true|false}]}.'
            "\n\nPAIRS:\n" + json.dumps(items, ensure_ascii=False)
        )
        try:
            res = ai_client.ask_json(prompt, max_tokens=1024, timeout=60) or {}
        except Exception as exc:
            print(f"[knowledge_vault] batch dedup failed, keeping vector groups: {exc}")
            continue
        for p in (res.get("pairs") or []):
            try:
                idx = int(p.get("i"))
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(batch) and p.get("duplicate"):
                dups.append(batch[idx])
    return dups


_RELATIONS = ("same-topic", "prereq", "alternative", "related")


def _ai_relabel_edges(edges, node_by_id, ai_budget) -> None:
    """Refine edge relation labels via batched AI calls (opt-in, budget-capped).

    The heuristic already set same-topic/related from similarity; here Claude may
    upgrade a batch of edges to richer relations (prereq/alternative). Batched
    (KV_RELATION_BATCH edges per prompt) so the phase is a few CLI spawns, not one
    per edge. Each batch decrements ai_budget; leftover edges keep their heuristic
    label. Unknown/absent verdicts are left unchanged.
    """
    for start in range(0, len(edges), _RELATION_BATCH):
        if ai_budget[0] <= 0:
            break
        ai_budget[0] -= 1
        batch = edges[start:start + _RELATION_BATCH]
        _status["phase"] = f"relations {start + 1}-{start + len(batch)}/{len(edges)}"
        items = []
        for i, e in enumerate(batch):
            a, b = node_by_id.get(e.source_id), node_by_id.get(e.target_id)
            if not a or not b:
                continue
            items.append({
                "i": i,
                "a": f"{a.title}: {a.summary}"[:_ITEM_TEXT_MAX],
                "b": f"{b.title}: {b.summary}"[:_ITEM_TEXT_MAX],
            })
        if not items:
            continue
        prompt = (
            "For each pair (A, B) below, classify how A relates to B with ONE of: "
            "same-topic, prereq (A is a prerequisite for B), alternative (A and B "
            "are interchangeable options), related. Return STRICT JSON: "
            '{"edges":[{"i":<i>,"relation":"..."}]}.'
            "\n\nPAIRS:\n" + json.dumps(items, ensure_ascii=False)
        )
        try:
            res = ai_client.ask_json(prompt, max_tokens=1024, timeout=60) or {}
        except Exception as exc:
            print(f"[knowledge_vault] batch relation labelling failed, keeping heuristics: {exc}")
            continue
        for r in (res.get("edges") or []):
            try:
                idx = int(r.get("i"))
            except (TypeError, ValueError):
                continue
            rel = str(r.get("relation") or "").strip()
            if 0 <= idx < len(batch) and rel in _RELATIONS:
                repository.set_edge_relation(batch[idx].id, rel)


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
