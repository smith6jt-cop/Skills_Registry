# Skilled Agent Architecture (v5.0.0)

Single tool-augmented Claude agent replacing the 5-specialist multi-agent system for RL training optimization.

**Version:** v5.0.0 (2026-03-02)

## Key Finding

Three A/B experiments (Feb 2026) conclusively showed the multi-agent system provided zero benefit. Root cause: agents lacked genuine skills — just generic LLM prompt-responders observing 6 scalar metrics. The skilled agent replaces 25-33 API calls/run ($2-7) with ~4 tool-augmented consultations (~$0.15) using the Claude Agent SDK.

## Architecture

- 1 skilled agent (Sonnet) with 5 callable tools via `claude-agent-sdk`
- Rule-based autopilot handles 11-12 of 15 validations (no LLM)
- 4 event-based consultations: phase transitions, first pathology, training completion
- Simulate-verify loop: predict → apply → verify → learn (instinct graduation)
- Prompt evolution: 8 learnable parameters optimized numerically after each run

## New Files

- `training/skilled_agent.py` (~1100 lines) — Core trainer
- `training/agent_tools.py` (~550 lines) — 5 callable tools + MCP server
- `training/knowledge_base.py` (~250 lines) — Prediction tracking, graduation
- `training/prompt_evolution.py` (~300 lines) — Learnable prompt parameters

See `skills/skilled-agent-v500/SKILL.md` for full documentation.
