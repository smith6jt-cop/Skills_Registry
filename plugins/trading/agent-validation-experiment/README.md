# Agent Validation Experiment

**Problem (v1.2):** Multi-agent training integration caused premature training termination due to Risk Analyst recommending "halt" during early training instability.

**Problem (v2.0):** Analysis of 90 agent consultations across 10 baseline + 10 treatment runs revealed 7 systemic problems: identical recommendations across runs, agents blind to drawdown quality, Reward Engineer using wrong weights, Risk Analyst fixated on KL, no trade quality analysis.

**Solution (v1.4):** Grace period that converts halt actions to checkpoints during early training (<25%).

**Solution (v2.0):** Comprehensive fix: per-component reward metrics from environment, rewritten agent prompts with correct weights and trade-quality focus, adaptive drawdown threshold, expanded experiment results.

---

## Implementation (v2.0 - Agent Prompt Rewrite + Component Metrics)

### Per-Component Reward Metrics (`vectorized_env.py`)

GPU-resident accumulators track per-component reward means with zero rollout overhead. `get_component_metrics()` returns:
- **component_means / component_weighted**: Raw and weighted contributions for all 8 components
- **action_summary**: HOLD/BUY/SELL percentages
- **position_sizing**: Mean size, std, trades/episode, win rate
- **drawdown**: Current mean/max, observed max, adaptive threshold
- **symbol / current_volatility**: Context for per-run differentiation

### Adaptive Drawdown Threshold (`vectorized_env.py`)

Fixed 15% threshold never triggered (training DD is 0.05-0.72%). Replaced with adaptive:
```python
GPUEnvConfig(
    use_adaptive_drawdown_threshold=True,   # On by default
    adaptive_drawdown_multiplier=2.0,       # Threshold = 2x observed max DD
    adaptive_drawdown_min_threshold=0.01,   # Floor: 1%
)
```

### Agent Prompt Rewrites (`multi_agent.py`)

| Agent | Key Change |
|-------|-----------|
| **Reward Engineer** | Fixed weights to v3.8.0 (pnl=0.40, direction=0.15, dsr=0.10). Added component balance, action distribution, position sizing analysis. |
| **Risk Analyst** | Trade quality PRIMARY, drawdown trajectory SECONDARY, KL TERTIARY (only at 3x target). New `trade_quality`, `drawdown_trajectory` fields. |
| **Hyperparameter Tuner** | Symbol/volatility context. Trade quality drives decisions. New `primary_signal` field. |
| **Orchestrator** | Reward Engineer authority on component balance. Aware of new metric dimensions. |

### Expanded Prompt Template (`multi_agent.py`)

Agent prompts now include 5 new sections: Reward Component Breakdown, Action Distribution, Position Sizing, Drawdown (live), Symbol & Volatility Context.

### Richer Experiment Results (`agent_validation_experiment.py`)

`TrainingResult` now has 12 new fields: 5 reward components, 3 action distribution, 5 position/trade quality metrics. `compute_comparison()` runs statistical tests on all new metrics.

---

## Implementation (v2.1 - Bug Fixes, v3.9.1)

Five bugs found during v2.0 experiment (20 runs, 200M timesteps, +11.6% profit factor p=0.009):

| Bug | Impact | Fix |
|-----|--------|-----|
| ~50% Risk Analyst parse failures | Truncated JSON from `max_tokens=800` | 5-strategy parser + `max_tokens=1500` |
| Grace period → invalid `save_checkpoint` | Action silently fails | Changed to `checkpoint` |
| Unknown action types pass through | `flag_for_review` etc. reach `_apply_action` | `VALID_ACTION_TYPES` + `ACTION_TYPE_ALIASES` |
| Risk Analyst prompt suggests invalid types | Agent returns `save_checkpoint`, `reduce_lr` | Prompt uses `checkpoint`, `adjust_lr` |
| `max_tokens=800` too low | Truncates 8-field JSON responses | Increased to 1500 |

### Action Type Validation (`multi_agent.py`)

```python
VALID_ACTION_TYPES = {"adjust_lr", "adjust_entropy", "checkpoint", "halt", "continue"}

ACTION_TYPE_ALIASES = {
    "save_checkpoint": "checkpoint", "reduce_lr": "adjust_lr",
    "flag_for_review": "checkpoint", "early_stop": "halt", ...  # 13 aliases total
}
```

### Robust JSON Parser (`multi_agent.py`)

