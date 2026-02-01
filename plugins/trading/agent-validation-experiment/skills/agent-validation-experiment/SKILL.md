---
name: agent-validation-experiment
description: "A/B testing infrastructure for validating Claude agent integration in RL training. Trigger when: (1) planning agent validation, (2) analyzing agent effectiveness, (3) deciding whether to enable agents, (4) understanding agent cost-benefit."
author: Claude Code
date: 2025-01-31
version: v1.0
---

# Agent Validation Experiment

## Overview

| Item | Details |
|------|---------|
| **Date** | 2025-01-31 |
| **Goal** | Determine if Claude agent integration improves model predictive power |
| **Status** | Infrastructure ready - awaiting experiment execution |
| **Files** | `scripts/agent_validation_experiment.py`, `notebooks/agent_validation_analysis.ipynb` |

## The Question

**Does integrating Claude agents during RL training provide measurable improvement to model quality?**

The codebase has ~4,744 lines of agent integration code. Before relying on it:
1. We need empirical evidence that agents help
2. We need to quantify the cost-benefit tradeoff

## Experimental Design

### A/B Test Protocol

| Group | Description | Agent Integration |
|-------|-------------|-------------------|
| **Baseline (Control)** | Standard NativePPOTrainer | None |
| **Treatment** | MultiAgentTrainer with agents | Hyperparameter Tuner, Risk Analyst, Reward Engineer |

### Matching Protocol
- Same symbols in both groups
- Same random seeds for reproducibility
- Same training timesteps (50M recommended)
- Same environment configuration (v3.3.0)

### Sample Size
- Minimum: 10 runs per group (2 symbols x 5 seeds)
- Recommended: 20 runs per group (4 symbols x 5 seeds)
- Statistical power: 80% to detect Cohen's d = 0.8

## Success Criteria

| Metric | Minimum Improvement | Statistical Significance |
|--------|---------------------|--------------------------|
| Profit Factor | +0.2 (e.g., 1.5 → 1.7) | p < 0.05 |
| Sharpe/Reward-to-Risk | +0.1 | p < 0.05 |
| Max Drawdown | -2% (e.g., 12% → 10%) | p < 0.10 |
| Consistency | +3% (e.g., 62% → 65%) | p < 0.05 |

### Decision Matrix

| Result | Action |
|--------|--------|
| 2+ metrics significantly improved | Activate agents in production |
| 1 metric improved, others neutral | Use agents in advisory mode only |
| No significant improvement | Disable agents, save ~$350/year |
| Performance degraded | Do NOT use agents |

## Running the Experiment

### Prerequisites
1. Google Colab with A100 GPU
2. `ANTHROPIC_API_KEY` environment variable set
3. Alpaca API credentials configured
4. Pre-cached market data in Google Drive

### Execution (Colab)

```python
# In training.ipynb or separate Colab notebook

# 1. Setup
import os
os.environ['ANTHROPIC_API_KEY'] = 'your-key-here'

# 2. Run experiment
from scripts.agent_validation_experiment import run_validation_experiment

results = run_validation_experiment(
    symbols=["AAPL", "GOOGL", "MSFT", "NVDA"],  # 4 symbols
    n_seeds=5,                                    # 5 seeds each
    timesteps=50_000_000,                         # 50M timesteps
    cache_dir='/content/drive/MyDrive/Colab_Projects/training_data',
    output_dir='/content/drive/MyDrive/Colab_Projects/agent_validation',
    keys_file='/content/Alpaca_trading/config/API_key.txt',
)

# 3. Results saved to Google Drive automatically
```

### Analysis

```python
# Open notebooks/agent_validation_analysis.ipynb
# or run analysis cells in the experiment output
```

## Resource Requirements

| Resource | Estimate |
|----------|----------|
| Training runs | 40 (20 baseline + 20 treatment) |
| Compute time | ~20-40 hours on A100 |
| API costs | ~$70 (20 treatment runs x $3.50/run) |
| Storage | ~500 MB (models + logs) |

