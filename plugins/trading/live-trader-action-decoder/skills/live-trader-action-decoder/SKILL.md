# Live Trader Action Decoder & Confidence Threshold Fix

## Problem
Three bugs prevented the live trader from executing trades after deploying v5.3.0 (8-action) models:

1. **8-action decoder missing**: `multi_tf_predictor.py:_get_rl_prediction()` only handled `n_actions == 7`, falling through to legacy 3-action for 8-action models. BUY_50% (action=2) decoded as SELL (direction=-1). Actions 3-7 all decoded as HOLD.
2. **Markov system init**: `timeframe_selector.py` passed `chains` as a list instead of `Dict[str, MarkovChain]`, crashing all multi-TF predictions.
3. **Confidence thresholds unreachable**: Base 0.55 + regime adjustments (up to 0.65) exceeded structural max of 8-action softmax (~0.55).

## Root Cause Analysis

### 8-Action Decoder
The correct decoder (`interpret_model_action()`) existed in `live_trader.py:654` but `multi_tf_predictor.py` had its own inline decoder that only handled 7-action and 3-action. When models upgraded from 7 to 8 actions in v4.0.0, the multi_tf_predictor decoder was not updated.

**Detection pattern**: If model has `n_actions=8` and logs show `dir=-1` when model should be buying, or permanent `dir=0`, suspect action decoder mismatch.

### Confidence Thresholds
With 8 actions, the maximum softmax probability is structurally lower than with 3 actions (uniform = 0.125 vs 0.333). The practical max observed was ~0.56. A base threshold of 0.55 blocked >98% of signals.

**Detection pattern**: If logs show >95% of directional predictions rejected by confidence threshold, the threshold is likely calibrated for a different action space size.

## Solution

### Files Modified
1. `alpaca_trading/prediction/multi_tf_predictor.py:367` — Added `n_actions == 8` branch matching the action space:
   ```
   0=HOLD, 1=BUY_25%, 2=BUY_50%, 3=BUY_75%, 4=SELL_25%, 5=SELL_50%, 6=SELL_75%, 7=CLOSE
   ```

2. `alpaca_trading/signals/timeframe_selector.py:119` — Changed list to dict with MarkovChain wrapping:
   ```python
   chains={"volatility": MarkovChain(vol_chain), "trend": MarkovChain(trend_chain), "timeframe": MarkovChain(timeframe_chain)}
   ```

3. `scripts/live_trader.py:1050` — Lowered `base_threshold` 0.55 → 0.40, regime adjustments reduced, extreme vol gate 0.70 → 0.45.

### Final Parameters
```python
# Confidence thresholds (v5.3.3)
base_threshold = 0.40
regime_adjustments = {
    'low': -0.02,      # 0.38
    'subdued': -0.01,  # 0.39
    'normal': 0.0,     # 0.40
    'elevated': +0.03, # 0.43
    'high': +0.05,     # 0.45
    'unknown': +0.02   # 0.42
}
extreme_vol_confidence = 0.45  # For annualized vol > 60%
```

## Verification
- CNM immediately placed a buy order on first prediction cycle after fix (was blocked for 23 hours before)
- WST changed from permanent `dir=0` to `dir=1` (correct BUY signal)
- CLSK no longer crashes with `'list' object has no attribute 'items'`
- 169 tests passed, 0 failures

## Key Lesson
When adding new action spaces to the training environment, **grep for ALL action decoders** across the codebase. There were two independent decoders: `interpret_model_action()` in `live_trader.py` (correct) and inline code in `multi_tf_predictor.py` (broken). The correct one was never called by the live prediction pipeline.

**Prevention**: The `interpret_model_action()` function should be the single source of truth, imported wherever action decoding is needed (moved to a shared module, not duplicated).