5-strategy fallback in `_parse_agent_response()`:
1. Markdown fence extraction (standard)
2. Truncated fence handling (no closing ```)
3. Brace-delimited extraction (text around JSON)
4. Brace balancing for truncated JSON
5. Regex field extraction (last resort, tagged `_parsed_via: "regex_fallback"`)

---

## Implementation (v1.4 - Grace Period)

### Grace Period Logic (`multi_agent.py`)

```python
# Grace period: Convert halt to checkpoint in early training (<25%)
training_progress = trainer.global_step / self.trainer.config.total_timesteps
if action.action_type == "halt" and training_progress < 0.25:
    print(f"  [GRACE PERIOD] Converting halt -> checkpoint at {training_progress:.1%} progress")
    action.action_type = "checkpoint"  # v3.9.1: was "save_checkpoint" (invalid)
    action.params = {"reason": f"[Converted from halt] {action.params.get('reason', 'Early training grace period')}"}
```

### Risk Analyst Prompt Updates

1. **Phase-aware KL divergence targets:**
   - Early (0-30%): <0.025 (exploration phase)
   - Mid (30-70%): <0.020 (stabilization)
   - Late (70%+): <0.015 (refinement)

2. **New guidance section:**
   ```
   5. EARLY TRAINING GRACE PERIOD (Critical)
      - Training < 25%: NEVER recommend halt for poor metrics
      - Early training is inherently unstable - 0% consistency at 20% is NORMAL
      - KL divergence up to 0.025 is acceptable in first 30%
      - Always recommend checkpoint over halt in early phases
   ```

---

## Experiment Configuration

### Production-Length Experiment (200M timesteps)

| Parameter | Standard (Previous) | Production (New) |
|-----------|---------------------|------------------|
| TIMESTEPS | 50,000,000 | **200,000,000** |
| TRAINING_MODE | 'standard' | **'production'** |
| validation_interval | 20 | 40 (auto) |
| Expected updates | ~95 | ~380 |
| Duration per model | ~35 min | ~140 min |

### Quick Validation Test

Before running full experiment, use cell 25 with 10M timesteps to verify:
1. API key detected by trainer
2. Agent consultations > 0
3. Grace period converts halt actions (watch for `[GRACE PERIOD]` messages)

---

## Expected Results After Fix

### Key Success Metrics
1. **All treatment runs complete** (no early halts)
2. **Updates match baseline** (380 vs 380, not 9 vs 380)
3. **Performance comparable or better** than baseline

### Quantitative Expectations
| Metric | Baseline (Expected) | Treatment (Expected) |
|--------|---------------------|----------------------|
| Updates Completed | 380 | 380 |
| Profit Factor | 4-5 | 4-6 (agents may tune LR) |
| Consistency | 100% | 100% |
| Fitness Score | 0.7-0.9 | 0.7-0.95 |

---

## Files Modified

| File | Changes |
|------|---------|
| `alpaca_trading/gpu/vectorized_env.py` | Component tracking accumulators, `get_component_metrics()`, adaptive drawdown config (v2.0) |
| `alpaca_trading/gpu/ppo_trainer_native.py` | Pipe component metrics through validation callback (v2.0) |
| `alpaca_trading/training/multi_agent.py` | Rewritten prompts (4 agents), expanded `_get_current_metrics()`, expanded prompt template (v2.0); Grace period logic (v1.4) |
| `scripts/agent_validation_experiment.py` | Expanded `TrainingResult` (12 new fields), `_extract_component_metrics()`, updated `compute_comparison()` (v2.0) |
| `tests/test_multi_agent.py` | New: 16 tests for prompt correctness, component metrics, adaptive drawdown, metrics flow (v2.0) |
| `notebooks/agent_validation_analysis.ipynb` | TIMESTEPS=200M, TRAINING_MODE='production' (cell 12), test config (cell 25) |

---

## Usage

### Run Full A/B Experiment

```python
# In agent_validation_analysis.ipynb cell 12:
TIMESTEPS = 200_000_000
TRAINING_MODE = 'production'
RUN_BASELINE = True
RUN_TREATMENT = True
```

### Monitor Grace Period

Watch console output during treatment training for:
```
  [GRACE PERIOD] Converting halt -> checkpoint at 15.2% progress
```

This indicates the fix is working - halt actions are being safely converted to checkpoints.

---

## Version History

- **v1.3.0** (2026-01-31): Initial experiment infrastructure, API key fixes
- **v1.4.0** (2026-02-05): Grace period fix, production-length configuration
- **v2.0.0** (2026-02-06): Agent prompt rewrite, per-component metrics, adaptive drawdown, expanded experiment results. Addresses 7 systemic problems found in v1.2 experiment analysis.
- **v2.1.0** (2026-02-07): Bug fixes from v2.0 experiment results (+11.6% PF, p=0.009). Robust JSON parser, action type validation, grace period fix, prompt vocabulary fix, increased max_tokens.