## Cost Analysis

### Agent API Costs (per training run)
| Agent | Model | Est. Cost |
|-------|-------|-----------|
| Orchestrator | Opus | ~$1.50 |
| Hyperparameter Tuner | Sonnet | ~$0.60 |
| Risk Analyst | Sonnet | ~$0.90 |
| Reward Engineer | Sonnet | ~$0.30 |
| Data Monitor (disabled) | Haiku | ~$0.10 |
| **Total/run** | - | **~$3.50** |

### Annual Cost Projection
- 100 training runs/year: ~$350
- 200 training runs/year: ~$700

### Break-even Analysis
If agents improve Sharpe by 0.1:
- Worth approximately 1% additional annual return
- On $100k portfolio: $1,000/year value
- ROI: 3x on $350 investment

## What Agents Actually Do

### During Training
1. **Hyperparameter Tuner** (every 5 validations)
   - Monitors learning rate, entropy coefficient
   - Recommends adjustments based on loss trends
   - Bounds: LR 0.1x-3.0x, Entropy 0.1x-5.0x

2. **Risk Analyst** (every 3 validations)
   - Tracks max drawdown proxy metric
   - Detects overfitting (validation declining while loss decreases)
   - Can recommend checkpoint saves or training halt

3. **Reward Engineer** (every 10 validations)
   - Analyzes reward distribution (mean, std, skew, kurtosis)
   - Detects HOLD bias (>60% HOLD actions)
   - Flags reward collapse (std < 1e-6)

### Limitations
- Claude has **no memory across training runs** - cannot learn what worked
- Consultations are **rate-limited** (100/run) - cannot react to every update
- Recommendations are **generic RL knowledge** - may not apply to this specific system
- **Latency**: By the time Claude sees a problem, thousands of updates have occurred

## Why Results Are Uncertain

### Fundamental Concerns
1. **LLMs don't learn from feedback** - Each consultation is independent
2. **Generic vs. specific knowledge** - Claude knows RL, but not this specific reward structure
3. **Reaction latency** - PPO updates at 50,000+ FPS, consultations every ~1000 updates
4. **No counterfactual** - Can't run same training with and without agents simultaneously

### What Claude *Can* Do Well
1. Pattern recognition in metrics (reward collapse, HOLD bias)
2. Safety guardrails (veto authority, bounds enforcement)
3. Documentation/audit trail for post-training analysis

## Failed Attempts (Predicted)

| Attempt | Why It Might Fail | Mitigation |
|---------|-------------------|------------|
| Using same seed for both groups | Random seed doesn't guarantee identical training | Use multiple seeds, compare distributions |
| Too few samples | High variance in training outcomes | Minimum 10 runs per group |
| Different symbols per group | Symbol difficulty varies | Match symbols exactly |
| Agent costs explode | Runaway consultations | Max 50 consultations/run |

## Key Principles

1. **Validate before activating** - Don't assume agents help
2. **Match configurations exactly** - Only difference is agent presence
3. **Multiple seeds required** - Single comparison is meaningless
4. **Statistical tests required** - "Looks better" is not evidence
5. **Cost-benefit matters** - Improvement must justify $350+/year

## Results (To Be Completed After Experiment)

### Experiment Run: [DATE]

| Metric | Baseline Mean | Treatment Mean | Diff | p-value | Significant |
|--------|---------------|----------------|------|---------|-------------|
| Profit Factor | - | - | - | - | - |
| Consistency | - | - | - | - | - |
| Max Drawdown | - | - | - | - | - |
| Fitness Score | - | - | - | - | - |

### Recommendation: [TO BE DETERMINED]

## References

- `scripts/agent_validation_experiment.py` - Experiment runner
- `notebooks/agent_validation_analysis.ipynb` - Statistical analysis
- `alpaca_trading/training/multi_agent.py` - Agent integration code
- `.skills/plugins/trading/multi-agent-integration/` - Integration documentation
