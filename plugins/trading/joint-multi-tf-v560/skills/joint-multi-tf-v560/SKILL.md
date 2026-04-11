---
name: joint-multi-tf-v560
description: "v5.6.0 joint multi-TF model: single model per symbol with broadcast 1Hour context replaces dual 15Min/1Hour models. Trigger: (1) replacing weighted-voting model aggregation, (2) adding broadcast features to vectorized env, (3) limited training data + worried about overfitting from doubling obs_dim, (4) backtest builder mismatch with newer feature counts."
author: Claude Code
date: 2026-04-10
---

# Joint Multi-TF Architecture v5.6.0

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-04-10 |
| **Goal** | Replace separate 15Min/1Hour models + weighted voting with single joint model that uses 15Min steps and 1Hour context broadcast features |
| **Environment** | GPUVectorizedTradingEnv, NativePPOTrainer, InferenceObservationBuilder, BacktestObservationBuilder |
| **Status** | Code complete, awaiting Colab training + walk-forward validation |

## Context

Two prior architectures had problems:
- **v5.2.0 dual-model**: Train 15Min and 1Hour models independently, combine via `aggregate_timeframe_predictions()` weighted voting (15Min w=0.15, 1Hour w=0.25). Models never learn to complement each other.
- **Mar-25 evaluation**: Multi-TF was NOT universally better — only CLSK improved (PF 1.29→3.98), CNM degraded (PF 1.84→1.25), MOH degraded, PSTG overtraded.

The user's plan was a "hierarchical" architecture where 15Min refines confidence in the 1Hour prediction. Three options were considered:

| Option | Description | obs_dim | Verdict |
|--------|-------------|---------|---------|
| A | Full dual 51-feature 1H window (separate window) | 10,200 | Rejected — doubles first-layer params, ~140K crypto bars too few |
| B | **Broadcast 1H summary features** | 5,800 | **Chosen** |
| C | Compressed 1H window (different shape) | ~7,000 | Rejected — needs MLP arch changes or padding hacks |

## Verified Workflow

### 1. Add Config Fields (GPUEnvConfig)

```python
# alpaca_trading/gpu/vectorized_env.py
@dataclass(slots=True)
class GPUEnvConfig:
    # ... existing fields ...
    use_hourly_context: bool = False          # v5.6.0: 1Hour broadcast features
    hourly_context_bars_per_hour: int = 4     # 15Min bars per hour
```

### 2. Vectorized Precomputation at Init

```python
def _precompute_hourly_context(self):
    """Pre-compute (T, 7) hourly context tensor — fully vectorized, no Python loops."""
    bph = self.config.hourly_context_bars_per_hour
    p = prices[0] if prices.dim() == 2 else prices  # (T,)
    T = p.shape[0]
    hc = torch.zeros(T, 7, dtype=self.dtype, device=self.device)

    # Returns
    returns = torch.zeros(T, dtype=self.dtype, device=self.device)
    returns[1:] = (p[1:] - p[:-1]) / (p[:-1] + 1e-8)

    # Hour boundary indexing (vectorized)
    bar_indices = torch.arange(T, device=self.device)
    h_end = (bar_indices // bph) * bph     # (T,)
    valid_hour = h_end >= bph
    h_start = (h_end - bph).clamp(min=0)

    # Gather hour-level features
    hour_open = p[h_start]
    hour_close = p[(h_end - 1).clamp(min=0)]
    hc[valid_hour, 0] = (hour_close[valid_hour] - hour_open[valid_hour]) / (hour_open[valid_hour] + 1e-8)

    # Reshape into (n_complete_hours, bph) blocks for per-hour std/range
    n_complete_hours = T // bph
    if n_complete_hours > 0:
        hourly_returns = returns[:n_complete_hours * bph].reshape(n_complete_hours, bph)
        hourly_vol = hourly_returns.std(dim=1)
        hour_idx = ((bar_indices // bph) - 1).clamp(min=0)
        hc[valid_hour, 1] = hourly_vol[hour_idx[valid_hour].clamp(max=n_complete_hours - 1)]

    # Lookback features (16-bar trend, 4/8-bar momentum acceleration)
    p_16_ago = p[(bar_indices - 16).clamp(min=0)]
    hc[:, 2] = (p - p_16_ago) / (p_16_ago + 1e-8)
    hc[:16, 2] = 0.0

    # Cumulative sum trick for rolling RSI proxy
    positive_returns = (returns > 0).float()
    if T >= 16:
        cumsum = positive_returns.cumsum(dim=0)
        rsi_sum = cumsum.clone()
        rsi_sum[16:] = cumsum[16:] - cumsum[:-16]
        hc[16:, 4] = rsi_sum[16:] / 16.0

    # Position in hour (always valid)
    hc[:, 6] = ((bar_indices % bph) + 1).float() / bph

    self._obs_hourly_context = hc
```

