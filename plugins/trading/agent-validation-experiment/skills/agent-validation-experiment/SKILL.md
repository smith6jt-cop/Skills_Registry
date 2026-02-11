---
name: agent-validation-experiment
description: "A/B testing infrastructure for validating Claude agent integration in RL training. Trigger when: (1) planning agent validation, (2) analyzing agent effectiveness, (3) deciding whether to enable agents, (4) understanding agent cost-benefit, (5) reviewing agent prompt design, (6) debugging agent response parsing, (7) notebook API key loading issues."
author: Claude Code
date: 2026-02-10
version: v2.2
---

# Agent Validation Experiment

## Overview

| Item | Details |
|------|---------|
| **Date** | 2026-02-10 |
| **Goal** | Determine if Claude agent integration improves model predictive power |
| **Status** | v1.0 failed (zero consultations), v1.1 failed (missing directories), v1.2 ran (90 consultations analyzed), v2.0 systemic fixes deployed, v2.1 bug fixes from experiment results (+11.6% PF, p=0.009), **v2.2 notebook key parsing fix + quick validation speed fix** |
| **Files** | `scripts/agent_validation_experiment.py`, `notebooks/agent_validation_analysis.ipynb`, `alpaca_trading/training/multi_agent.py`, `alpaca_trading/gpu/vectorized_env.py`, `tests/test_multi_agent.py` |

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

## What Agents Actually Do (v2.0)

### During Training
1. **Hyperparameter Tuner** (every 5 validations)
   - PRIMARY: Analyzes trade quality (win rate, profit factor) to drive LR/entropy decisions
   - SECONDARY: Checks action distribution (>70% HOLD -> increase entropy)
   - TERTIARY: KL divergence (only intervene at 3x target)
   - Receives symbol name and GARCH volatility for per-run differentiation
   - Bounds: LR 0.1x-3.0x, Entropy 0.1x-5.0x

2. **Risk Analyst** (every 3 validations)
   - PRIMARY: Trade quality trajectory (win rate, profit factor, reward-to-risk trends)
   - SECONDARY: Drawdown trajectory (improving/stable/worsening)
   - TERTIARY: KL divergence (only at 3x target for 3+ consecutive validations)
   - Returns `trade_quality` and `drawdown_trajectory` assessments
   - Can recommend checkpoint saves or training halt

