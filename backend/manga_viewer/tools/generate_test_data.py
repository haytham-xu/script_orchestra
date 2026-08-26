#!/usr/bin/env python3
"""
Manga Viewer — test data generator / resetter.

Creates test manga folders arranged under the category tree
    <root>/<main.path>/<sub.path>/<manga folder>/files
so the viewer's category-combination scan discovers them and infers their
main/sub category from the folder they live in. Spans many media scenarios
(images, many-images, single, nested, video, pdf, mixed, empty, long CJK name).

Also rewrites the (now minimal) manga_viewer settings and pre-builds
manga_index.json (categories inferred from the tree; a slice left
uncategorized by placing them outside the category tree).

Running again RESETS everything.

Usage:
    cd backend && ./venv/bin/python manga_viewer/tools/generate_test_data.py

test_data/ and manga_viewer_settings.json are gitignored.
"""
import json
import os
import random
import shutil
import uuid

from PIL import Image, ImageDraw

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_ROOT = os.path.join(MODULE_DIR, "test", "test_data")
# root_path for the viewer = the category tree root
ROOT = os.path.join(TEST_ROOT, "library")
DELETE_DIR = os.path.join(TEST_ROOT, "to_del")
SETTINGS_FILE = os.path.join(MODULE_DIR, "manga_viewer_settings.json")

HOST_URL = "http://127.0.0.1:50001"
TOTAL_IN_TREE = 16        # manga inside the category tree
TOTAL_LOOSE = 4           # manga NOT under any combo → not scanned, stay outside
# Every Nth in-tree manga is created on disk but LEFT OUT of the pre-built index,
# so a refresh discovers it as new and auto-infers its category. Lets you test
# the refresh discovery + inference path out of the box.
UNINDEXED_EVERY = 5

random.seed(20260826)

# Categories: {key, name, path}. All values are meaningless placeholders.
MAIN_CATS = [
    {"key": "m1", "name": "Main One", "path": "main_1"},
    {"key": "m2", "name": "Main Two", "path": "main_2"},
]
SUB_CATS = [
    {"key": "s1", "name": "Sub One", "path": "sub_1"},
    {"key": "s2", "name": "Sub Two", "path": "sub_2"},
    {"key": "s3", "name": "Sub Three", "path": "sub_3"},
    {"key": "s4", "name": "Sub Four", "path": "sub_4"},
]
# Neutral placeholder authors. A couple of non-ASCII entries are kept only to
# exercise multilingual layout/sorting — they carry no real-world meaning.
AUTHORS = ["author_01", "author_02", "author_03", "著者04", "저자05", "author_06"]
IMG_COLORS = [
    (231, 76, 60), (52, 152, 219), (46, 204, 113), (155, 89, 182),
    (241, 196, 15), (26, 188, 156), (230, 126, 34), (149, 165, 166),
]


# ---- media generators (unchanged in spirit) --------------------------
def make_image(path, label, idx):
    img = Image.new("RGB", (480, 680), IMG_COLORS[idx % len(IMG_COLORS)])
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 460, 660], outline=(255, 255, 255), width=4)
    d.multiline_text((40, 40), f"{label}\np.{idx + 1}", fill=(255, 255, 255))
    img.save(path)


def make_video(path):
    try:
        import imageio.v2 as imageio
        import numpy as np
        frames = [np.array(Image.new("RGB", (128, 128), IMG_COLORS[i % len(IMG_COLORS)]))
                  for i in range(8)]
        imageio.mimsave(path, frames, fps=8, macro_block_size=None)
    except Exception as exc:
        print(f"  [video] ffmpeg unavailable ({exc}); stub")
        with open(path, "wb") as f:
            f.write(b"\x00\x00\x00\x18ftypmp42")


