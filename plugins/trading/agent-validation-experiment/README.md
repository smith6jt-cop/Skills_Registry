# Agent Validation Experiment

**Problem:** Multi-agent training integration caused premature training termination due to Risk Analyst recommending "halt" during early training instability.

**Root Cause:** The Risk Analyst misinterpreted normal early-training metrics (KL ~0.02, temporary 0% consistency) as "catastrophic failure" and triggered halt actions at ~19% training completion.

**Solution:** Add a grace period that converts halt actions to checkpoints during early training (<25%), and update the Risk Analyst prompt with phase-aware guidance.

---

## Implementation

### Grace Period Logic (`multi_agent.py` lines 987-992)

```python
# Grace period: Convert halt to checkpoint in early training (<25%)
training_progress = trainer.global_step / self.trainer.config.total_timesteps
if action.action_type == "halt" and training_progress < 0.25:
    print(f"  [GRACE PERIOD] Converting halt -> checkpoint at {training_progress:.1%} progress")
    action.action_type = "save_checkpoint"
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
| `alpaca_trading/training/multi_agent.py` | Grace period logic (lines 987-992), Risk Analyst prompt (lines 176-223) |
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
