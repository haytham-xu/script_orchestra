"""
Knowledge Base sub-module.

Registers local folders as sources, scans them for md/txt/pdf files,
chunks their text, generates local sentence-transformer embeddings, and
serves top-K semantic retrieval for the chat pipeline.

All models and indexes live under this module — nothing outside knows
how the retrieval works, only that it takes a query string and returns
a list of scored chunks.
"""