def make_pdf(path, label):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path)
    for i in range(3):
        c.setFillColorRGB(*[v / 255 for v in IMG_COLORS[i % len(IMG_COLORS)]])
        c.rect(0, 0, 600, 850, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.drawString(50, 800, f"{label} - page {i + 1}")
        c.showPage()
    c.save()


def scenario_for(i):
    # Explicit list so a small run (16) still covers every scenario at least
    # once. Extra slots go to the common image cases.
    plan = [
        {"kind": "images", "n": 6},
        {"kind": "images", "n": 10},
        {"kind": "many_images", "n": 60},
        {"kind": "single_image", "n": 1},
        {"kind": "nested", "n": 5},
        {"kind": "video", "n": 3},
        {"kind": "pdf", "n": 1},
        {"kind": "mixed", "n": 4},
        {"kind": "empty", "n": 0},
        {"kind": "long_name", "n": 4},
        # remaining slots: common cases + a second of the trickier ones
        {"kind": "images", "n": 8},
        {"kind": "many_images", "n": 45},
        {"kind": "nested", "n": 6},
        {"kind": "video", "n": 2},
        {"kind": "single_image", "n": 1},
        {"kind": "images", "n": 5},
    ]
    return plan[i % len(plan)]


def folder_name(i, kind):
    a = random.choice(AUTHORS)
    if kind == "long_name":
        return (f"[{a}] long_title_for_layout_overflow_test 超长标题布局测试 "
                f"very-long-folder-name-{i:03d}-aaaaaaaaaaaaaaaaaaaa [tag1][tag2]")
    if kind == "empty":
        return f"[{a}] empty_case_{i:03d}"
    return f"[{a}] test_manga_{i:03d}_{kind}"


def populate(folder_path, name, scn):
    os.makedirs(folder_path, exist_ok=True)
    kind, n = scn["kind"], scn["n"]
    count = 0
    if kind in ("images", "many_images", "single_image", "long_name"):
        for i in range(n):
            ext = ".png" if i % 3 == 0 else ".jpg"
            make_image(os.path.join(folder_path, f"{i + 1:03d}{ext}"), name, i); count += 1
    elif kind == "nested":
        for i in range(n):
            make_image(os.path.join(folder_path, f"{i + 1:03d}.jpg"), name, i); count += 1
        sub = os.path.join(folder_path, "chapter_02"); os.makedirs(sub, exist_ok=True)
        for i in range(n):
            make_image(os.path.join(sub, f"{i + 1:03d}.jpg"), name, i); count += 1
    elif kind == "video":
        for i in range(n):
            make_video(os.path.join(folder_path, f"clip_{i + 1:02d}.mp4")); count += 1
    elif kind == "pdf":
        make_pdf(os.path.join(folder_path, "book.pdf"), name); count += 1
    elif kind == "mixed":
        for i in range(n):
            make_image(os.path.join(folder_path, f"{i + 1:03d}.jpg"), name, i); count += 1
        make_video(os.path.join(folder_path, "trailer.mp4"))
        make_pdf(os.path.join(folder_path, "extra.pdf"), name); count += 2
    size = sum(os.path.getsize(os.path.join(b, fn))
               for b, _, files in os.walk(folder_path) for fn in files)
    return size, count


def build_file_list(folder_path):
    from urllib.parse import quote
    exts = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp",
            ".mp4", ".webm", ".mov", ".avi", ".mkv", ".pdf")
    urls = []

    def rel_url(full):
        rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
        return f"{HOST_URL}/manga-viewer/file/{quote(rel)}"

    entries = sorted(os.listdir(folder_path))
    for fn in entries:
        fp = os.path.join(folder_path, fn)
        if os.path.isfile(fp) and fn.lower().endswith(exts):
            urls.append(rel_url(fp))
    for dn in entries:
        dp = os.path.join(folder_path, dn)
        if os.path.isdir(dp):
            for sf in sorted(os.listdir(dp)):
                sfp = os.path.join(dp, sf)
                if os.path.isfile(sfp) and sf.lower().endswith(exts):
                    urls.append(rel_url(sfp))
    return urls


def write_settings():
    settings = {
        "random": {"count": 6, "enabled": True},
        "categories": {"main": MAIN_CATS, "sub": SUB_CATS},
        "display": {
            "page_size": 12,
            "show_uninitialized_only": False,
            "default_sort": "random",
            "classifier_mode_enabled": True,
            "name_sort_enabled": False,
            "size_sort_enabled": False,
        },
        "paths": {
            "root_path": ROOT,
            "delete_paths": DELETE_DIR,
            "ignore_scan_folders": [],
        },
    }
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    print(f"✓ settings → {SETTINGS_FILE}")