### 3. O(1) Step-Time Gather + Broadcast

```python
def _get_observations(self):
    # ... existing feature gathers ...

    # 12b. Hourly context features (7) — single gather + broadcast
    if self.config.use_hourly_context:
        if hasattr(self, '_obs_hourly_context'):
            hc_feats = self._obs_hourly_context[step_vals]  # (n_envs, 7)
            obs[:, :, feat_idx:feat_idx+7] = hc_feats.unsqueeze(1).expand(-1, W, -1)
            feat_idx += 7
```

### 4. Update Feature Count Detection

```python
# alpaca_trading/gpu/inference_obs_builder.py
def get_target_features_from_obs_dim(obs_dim, window=100):
    features = obs_dim // window
    if features == 58:
        return 58  # v5.6.0: 51 base + 7 hourly context
    elif features == 51:
        return 51  # v5.5.0
    # ... etc
```

### 5. Update Both Inference and Backtest Builders

`InferenceObservationBuilder` delegates to `build_inference_observation()` — add new branch:
```python
elif target_features == 58:
    n_base = 6; n_hourly_context = 7  # ... etc
```

`BacktestObservationBuilder` needs `_precompute_hourly_context()` and conditional reads in `get_obs_at_bar()`. Use exact same numpy formulas as the GPU vectorized version for parity.

### 6. Notebook Changes

Cell 14 (TRAINING_TIMEFRAMES): `['15Min']` (single TF)
Cell 24 (env_config): `n_features=58, use_hourly_context=True, hourly_context_bars_per_hour=4`
Cell 32 (loop): No change — already iterates over `(symbol, training_tf)` pairs, just one TF now

### 7. Live Trader / Backtest

**No code changes needed.** Both auto-detect `target_features` from `model.obs_dim` via `get_target_features_from_obs_dim()`. v5.6.0 models (obs_dim=5800) automatically get hourly context computation.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Python for-loop precomputation | T=140K bars × 7 features = ~1-2s init overhead | Vectorize with `torch.arange + clamp + gather`, even for init code |
| 8 hourly features → 59 total | Collides with v2.7.0 feature count in `get_target_features_from_obs_dim()` | Use 7 features → 58 total to avoid collision |
| Doubling obs_dim with full dual window | First layer would balloon to 10.4M params (12.6M total) on ~140K crypto bars — overfitting risk | Add features only as broadcast scalars, keep first layer ≤ ~6M params |
| Trusting `target_features >= 56` checks for backward compat | v5.5.0 (51) was NEVER backtested, so the always-write-7-base-features bug went undetected | Use exact `target_features in (51, 58)` checks rather than `>= N` thresholds |
| Forgetting reversal probs in BacktestObservationBuilder | v5.5.0/v5.6.0 expect 3 reversal prob features, but builder skipped straight to extended indicators | Match training env feature layout exactly — add reversal probs for `target_features in (51, 58, 65)` |

