# Agent Validation Experiment

A/B testing infrastructure for validating Claude agent integration in RL training.

**Version:** v3.0 (2026-02-18)

## Key Finding (v2.4)

Agents HURT performance: Fitness -38.2%, PF -6.3%. Root causes: compounding entropy increases, misdiagnosis of normal PPO dynamics, LR adjustments are silent no-ops.

## v3.0 Guardrails ("Primum Non Nocere")

- Phase gates (no intervention before 30%, entropy decrease only after 50%)
- Cumulative entropy bounds [0.5x, 1.5x]
- Fitness-gated checkpoints with rollback
- LR adjustments disabled (cosine scheduler overwrites them)
- Institutional knowledge injection (5 lessons from v2.4)
- Agent memory persistence (`agent_memory.py`) for cross-run learning
- Reward Engineer is read-only diagnostic
- Reduced consultation intervals (hyperparam 8, risk 5, reward 15)
- Welch's t-test + Bonferroni correction for statistical analysis

See `skills/agent-validation-experiment/SKILL.md` for full documentation.

## Version History

- **v1.3-v1.4**: Initial infrastructure, grace period fix
- **v2.0**: Agent prompt rewrite, per-component metrics, adaptive drawdown
- **v2.1**: Robust JSON parser, action type validation, max_tokens fix
- **v2.2**: API key parsing fix, quick validation speed
- **v2.3**: Compute cost reduction (580 CU → ~70-95 CU)
- **v2.4**: Pre-computed observation windows (7K→15-25K FPS)
- **v3.0**: Guardrails overhaul (phase gates, cumulative bounds, rollback, memory, institutional knowledge)
