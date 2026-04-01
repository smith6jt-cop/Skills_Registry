# Confidence Pipeline Fix (v5.4.1)

## Trigger
When the live trader produces predictions but executes zero trades, or when confidence values are consistently below the entry threshold.

## Problem
Paper trader ran 03-25 through 03-28 with 4,200 signal rejections and 0 trades executed. All predictions rejected as `confidence_too_low`.

## Root Causes (6 issues found)

### 1. Predator-Prey Confidence Penalties (PRIMARY)
**File**: `alpaca_trading/prediction/multi_tf_predictor.py:532-569`
**Impact**: Reduced raw softmax 0.35 → 0.20 (below 0.40 threshold)

Three multiplicative penalties compounded:
- High vol (>35% annualized): 0.7x — triggered for all models
- PP disagreement (PP signal ≠ RL signal): 0.5x
- Low PP confidence (<0.4): 0.8x — triggered almost always (PP defaults ~0.33)
- Combined worst case: 0.7 × 0.5 × 0.8 = 0.28x reduction

**Fix**: Disabled penalties. RL model already incorporates regime info via Markov chains. PP signal still logged.

### 2. Regime Duration Features Always Zero
**File**: `alpaca_trading/gpu/inference_obs_builder.py:636-663`
**Impact**: Train/inference feature mismatch

Three of 6 new v5.3.0 features (`trend_bars`, `vol_bars`, `macro_bars`) hardcoded to 0.0 during inference but had real values during training. Fix: Track counters across `build()` calls in `InferenceObservationBuilder`, pass via kwargs, normalize as `min(bars/50, 1.0)`.

### 3. Wrong Vol Probs Initialization
**File**: `alpaca_trading/gpu/inference_obs_builder.py:827`
**Impact**: First prediction uses wrong Markov priors

Builder initialized `vol_probs = [0.33, 0.34, 0.33]` but GPU/CPU Markov both use `[0.2, 0.6, 0.2]` (medium vol prior). Fix: Changed builder defaults to match.

### 4. Duplicate Entry Orders
**File**: `scripts/live_trader.py:1601`
**Impact**: 42+ unfilled limit orders accumulated ($78.7k pending exposure)

Entry code submitted new limit order every 15s loop without checking for existing pending orders. Fix: Added `broker.list_orders(status='open')` check before entry.

### 5. Asset Type Misclassification
**File**: `alpaca_trading/trading/market_hours.py:241`
**Impact**: 3-char stock tickers treated as futures (WST, CNM), bypassing market hours

`detect_asset_type()` used `len(symbol) <= 3` as futures heuristic. Fix: Removed length heuristic, exact match only.

### 6. Spurious VaR Circuit Breaker
**Impact**: 30-min trading suspension from stale weekend data

VaR calculation produced 81.6x limit (1.631 vs 0.020) using stale return data across market close. Self-resolves after suspension period.

## Investigation Approach

1. Checked log for rejection patterns → found 4,200 `confidence_too_low` rejections
2. Queried trading DB → confirmed 0 trades, all predictions below 0.40
3. Traced confidence pipeline: raw softmax → PP penalties → aggregation → threshold
4. Found PP penalties reducing confidence by 44-56%
5. Checked observation builder for train/inference mismatches
6. Found regime bar features hardcoded to 0.0
7. After fixing confidence, found duplicate orders (42 accumulated)
8. After fixing orders, found asset type misclassification

## Results
- Raw confidence after fix: WST 0.43-0.65, CNM 0.40-0.56, CLSK 0.30-0.46
- First trade at 09:31 on Day 1 (CNM LONG, +$0.38)
- 4 trades on Day 1: 2W/2L, net -$71 (-0.07%)

## Key Insight
With 8-action softmax, typical confidence range is 0.30-0.65. The 0.40 threshold is appropriate for this range. Any multiplicative penalty pipeline will almost certainly block all trades.

## Parameters
- `min_confidence`: 0.40 (base floor)
- Adaptive thresholds: low=0.38, normal=0.40, elevated=0.43, high=0.45
- Max theoretical confidence: ~0.65 (8-action softmax)