def build_index(folders):
    """Pre-build index in the derived location <root>/.manga_index/.

    Folders flagged in_index=False are omitted so a refresh will discover
    them and infer their category from the combo dir they live in.
    """
    index_dir = os.path.join(ROOT, ".manga_index")
    os.makedirs(index_dir, exist_ok=True)
    index = {"metadata": {}, "folders": {}}
    auth_set, main_set, sub_set = set(), set(), set()
    indexed = [fo for fo in folders if fo.get("in_index", True)]
    for fo in indexed:
        fid = str(uuid.uuid4())
        mk, sk = fo["main_key"], fo["sub_key"]
        initialized = bool(mk or sk)
        tags = {"auth": [], "name": [], "category_main": mk, "category_sub": sk,
                "custom": [], "mosaic": None, "others": []}
        if initialized and random.random() < 0.5:
            author = random.choice(AUTHORS)
            tags["auth"] = [author]; auth_set.add(author)
        if mk: main_set.add(mk)
        if sk: sub_set.add(sk)
        index["folders"][fid] = {
            "id": fid, "name": fo["name"], "path": fo["path"], "files": fo["files"],
            "size": fo["size"], "number": fo["number"],
            "initialized": initialized, "tags": tags,
            "favorite": (len(index["folders"]) % 4 == 0),  # ~1/4 marked favorite
        }
    index["metadata"] = {"auth": sorted(auth_set),
                         "category_main": sorted(main_set),
                         "category_sub": sorted(sub_set)}
    with open(os.path.join(index_dir, "manga_index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    unindexed = len(folders) - len(indexed)
    print(f"✓ index → {index_dir}/manga_index.json "
          f"({len(indexed)} in index, {unindexed} left out for refresh to discover)")


def reset_tree():
    if os.path.exists(TEST_ROOT):
        shutil.rmtree(TEST_ROOT); print(f"✓ wiped {TEST_ROOT}")
    os.makedirs(ROOT, exist_ok=True)
    os.makedirs(DELETE_DIR, exist_ok=True)
    # pre-create every main×sub combination directory
    for m in MAIN_CATS:
        for s in SUB_CATS:
            os.makedirs(os.path.join(ROOT, m["path"], s["path"]), exist_ok=True)


def main():
    print(f"Manga Viewer test data — {TOTAL_IN_TREE} in-tree + {TOTAL_LOOSE} loose")
    reset_tree()
    counts, folders = {}, []
    combos = [(m, s) for m in MAIN_CATS for s in SUB_CATS]

    for idx in range(TOTAL_IN_TREE):
        scn = scenario_for(idx)
        counts[scn["kind"]] = counts.get(scn["kind"], 0) + 1
        m, s = combos[idx % len(combos)]
        name = folder_name(idx, scn["kind"])
        fpath = os.path.join(ROOT, m["path"], s["path"], name)
        size, number = populate(fpath, name, scn)
        # Some folders are deliberately left out of the pre-built index so a
        # refresh discovers them (and infers their category from the combo dir).
        in_index = (idx % UNINDEXED_EVERY) != 0
        folders.append({"name": name, "path": fpath, "size": size, "number": number,
                        "files": build_file_list(fpath),
                        "main_key": m["key"], "sub_key": s["key"],
                        "in_index": in_index})
        if (idx + 1) % 30 == 0:
            print(f"  ... {idx + 1}/{TOTAL_IN_TREE} in-tree")

    # loose manga directly under root (NOT in any main/sub combo) — will stay
    # uncategorized and won't be scanned by the combo-based refresh.
    loose_dir = os.path.join(ROOT, "_unsorted")
    os.makedirs(loose_dir, exist_ok=True)
    for j in range(TOTAL_LOOSE):
        name = folder_name(1000 + j, "images")
        fpath = os.path.join(loose_dir, name)
        populate(fpath, name, {"kind": "images", "n": 4})

    write_settings()
    build_index(folders)

    print("\nScenario spread (in-tree):")
    for k, v in sorted(counts.items()):
        print(f"  {k:14s} {v}")
    print(f"\nDone. Root: {ROOT}")
    print("Backend reads settings live; refresh in the UI to rescan.")


if __name__ == "__main__":
    main()
