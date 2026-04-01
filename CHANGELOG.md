cd C:\Users\ilies\git\bitcoin-trading-assistant\backend
.\venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000# Changelog

All notable changes to this project will be documented in this file.

## [0.5.1] - 2026-01-09

### Added
- **Scheduler resample 4h→1d**: après chaque fetch CoinGecko 4h, les candles sont automatiquement agrégés en timeframe 1d
- `/scheduler/status` expose `last_result.resample.1d` avec le nombre de candles 1d créés
- 7 nouveaux tests backend pour le resample (`test_scheduler_resample_1d.py`)
- Support `db_upsert.py` dialect-aware (SQLite + PostgreSQL)
- Support `resample_service.py` pour agrégation OHLCV

### Fixed
- Candles 1d alignés sur 00:00 UTC (l'affichage peut montrer +01:00 selon timezone locale)

### Technical
- 89 tests backend passing
- Resample idempotent (upsert, pas de duplication)
- Erreur resample isolée (ne fait pas échouer le job principal)

## [0.5.0] - 2026-01-08

### Added
- Frontend Dashboard complet avec indicateurs RSI/MACD/SMA/Bollinger
- Chips DATA: FRESH/STALE/GAPS + SCHEDULER: ON/OFF
- Graphique chandeliers Lightweight Charts
- Bouton "Récupérer données" avec guards timeframe
- ErrorBoundary pour le graphique
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