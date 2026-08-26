"""
Knowledge Base config
"""
from pathlib import Path

# Embedding model — multilingual, 500 MB, fast, decent CJK support.
# Swap for `BAAI/bge-m3` or `bge-small-zh` if quality is not enough.
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Text chunking
CHUNK_SIZE_CHARS = 800
CHUNK_OVERLAP_CHARS = 120

# Retrieval
DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.30   # cosine similarity threshold; lower = looser

# File type routing
SUPPORTED_TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".org"}
SUPPORTED_CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".java",
                      ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
                      ".sh", ".yaml", ".yml", ".json", ".toml"}
SUPPORTED_PDF_EXT = {".pdf"}

# Files bigger than this are skipped (they'd blow up the chunker).
MAX_FILE_BYTES = 5 * 1024 * 1024   # 5 MB
