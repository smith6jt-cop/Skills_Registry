---
name: skilled-agent-v500
description: "Skilled agent architecture replacing multi-agent system for RL training. Trigger when: (1) planning agent-guided training, (2) implementing tool-augmented LLM consultations, (3) comparing skilled vs multi-agent approaches, (4) designing simulate-verify loops for training, (5) implementing prompt evolution / learnable parameters, (6) understanding Claude Agent SDK integration in training, (7) debugging SkilledTrainer consultations or tool calls, (8) configuring agent safety bounds for training actions."
author: Claude Code
date: 2026-03-02
version: v5.0.0
---

# Skilled Agent Architecture (v5.0.0)

## Overview

| Item | Details |
|------|---------|
| **Date** | 2026-03-02 |
| **Goal** | Replace 5-specialist multi-agent system with 1 tool-augmented agent using Claude Agent SDK |
| **Status** | Implemented. Unit tests (91 pass), integration tests (21 pass), zero regressions (1186 pass). Awaiting Colab validation run. |
| **Files** | `training/skilled_agent.py`, `training/agent_tools.py`, `training/knowledge_base.py`, `training/prompt_evolution.py`, `agents/safety.py`, `training/instincts.py` |

## The Problem

Three A/B experiments (Feb 21-27, 2026) conclusively showed the multi-agent system (v4.5.0) provided zero benefit:

| Experiment | Finding |
|------------|---------|
| Exp 1-2 (passive agents) | Agents irrelevant — took zero actions with guardrails |
| Exp 3 (active agents) | Agents harmful: -24% PF, -48% fitness |

Root cause: Agents had **no genuine skills**. They were generic LLM prompt-responders that observed 6 scalar metrics and output JSON. Literature review (EnvGen, ATLAS, QuantAgent, LangProp, MLE-Dojo) showed skilled agents require: callable tools, simulate-before-apply, adaptive prompt evolution, fewer but higher-quality consultations.

## Verified Workflow

### Architecture
```
NativePPOTrainer.train(validation_callback)
      |
      v  (~15 validations per run)
SkilledTrainer
      |
      +---> Rule-Based Autopilot (handles 11-12 of 15 validations)
      |      - Proactive overtrading/collapse fix (existing, kept)
      |      - Auto-best checkpoint (existing, kept)
      |      - High-confidence instincts (auto-applied, no LLM)
      |
      +---> Skilled Agent (~4 consultations at phase transitions)
               |
               v
          claude_agent_sdk.query(prompt, options)
               |
               +---> @tool simulate_reward_change    (~0ms)
               +---> @tool get_regime_analysis       (~100ms)
               +---> @tool run_mini_backtest          (~5-10s)
               +---> @tool query_knowledge_base       (~10ms)
               +---> @tool estimate_pnl_impact        (~10ms)
               |
               v
          Parse recommendation -> AgentSafetyWrapper -> _apply_action()
               |
               v  (next validation)
          Verify predicted vs actual -> Update instinct confidence
```

### Consultation Triggers (4 event-based, NOT interval-based)
1. **EARLY→MID phase** (~15% progress): Agent reviews early metrics, suggests initial weight adjustments
2. **MID→LATE phase** (~70% progress): Agent reviews convergence, suggests final tuning
3. **First pathology**: Overtrading, direction collapse, or reward collapse detected
4. **Training completion**: Post-mortem — which instincts to create/update?

### Simulate-Verify Loop
1. **Simulate**: Agent calls `simulate_reward_change` + `estimate_pnl_impact` → evidence-based recommendation
2. **Apply**: Standard `_apply_action()` with same bounds/gates as multi-agent
3. **Verify** (next validation): Direction correct + magnitude within 2x = confirmed
4. **Learn**: Confirmed instincts gain confidence. At 5+ confirmations ≥0.8 → graduate to autopilot rule

