"""One-shot migration to align local manga_viewer data with current code.

Aligns three things the code now expects but production local data still has
in the older shape:

1. Disk folders  <main.target>/<main.id>_<sub.id>  ->  <main.target>/<sub.id>
   (e.g. boutique/bou_hf -> boutique/hf)

2. Settings JSON — each sub gets `target_folder = <sub.id>` and each entry is
   rewritten to the new {key, name, path} shape.

3. Index file  <root>/manga_index.json  ->  <root>/.manga_index/manga_index.json
   (path derived by settings_manager.get_index_path_derived). All Folder.path
   and Folder.files entries are rewritten to the new subfolder names.

Usage:
    python migrate_local_data.py                # dry-run, prints the plan
    python migrate_local_data.py --apply        # actually perform the moves
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

SETTINGS_FILE = HERE.parent / "manga_viewer_settings.json"


def load_settings():
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_settings(data):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def norm_category_entry(c):
    """Read a legacy {id,label,target_folder} entry into a canonical dict."""
    if not isinstance(c, dict):
        return {"key": "", "name": "", "path": ""}
    key = c.get("key") or c.get("id") or ""
    name = c.get("name") if c.get("name") is not None else c.get("label", "")
    path = c.get("path") if c.get("path") is not None else c.get("target_folder", "")
    return {"key": key, "name": name or "", "path": path or ""}


def plan_folder_renames(root, mains, subs):
    """For every existing <root>/<main.path>/<main.key>_<sub.key> dir, plan a
    rename to <root>/<main.path>/<sub.key>. Skips ones that don't exist and
    ones already in target shape."""
    renames = []  # list of (src, dst)
    skipped = []  # list of (path, reason)
    for m in mains:
        m_key = m["key"]
        m_path = m["path"]
        if not m_key or not m_path:
            skipped.append((f"main {m}", "missing key or path"))
            continue
        for s in subs:
            s_key = s["key"]
            if not s_key:
                continue
            old_name = f"{m_key}_{s_key}"
            src = os.path.join(root, m_path, old_name)
            dst = os.path.join(root, m_path, s_key)
            if not os.path.isdir(src):
                skipped.append((src, "src not present"))
                continue
            if os.path.exists(dst):
                skipped.append((dst, "dst already exists — will NOT overwrite"))
                continue
            renames.append((src, dst))
    return renames, skipped


def rewrite_index(index_data, mains, subs):
    """Return (new_index_dict, num_folders_touched, num_url_replacements).

    Replaces every occurrence of `<main.path>/<main.key>_<sub.key>` inside
    Folder.path and each entry of Folder.files with `<main.path>/<sub.key>`.
    Also clears the metadata sets (they get rebuilt by the app on next
    write). The substitution is a plain string replace so it tolerates
    mixed path separators.
    """
    subs_pairs = []
    for m in mains:
        for s in subs:
            if not (m["key"] and m["path"] and s["key"]):
                continue
            old = f"{m['path']}/{m['key']}_{s['key']}"
            new = f"{m['path']}/{s['key']}"
            subs_pairs.append((old, new))
    subs_pairs.sort(key=lambda p: len(p[0]), reverse=True)  # longer prefix wins

    folders = index_data.get("folders", {})
    touched = 0
    url_repls = 0
    for fid, fd in folders.items():
        orig_path = fd.get("path", "")
        new_path = orig_path
        for old, new in subs_pairs:
            new_path = new_path.replace(old, new)
        if new_path != orig_path:
            fd["path"] = new_path
            touched += 1
        new_files = []
        for u in fd.get("files", []):
            nu = u
            for old, new in subs_pairs:
                nu = nu.replace(old, new)
            if nu != u:
                url_repls += 1
            new_files.append(nu)
        fd["files"] = new_files
    return index_data, touched, url_repls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually perform the migration")
    args = ap.parse_args()

    apply = args.apply
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== manga_viewer migration [{mode}] ===\n")

    settings = load_settings()
    cats = settings.get("categories", {})
    mains = [norm_category_entry(c) for c in cats.get("main", [])]
    subs = [norm_category_entry(c) for c in cats.get("sub", [])]

    root = settings.get("paths", {}).get("root_path", "")
    if not root:
        print("[ERROR] paths.root_path is empty; aborting")
        return 2
    root = os.path.abspath(root)
    print(f"root_path = {root}")
    print(f"mains: {[(m['key'], m['path']) for m in mains]}")
    print(f"subs:  {[s['key'] for s in subs]}\n")

    # --- 1. plan folder renames ---
    renames, skipped = plan_folder_renames(root, mains, subs)
    print(f"--- Step 1: folder renames ({len(renames)} planned, {len(skipped)} skipped) ---")
    for src, dst in renames:
        print(f"  RENAME  {src}\n       -> {dst}")
    if skipped:
        print(f"  ({len(skipped)} skipped: e.g. {skipped[0]!r})")

    # --- 2. plan settings JSON changes ---
    new_subs = []
    for s in subs:
        new_subs.append({"key": s["key"], "name": s["name"] or s["key"].upper(), "path": s["key"]})
    new_mains = []
    for m in mains:
        new_mains.append({"key": m["key"], "name": m["name"] or m["key"], "path": m["path"]})
    print(f"\n--- Step 2: settings JSON ---")
    print(f"  main entries after: {new_mains}")
    print(f"  sub  entries after: {new_subs}")

    # --- 3. plan index file relocation + rewrite ---
    old_index = os.path.join(root, "manga_index.json")
    new_index_dir = os.path.join(root, ".manga_index")
    new_index = os.path.join(new_index_dir, "manga_index.json")
    print(f"\n--- Step 3: index file ---")
    print(f"  move   {old_index}")
    print(f"     -> {new_index}")

    if os.path.exists(old_index):
        with open(old_index, "r", encoding="utf-8") as f:
            index_data = json.load(f)
        _, touched, url_repls = rewrite_index(index_data, mains, subs)
        print(f"  will rewrite {touched} folder.path entries and {url_repls} URL entries")
    else:
        index_data = None
        print(f"  (source index not found; will skip)")

    if not apply:
        print("\nDry-run only. Re-run with --apply to perform.")
        return 0

    # === APPLY ===
    print("\n=== APPLYING ===")

    # 1. rename folders
    for src, dst in renames:
        print(f"  rename {src} -> {dst}")
        os.rename(src, dst)

    # 2. write settings
    settings["categories"]["main"] = new_mains
    settings["categories"]["sub"] = new_subs
    save_settings(settings)
    print(f"  settings written to {SETTINGS_FILE}")

    # 3. rewrite + move index
    if index_data is not None:
        index_data, touched, url_repls = rewrite_index(index_data, mains, subs)
        os.makedirs(new_index_dir, exist_ok=True)
        with open(new_index, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        print(f"  new index written -> {new_index}")
        # leave old file as safety net
        safety_name = old_index + ".pre_migration"
        os.rename(old_index, safety_name)
        print(f"  old index renamed  -> {safety_name}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
