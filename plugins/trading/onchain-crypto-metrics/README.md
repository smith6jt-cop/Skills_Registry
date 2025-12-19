# On-Chain Crypto Metrics Pattern

## Problem
Crypto markets have unique data sources (blockchain) that equities don't have. Ignoring on-chain metrics means missing signals that provide 4%+ edge according to research.

## Solution
Create an OnChainFetcher that retrieves blockchain metrics and converts them to normalized features for the observation space.

## Key Metrics

| Metric | Signal | Typical Range |
|--------|--------|---------------|
| **SOPR** (Spent Output Profit Ratio) | <1 = capitulation (bullish), >1 = profit taking | 0.9 - 1.1 |
| **Exchange Flow Ratio** | >1 = sell pressure (inflow > outflow) | 0.5 - 2.0 |
| **Active Addresses Z-Score** | Network activity normalized | -3 to +3 |
| **NVT Ratio** | Network Value / Transaction Volume (like P/E) | 10 - 200 |
| **Funding Rate** | Perpetual futures sentiment | -0.01 to +0.01 |

## Implementation

### OnChainFetcher Class
```python
class OnChainFetcher:
    SYMBOL_MAP = {
        'BTCUSD': 'BTC', 'ETHUSD': 'ETH', 'SOLUSD': 'SOL', ...
    }

    def __init__(self, api_key=None, provider="free", cache_ttl=3600):
        self.api_key = api_key
        self.provider = provider  # "glassnode", "cryptoquant", "free"
        self.cache = TTLCache(maxsize=100, ttl=cache_ttl)

    def get_sopr(self, symbol: str) -> float:
        """SOPR < 1 indicates capitulation (bullish signal)."""
        # Try API, fallback to estimation

    def build_crypto_features(self, symbol: str) -> np.ndarray:
        """Build 5 normalized features for crypto observation space."""
        metrics = self.get_metrics(symbol)
        return np.array([
            (metrics.sopr - 1.0) * 10,           # Center at 0
            (metrics.exchange_flow_ratio - 1.0) * 2,
            metrics.active_addresses_zscore,     # Already z-score
            np.clip((metrics.nvt_ratio - 50) / 100, -1, 1),
            metrics.funding_rate * 1000,         # Scale to visible
        ], dtype=np.float32)
```

### Data Sources
- **Glassnode**: Premium on-chain analytics (API key required)
- **CryptoQuant**: Exchange flow data (API key required)
- **Free**: Binance funding rate (public API) + estimations

### Integration
```python
# In observation builder
if fetcher.is_crypto_symbol(symbol):
    onchain_features = fetcher.build_crypto_features(symbol)
    obs = np.concatenate([base_obs, onchain_features])
```

## Fallback Estimations
When premium APIs unavailable, use:
- SOPR: Estimate from price momentum (proxy)
- Exchange flow: Neutral with small random variation
- Active addresses: Neutral z-score
- NVT: Default values per asset (BTC=50, ETH=30)
- Funding rate: Binance public API (always available)

## Research Basis
- TFT-Crypto research shows 4%+ edge with on-chain metrics
- Adaptive TFT for Cryptocurrency (arxiv.org/pdf/2509.10542)
- On-chain metrics capture sentiment not visible in price

## Files Created/Modified
- `alpaca_trading/data/onchain_fetcher.py` (NEW)
- `alpaca_trading/data/__init__.py` (exports added)

## Caching Strategy
- 1-hour TTL cache (on-chain data doesn't change fast)
- Per-symbol caching
- Graceful degradation on API failures
