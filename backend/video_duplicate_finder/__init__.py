"""
Video Duplicate Finder
======================

Standalone tool for finding and managing duplicate VIDEO files via perceptual
hashing of N evenly-spaced frames.

This package is **completely decoupled** from `duplicate_finder` (the image-
based sibling). Code may not be cross-imported between the two.
See `buffer/PROGRESS.md` D-11 for the decoupling contract.

Architecture:
    See buffer/01_architecture.md (image version reference)
    See buffer/04_image_to_video_mapping.md (video-specific design decisions)

Workflow stages (mirrors duplicate_finder):
    Phase 1   /phase1/refresh         scan FS, compute N-frame phash signatures
    Phase 2   /phase2/build           pairwise hamming-aligned distance, write edges
    Phase 2.5 /phase2.5/materialize   BFS connected components into duplicate groups
    Phase 3   /phase3/get-duplicates  paginated read of materialized groups
    Compare   /compare-folders       scoped re-comparison (no deletes)
"""
