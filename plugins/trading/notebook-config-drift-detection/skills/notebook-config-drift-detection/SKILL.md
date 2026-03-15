---
name: notebook-config-drift-detection
description: "Detect and fix config drift between Colab notebooks and GPUEnvConfig defaults. Triggers when: (1) reviewing notebooks before training, (2) updating vectorized_env.py defaults, (3) preparing A/B experiments, (4) debugging unexpected training behavior."
author: smith6jt
date: 2026-02-21
---

# notebook-config-drift-detection — Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-21 |
| **Goal** | Detect and fix config parameter drift between Colab notebooks and codebase defaults |
| **Environment** | Windows 10, Alpaca Trading v4.1.0, Google Colab (A100) |
| **Status** | Success |

## Context
When `GPUEnvConfig` defaults change in `vectorized_env.py`, Colab notebooks that hardcode those values become stale. This is invisible during training (no error is raised) but invalidates A/B comparisons and produces models trained with unintended parameters.

In v4.1.0, `slippage_weight` changed from 0.04 to 0.06, but all three notebooks (`training.ipynb`, `agent_validation_analysis.ipynb`, `agent_validation_runpod.ipynb`) still had 0.04. Additionally, the RunPod agent validation notebook was missing `symbol=symbol` in `MultiAgentConfig`, silently disabling agent memory persistence.

## Verified Workflow

### 1. Identify source of truth
```bash
# The canonical defaults are in vectorized_env.py
grep -n "slippage_weight" alpaca_trading/gpu/vectorized_env.py
# Look for the dataclass field default: slippage_weight: float = 0.06
```

### 2. Check all notebooks for drift
```python
import json

PARAMS_TO_CHECK = {
    'slippage_weight': 0.06,   # v4.1.0 default
    'n_actions': 8,            # v4.0.0 default
    'dsr_weight': 0.10,        # v3.8.0 default
}

for nb_path in ['notebooks/training.ipynb',
                'notebooks/agent_validation_analysis.ipynb',
                'notebooks/agent_validation_runpod.ipynb']:
    with open(nb_path) as f:
        nb = json.load(f)
    for cell in nb['cells']:
        source = ''.join(cell['source'])
        for param, expected in PARAMS_TO_CHECK.items():
            if f'{param}=' in source:
                # Extract actual value and compare
                pass
```

### 3. Check MultiAgentConfig has symbol set
```python
# In treatment function, verify:
agent_config = MultiAgentConfig(
    symbol=symbol,  # REQUIRED for _save_run_summary() to persist
    ...
)
# Without symbol, _save_run_summary() exits early at line 1540:
# if self._agent_memory is None or not self.config.symbol: return
```

### 4. Fix and validate
```python
# After fixing, verify with:
import json
with open('notebooks/agent_validation_analysis.ipynb') as f:
    nb = json.load(f)
src = ''.join(nb['cells'][20]['source'])  # cell 20 = env_config
assert 'slippage_weight=0.06' in src
assert 'slippage_weight=0.04' not in src
```

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Inline Python verification via Bash on Windows | Special characters (`'` inside `"`) cause quoting hell in Windows bash | Write a temp .py script file and run it instead |
| Relying on notebook version headers | Headers said v1.5.0 but actual config values were stale | Always check the actual parameter values, not just version strings |
| Assuming all notebooks have same config | RunPod had missing `symbol=symbol`, Colab already had it | Check each notebook independently |
| Documenting per-TF env_config in skill but not in notebook | v5.2.0 `multi-timeframe-training` skill had correct `dataclass_replace()` pattern, but notebook cells still used bare `env_config` | Always verify notebook cells match skill documentation after codebase changes (v5.2.1 fix) |

## Final Parameters
```yaml
# Parameters to audit in every notebook before training:
slippage_weight: 0.06       # vectorized_env.py default
n_actions: 8                # v4.0.0+
dsr_weight: 0.10            # v3.8.0+
use_curriculum_reward: true  # v4.0.0+
use_adaptive_drawdown_threshold: true  # v3.9.0+

# MultiAgentConfig (treatment group only):
symbol: must be set          # Required for agent memory persistence
memory_dir: must be set      # Where {symbol}_memory.json is written
```

## Key Insights
- **Silent failure mode**: Config drift produces no errors — models just train with wrong parameters
- **A/B invalidation**: If baseline and treatment use different env_config, comparison is invalid. Both groups share the same `env_config` object, so fixing it requires re-running both groups
- **Three notebooks to sync**: `training.ipynb`, `agent_validation_analysis.ipynb` (Colab), `agent_validation_runpod.ipynb` (RunPod)
- **Data freshness is also a drift**: `prefetch_all_data(force_refresh=False)` silently reuses stale cache. See `persistent-cache-gap-filling` skill
- **Agent memory persistence requires two params**: Both `symbol` and `memory_dir` must be set on `MultiAgentConfig`

## References
- `alpaca_trading/gpu/vectorized_env.py` — Canonical GPUEnvConfig defaults
- `alpaca_trading/training/multi_agent.py:1540` — `_save_run_summary()` guard clause
- `notebooks/CLAUDE.md` — Config alignment table
- Skill: `colab-notebook-development` — Notebook cell structure requirements
