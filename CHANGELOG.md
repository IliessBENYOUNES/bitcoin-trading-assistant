# Changelog

All notable changes to the Bitcoin Trading Assistant project.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [v0.4-scheduler] - 2026-01-08

### Added
- **APScheduler integration** for automatic candle fetching
- `GET /scheduler/status` endpoint returning enabled, running, next_run_time, last_result
- Scheduler configuration via environment variables:
  - `SCHEDULER_ENABLED` (true/false)
  - `SCHEDULER_INTERVAL_MINUTES` (default: 240 = 4h)
  - `SCHEDULER_SYMBOL` (default: BTC/USD)
  - `SCHEDULER_DAYS` (default: 7)
- Thread-safe state management for scheduler
- Proper DB session handling (create/close per job)
- 16 new scheduler tests

### Changed
- `app/config.py`: Added scheduler settings fields
- `app/main.py`: Added scheduler startup/shutdown hooks

### Fixed
- FastAPI `Query(regex=...)` deprecated warning → `Query(pattern=...)`

### Documentation
- Added `CHANGELOG.md`
- Added `docs/requirements_traceability.md` (RTM)
- Added `backend/README.md` with setup instructions

### QA Status
- Tests: 88 passing
- Scheduler: `last_result.status: "success"`
- Freshness: `FRESH` (data_lag < 4h)
- Completeness: `OK` (43/43 candles)
- Global: `OK`

---

## [v0.3-indicators] - 2026-01-07

### Added
- `GET /market/indicators` endpoint
- Technical indicators: RSI(14), MACD(12,26,9), SMA(20,50,200), Bollinger(20,2)
- Centralized time utilities in `app/utils/time_buckets.py`
- NaN → null JSON serialization (warmup periods)
- `include_candles` parameter for full OHLCV in response
- `end_ts` parameter for backtest reproducibility
- 35 indicator tests

### Changed
- Bucket alignment logic unified (0/4/8/12/16/20 UTC for 4h)

---

## [v0.2-market-live] - 2026-01-06

### Added
- `GET /market/candles` endpoint with rolling window support
- `POST /market/candles/fetch` to fetch from CoinGecko API
- `GET /market/candles/gaps` for data quality analysis
- `GET /market/price` for current price
- `GET /market/info` for market data
- Completeness vs Freshness separation in QA
- PostgreSQL storage with SQLAlchemy
- Idempotent upsert (duplicates detection)

### Infrastructure
- FastAPI + Uvicorn
- PostgreSQL + SQLAlchemy
- React + TypeScript frontend (basic dashboard)
- pytest test suite