## Pre-existing Bug Discovered During v5.6.0 Work

`BacktestObservationBuilder.get_obs_at_bar()` always wrote 7 base + 4 intraday features (53 total) regardless of `target_features`. For v5.5.0 (51 features), this caused `IndexError: index 51 out of bounds`. The bug was latent because v5.5.0 models were never backtested before v5.6.0 work — the system jumped from v5.3.0 (65 features, builder works) to v5.6.0 (forced the bug to surface).

**Fix**: Conditional skip of volume_proxy and intraday for `target_features in (51, 58)`. Also added reversal probs (3 features) for `target_features in (51, 58, 65)`.

**Lesson**: After feature reductions, ALWAYS run a smoke test through `BacktestObservationBuilder.precompute() + get_obs_at_bar()` with the new feature count. Don't trust that "if training compiles, backtest will too" — they have separate observation pipelines.

## Final Parameters

```python
# v5.6.0 GPUEnvConfig
n_features = 58
use_hourly_context = True
hourly_context_bars_per_hour = 4  # 15Min bars per hour
timeframe = '15Min'  # Stepping timeframe (1Hour context is internal)

# Feature breakdown (58 total)
base = 6                  # norm_price, returns, log_returns, vol, momentum, rsi
temporal = 7              # calendar features
markov = 12               # vol/trend/momentum/macro probs
reversal_probs = 3        # always with markov
extended = 14             # MACD, ADX, Stoch, ATR, BB, CCI, Williams, ROC, RSI
multi_window = 9          # 3 windows × 3 features
hourly_context = 7        # NEW: h1_return, h1_vol, h1_trend, h1_momentum, h1_rsi, h1_range, position_in_hour
```

## Key Insights

- **First layer width dominates network params** (86-90%) — adding broadcast features is much cheaper than adding windowed features (no `× window` multiplier on params, but still gives the model the info every step).
- **Broadcast pattern is the right level of abstraction** for time-series context features — same-value-across-window matches how the model can already use volatility, momentum, multi-window features.
- **Crypto overtrains at 200M steps** (peak at 50-100M per memory) → modest network growth is preferred over full dual obs space.
- **Feature count avoidance**: Always check `get_target_features_from_obs_dim()` lookup table before choosing a new total. 58 was deliberately chosen to avoid collision with v2.7.0's 59.
- **Position-in-hour is the cheapest, most useful feature** — single broadcast scalar tells the model "you have 25%/50%/75%/100% of the hour's data" so it knows when to commit vs when to wait.

## Testing Strategy

- **Unit tests** for `_precompute_hourly_context()`: Verify h1_return/h1_volatility/position_in_hour on known prices
- **Output shape tests**: `(n_envs, 100, 58)` for env, `(100, 58)` for builders
- **Train/inference parity**: Same prices → same hourly context values across env / inference builder / backtest builder
- **Backward compat**: v5.5.0 models (obs_dim=5100) still load and infer correctly
- **Quick training smoke test** on synthetic data (10M steps)

18 new tests in `tests/test_hourly_context.py`. All 18 pass plus 13 updated `test_model_version.py`.

## References
- `alpaca_trading/gpu/vectorized_env.py`: `_precompute_hourly_context()`, `_get_observations()` lines ~1846-1853, `_calculate_obs_features()` line ~1067
- `alpaca_trading/gpu/inference_obs_builder.py`: `build_inference_observation()` (target_features=58 branch), `BacktestObservationBuilder._precompute_hourly_context()`
- `alpaca_trading/training/model_version.py`: v5.6.0 `ModelSpec`, version detection
- `notebooks/training.ipynb`: Cell 14 (TRAINING_TIMEFRAMES), Cell 24 (env_config)
- `tests/test_hourly_context.py`: 18 tests (feature count, model version, both builders, env config)
- `CHANGELOG.md`: v5.6.0 entry
- See also: `multi-timeframe-training` skill (the deprecated dual-model approach)