3. **Reward Engineer** (every 10 validations)
   - Analyzes per-component reward balance (P&L should dominate at 40%)
   - Checks for component gaming (e.g., direction >> P&L = predicts but doesn't profit)
   - Evaluates action distribution (40-60% HOLD target for hourly trading)
   - Assesses position sizing health (varied sizes = good, fixed = bad)
   - Returns `dominant_component`, `component_balance`, `action_distribution_health`, `position_sizing_health`

### v1.2 Analysis Findings (90 consultations)

| Problem | Evidence | Impact |
|---------|----------|--------|
| Identical recommendations | All 10 HP tuner at 31.5% gave `lr_mult=0.7, entropy_mult=1.3` | No per-run value |
| Agents blind to drawdown | Training DD 0.05-0.72%; 15% threshold never triggers | No DD learning |
| Wrong weights in prompt | RE showed `direction: 0.40, pnl: 0.10` (v2.5.0) | Wrong analysis |
| KL fixation | ~90% of RA flags cite KL | PPO already manages KL |
| No trade quality analysis | Win rate, position sizing never discussed | Missing key signals |

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

## Failed Attempts

| Attempt | Date | What Happened | Root Cause | Fix |
|---------|------|--------------|------------|-----|
| v1.0 | 2026-02-01 | Zero agent consultations across all 10 treatment runs. Treatment results were byte-for-byte identical to baseline. | **validation_interval mismatch**: With 50M timesteps, `n_envs=1024`, `n_steps=512`, only ~95 updates occurred. With `validation_interval=20`, only 4-5 validation cycles happened. Agent intervals (3, 5, 10) rarely aligned with these few cycles. | `train_with_guidance()` now auto-adjusts `validation_interval` to ensure ≥15 validation cycles. Added diagnostic logging to track callback invocations. |
| v1.1 | 2026-02-04 | Agent consultations now working, but "Parent directory checkpoints does not exist" error during checkpoint action. Training continued but agent-triggered checkpoints failed silently. | **Missing directory creation**: (1) `_apply_action()` wrote to `checkpoints/agent_triggered_{step}.pt` without creating directory. (2) `save_agent_logs()` wrote to filepath without ensuring parent exists. | Added `os.makedirs(os.path.dirname(path), exist_ok=True)` before both save operations in `multi_agent.py` (lines 589 and 1086-1088). |
| v1.2 | 2026-02-05 | 90 consultations analyzed. All HP tuner recommendations identical (`lr=0.7, ent=1.3`). Risk Analyst fixated on KL. Reward Engineer using v2.5.0 weights. No agents analyzed trade quality. Drawdown penalty inactive (15% threshold never triggered). | **7 systemic problems**: (1) No per-run context (symbol/volatility), (2) Fixed DD threshold useless, (3) No component breakdown visible, (4) KL over-emphasized, (5) Wrong weights in RE prompt, (6) No position sizing analysis, (7) Grace period untested. | v2.0: Rewritten prompts, per-component metrics pipeline, adaptive drawdown, expanded TrainingResult. 16 new tests. |
| v2.0 | 2026-02-07 | Experiment showed +11.6% profit factor (p=0.009) but 5 bugs degraded agent effectiveness: ~50% Risk Analyst parse failures, grace period produced invalid action type, orchestrator passed unknown action types, Risk Analyst prompt suggested invalid types, max_tokens too low. | **5 code bugs**: (1) `max_tokens=800` truncates 8-field JSON, (2) grace period converts to `save_checkpoint` (invalid), (3) no action type validation, (4) prompt vocabulary uses non-canonical types, (5) parser has no truncation recovery. | v2.1: 5-strategy JSON parser, `VALID_ACTION_TYPES` + `ACTION_TYPE_ALIASES`, grace period→`checkpoint`, prompt vocabulary fix, max_tokens→1500. 17 new tests. |
| v2.1 | 2026-02-10 | Notebook gap-fill fails with 401 Authorization Required. Quick validation takes >10 min instead of ~5 min. | **2 bugs**: (1) Cell 10 parsed API key file with naive `lines[0]`/`lines[1]` — file has `Key:` and `Secret:` labels on their own lines, so `APCA_API_KEY_ID="Key:"` was sent to Alpaca. (2) Quick validation used 10M timesteps + validation_interval=3 + max_consultations=10 → 76 updates, 25 validations, 10+ API calls. | v2.2 (notebook v1.5.0): Use `_read_keys_from_file()` from broker module. Reduce to 2M timesteps, validation_interval=5, max_consultations=5. |

### v2.1 Failure Details (2026-02-10)

**Symptoms (API key parsing):**
- Gap-fill for AAPL and GOOGL returns `401 Authorization Required` HTML from nginx
- Log shows `Alpaca API keys loaded from environment variables` (keys exist but wrong values)
- Cache falls back to 11-day-old data (no gap-fill)

**Root Cause:**
The API key file (`config/API_key_500Paper.txt`) has a labeled format:
```
Key:
PKTH...JLH2
Secret:
EsNf...6kbw
```
Cell 10 read it as `lines = [line for line if line.strip()]`, producing `["Key:", "PKTH...", "Secret:", "EsNf..."]`. Then `lines[0]="Key:"` was set as `APCA_API_KEY_ID` and `lines[1]="PKTH..."` (the actual key) as `APCA_API_SECRET_KEY`. Alpaca rejected "Key:" as an API key ID → 401.

**Fix:** Use `_read_keys_from_file()` from `alpaca_trading.trading.broker` which handles `Key:` / `Secret:` labels, `KEY=VALUE`, and `KEY: VALUE` formats correctly.

**Symptoms (slow quick validation):**
- 10M timesteps with batch_size=131K → 76 updates
- validation_interval=3 → ~25 validations
- Each validation potentially triggers agent API calls (~10-20s each)
- max_consultations=10 allowed up to 10 Claude API roundtrips

**Fix:** Reduce to 2M timesteps (15 updates), validation_interval=5 (3 validations), max_consultations=5. Target ~3 min.

### v2.0 Failure Details (2026-02-07)

**Experiment Results (statistically significant improvement despite bugs):**
- +11.6% profit factor (p=0.009)
- 20 runs, 200M timesteps each, A100 GPU

**5 Bugs Found:**
1. **~50% parse failures**: Risk Analyst's 8-field JSON with reasoning regularly exceeds 800 tokens. Response truncated before closing `}`, `json.loads()` fails, returns `{"error": "Failed to parse response"}`.
2. **Invalid grace period type**: `halt → save_checkpoint` — but `_apply_action()` only handles `checkpoint`, so the action falls through to "Unknown action type" and does nothing.
3. **Unknown action types pass through**: Orchestrator creates `TrainingAction(action_type="flag_for_review")` from LLM output. `_apply_action()` returns "Unknown action type" but the action is silently ignored.
4. **Prompt vocabulary mismatch**: Risk Analyst prompt says `"recommendation": "continue|save_checkpoint|halt|reduce_lr"` — two of those (`save_checkpoint`, `reduce_lr`) are not canonical types.
5. **Root cause of #1**: `max_tokens=800` for agent consultations, `max_tokens=1000` for orchestrator. Risk Analyst's response with 8 fields + detailed reasoning regularly needs 1200+ tokens.

### v1.1 Failure Details (2026-02-04)

**Symptoms:**
- Error message: `⚠️ Agent consultation error: Parent directory checkpoints does not exist.`
- Training continued (error caught in callback exception handler)
- Agent-triggered checkpoints not saved
- Risk analyst halted Treatment 1/10 early due to "zero fitness collapse"
- Consultations happening but actions failing silently

**The Code That Broke It:**
```python
# multi_agent.py line 588 (BEFORE fix)
elif action.action_type == "checkpoint":
    checkpoint_path = f"checkpoints/agent_triggered_{self.trainer.global_step}.pt"
    self.trainer.save(checkpoint_path)  # FAILS - checkpoints/ doesn't exist in Colab
```

**Why It Wasn't Caught Earlier:**
1. Exception handler at line 987 catches all errors and logs them as warnings
2. Training continues after error - doesn't fail visibly
3. Quick validation test (cell 25) doesn't trigger checkpoint actions
4. Risk analyst triggered `halt` action on first run, masking the checkpoint issue

**Files Modified:**
- `alpaca_trading/training/multi_agent.py`:
  - Line 589: Added `os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)`
  - Lines 1086-1088: Added parent directory creation before `save_agent_logs()`

### v1.0 Failure Details (2026-02-01)

**Symptoms:**
- All treatment runs showed `agent_consultations: 0`, `agent_actions_taken: 0`
- Agent config files had empty arrays: `"consultations": [], "decisions": []`
- Treatment metrics were identical to baseline (same seeds, no agent interventions)

**The Math That Broke It:**
```
Steps per update: 1024 * 512 = 524,288
Total updates: 50M / 524,288 ≈ 95 updates
Validation interval: 20 (from get_auto_config('standard'))
Validation cycles: 95 / 20 ≈ 4-5 cycles

Agent intervals:
- Risk Analyst: every 3rd cycle → triggers at cycle 3
- Hyperparameter Tuner: every 5th cycle → triggers at cycle 5
- Reward Engineer: every 10th cycle → never triggers with only 4-5 cycles
```

**Why Treatment == Baseline:**
1. Same random seeds used
2. No agents consulted → no hyperparameter changes
3. Deterministic training with identical conditions

## Failed Attempts (Predicted)

| Attempt | Why It Might Fail | Mitigation |
|---------|-------------------|------------|
| Using same seed for both groups | Random seed doesn't guarantee identical training | Use multiple seeds, compare distributions |
| Too few samples | High variance in training outcomes | Minimum 10 runs per group |
| Different symbols per group | Symbol difficulty varies | Match symbols exactly |
| Agent costs explode | Runaway consultations | Max 50 consultations/run |
| Silent file I/O failures | Colab working directory differs from expected, directories don't exist | Always use `os.makedirs(parent, exist_ok=True)` before any file write |
| Risk analyst too aggressive | Halts training early on normal early-training volatility | Grace period (v1.4) + KL de-emphasized to tertiary (v2.0) |
| Agents give same advice to every run | No per-run context, same static prompt | Symbol/volatility context + per-component metrics (v2.0) |
| Wrong reward weights in prompts | Prompts out of date with code | Tests verify prompt weights match code (v2.0: `test_multi_agent.py`) |

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

- `scripts/agent_validation_experiment.py` - Experiment runner (v2.0: expanded TrainingResult)
- `notebooks/agent_validation_analysis.ipynb` - Statistical analysis
- `alpaca_trading/training/multi_agent.py` - Agent integration code (v2.0: rewritten prompts; v2.1: robust parser, action validation, max_tokens)
- `alpaca_trading/gpu/vectorized_env.py` - Component metrics + adaptive drawdown (v2.0)
- `alpaca_trading/gpu/ppo_trainer_native.py` - Metrics pipeline (v2.0)
- `tests/test_multi_agent.py` - 33 tests: prompt correctness, metrics flow, adaptive drawdown (v2.0), parser robustness, action validation, grace period (v2.1)
- `.skills/plugins/trading/multi-agent-integration/` - Integration documentation