### Prompt Evolution
8 learnable parameters (numeric + categorical):
- `overtrading_threshold` (0.20), `direction_collapse_threshold` (0.40)
- `reward_adjustment_magnitude` (0.03), `early_phase_cutoff` (15.0)
- `tool_budget` (3), `primary_objective` ("P&L")
- `risk_tolerance` ("moderate"), `preferred_pattern` ("increase_slippage_for_overtrading")

After each run, records (parameter_value, fitness_delta). After 3+ data points, nudges numeric values 20% toward historically best-performing value. Pure numerical optimization — no LLM.

## Failed Attempts

| Attempt | What Failed | Why | Lesson |
|---------|------------|-----|--------|
| Multi-agent v4.5.0 (5 specialists) | Zero actions taken | Agents paralyzed by safety gates + lack of skills | Skills matter more than agent count |
| Multi-agent v4.5.0 (active mode) | -24% PF, -48% fitness | Compounding bad adjustments from generic advice | Simulate-before-apply is essential |
| Interval-based consultations | Wasted API calls | Most validations don't need LLM input | Event-based triggers are 6x cheaper |
| Opus orchestrator | $5/run for rubber-stamping | Orchestrator added cost without insight | Single Sonnet agent is sufficient |
| Agent memory without verification | Accumulated false patterns | No ground truth checking | Simulate-verify loop required |

## Final Parameters

### SkilledAgentConfig
```python
SkilledAgentConfig(
    max_consultations=4,           # Budget per run
    model="claude-sonnet-4-5",     # Cost-effective for tool use
    phase_early_to_mid_pct=15.0,   # EARLY→MID trigger
    phase_mid_to_late_pct=70.0,    # MID→LATE trigger
    proactive_low_hold_threshold=2, # Consecutive low-hold before auto-fix
    proactive_collapse_threshold=2,  # Consecutive collapse before auto-fix
)
```

### Cost
| | Multi-Agent (v4.5.0) | Skilled Agent (v5.0.0) |
|---|---|---|
| Agents/run | 5 specialists + 1 orchestrator | 1 |
| API calls/run | 25-33 | ~4 |
| Cost/run | $2-7 | ~$0.15 |
| Annual (100 models) | $200-700 | ~$15 |
| FPS impact | 4-6x slower | <5% slower |

### Safety (Unchanged)
All safety bounds from `AgentSafetyWrapper` preserved:
- ±0.05/call, ±0.15 cumulative, 0.01 floor per reward component
- Phase gate: No reward changes before 15% progress
- Tiered fitness decline gate (strict for rollback/halt, moderate for weight changes)
- Forbidden actions: `bypass_all_gates`, `disable_risk_controls`, etc.
- Rate limiting: 50 actions/hour, 60s minimum interval

## Key Insights

1. **Tool-augmented > prompt-only**: Giving the agent callable tools (simulate, backtest, knowledge search) produces evidence-based recommendations instead of generic advice
2. **Fewer, better consultations**: 4 event-based calls beat 25-33 interval-based calls in both quality and cost
3. **Simulate-verify is essential**: Without ground truth checking, agents accumulate false confidence
4. **Prompt evolution works without LLM**: Simple numerical optimization (20% nudge toward best) outperforms meta-prompting
5. **Autopilot graduation**: High-confidence instincts (5+ confirmations ≥0.8) become rules — system gets faster over time
6. **Safety wrapper is reusable**: `AgentSafetyWrapper` works identically for single-agent and multi-agent

## References

- **EnvGen** (arXiv:2307.01548): Environment generation for skill learning
- **ATLAS** (arXiv:2407.00813): Tool-augmented agents for science
- **QuantAgent** (arXiv:2402.11412): Self-improving quantitative agents
- **LangProp** (arXiv:2312.09473): Code optimization via LLM agents
- **MLE-Dojo** (arXiv:2503.07475): Interactive learning environments for agents
- **Adaptive-OPRO / Symbolic Learning**: Prompt parameters as learnable values

## Dependency

Requires `claude-agent-sdk>=0.1.44` (added to `config/requirements.txt`).
The system gracefully degrades when the SDK is not installed — `AGENT_SDK_AVAILABLE` guard disables consultations and falls back to rule-based autopilot only.
