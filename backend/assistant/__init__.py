"""
Assistant Tool

A ChatGPT-style AI assistant backed by Claude. Uses a small Haiku call to
classify prompt complexity, then routes to Haiku / Sonnet / Opus for the
actual answer. Conversation history is persisted in SQLite.
"""
