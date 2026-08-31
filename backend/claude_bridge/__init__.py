"""Claude Bridge — remote Claude Code agent, driven by claude-agent-sdk.

Exposes a real Claude Code session (multi-turn, streaming, tool use, approvals)
over HTTP + WebSocket so a phone client can talk to Claude running on this Mac.
See .claude/plans/humming-noodling-riddle.md for the full design.
"""
