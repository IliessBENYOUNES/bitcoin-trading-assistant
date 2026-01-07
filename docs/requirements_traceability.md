# Requirements Traceability Matrix (RTM)

## Project: Bitcoin Trading Assistant
## Version: v0.4-scheduler
## Date: 2026-01-08

---

## Functional Requirements

| ID | Requirement | Acceptance Criteria | Status | Proof |
|----|-------------|---------------------|--------|-------|
| FR-MKT-001 | Fetch OHLC candles from CoinGecko | `POST /market/candles/fetch` returns fetched count > 0 | ✅ PASS | `{"fetched": 42, "inserted": 0, "duplicates": 42}` |
| FR-MKT-002 | Store candles in PostgreSQL | Candles persisted across restarts | ✅ PASS | `total_in_db: 56` |
| FR-MKT-003 | Idempotent upsert (no duplicates) | Same candle not inserted twice | ✅ PASS | `duplicates: 42` on re-fetch |
| FR-MKT-004 | Rolling window query | `GET /market/candles?days=7` returns 7-day window | ✅ PASS | `actual_count: 43` |
| FR-QA-001 | Detect data gaps | `GET /market/candles/gaps` returns missing_count | ✅ PASS | `missing_count: 0` |
| FR-QA-002 | Freshness status | data_lag < threshold → FRESH | ✅ PASS | `data_lag_hours: 3.31, status: FRESH` |
| FR-QA-003 | Completeness status | expected == actual → OK | ✅ PASS | `expected_count: 43, actual_count: 43, status: OK` |
| FR-IND-001 | Calculate RSI(14) | `GET /market/indicators` returns rsi_14 | ✅ PASS | `latest.rsi_14 != null` after warmup |
| FR-IND-002 | Calculate MACD(12,26,9) | Response contains macd, macd_signal, macd_hist | ✅ PASS | Endpoint returns all MACD fields |
| FR-IND-003 | Calculate SMA(20,50,200) | Response contains sma_20, sma_50, sma_200 | ✅ PASS | sma_20 calculated (sma_50/200 null if insufficient data) |
| FR-IND-004 | Calculate Bollinger(20,2) | Response contains bb_mid, bb_upper, bb_lower | ✅ PASS | Bollinger bands calculated |
| FR-IND-005 | NaN → null in JSON | Warmup periods return null, not NaN | ✅ PASS | First 14 points have `rsi_14: null` |
| FR-SCH-001 | Scheduler enable/disable | `SCHEDULER_ENABLED=true/false` controls startup | ✅ PASS | `enabled: true, running: true` |
| FR-SCH-002 | Periodic fetch job | Job executes at configured interval | ✅ PASS | `last_run_time` populated |
| FR-SCH-003 | Scheduler status endpoint | `GET /scheduler/status` returns state | ✅ PASS | See proof below |
| FR-SCH-004 | Job success reporting | `last_result.status: "success"` on success | ✅ PASS | `{"status":"success","fetched":42}` |

---

## Non-Functional Requirements

| ID | Requirement | Acceptance Criteria | Status | Proof |
|----|-------------|---------------------|--------|-------|
| NFR-SEC-001 | No secrets in repo | `.env` not tracked, no passwords in code | ✅ PASS | `git ls-files \| findstr .env` → empty |
| NFR-SEC-002 | Test artifacts ignored | `test.db` not tracked | ✅ PASS | Listed in `.gitignore` |
| NFR-TEST-001 | Backend tests pass | `pytest -v` all green | ✅ PASS | 88 tests passing |
| NFR-TZ-001 | UTC timestamps | All timestamps stored/returned in UTC | ✅ PASS | `max_ts: "2026-01-07T20:00:00+00:00"` |
| NFR-IDEM-001 | Idempotent fetch | Re-fetch same data → 0 inserts | ✅ PASS | `inserted: 0, duplicates: 42` |

---

## QA Evidence

### Scheduler Status (2026-01-07T23:10)
```json
{
  "enabled": true,
  "running": true,
  "interval_minutes": 5,
  "symbol": "BTC/USD",
  "days": 7,
  "last_run_time": "2026-01-07T23:10:07.574460+00:00",
  "next_run_time": "2026-01-07T23:15:07.573764+00:00",
  "last_result": {
    "status": "success",
    "symbol": "BTC/USD",
    "days": 7,
    "timeframe": "4h",
    "fetched": 42,
    "inserted": 0,
    "updated": 0,
    "duplicates": 42,
    "duration_seconds": 0.917
  }
}
```

### Data Quality (2026-01-07T23:18)
```json
{
  "symbol": "BTC/USD",
  "timeframe": "4h",
  "freshness": {
    "data_lag_hours": 3.31,
    "threshold_hours": 4,
    "status": "FRESH"
  },
  "completeness": {
    "expected_count": 43,
    "actual_count": 43,
    "missing_count": 0,
    "status": "OK"
  },
  "global_status": "OK"
}
```

---

## Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| test_health.py | 3 | ✅ |
| test_market.py | 4 | ✅ |
| test_indicators.py | 35 | ✅ |
| test_time_buckets.py | 30 | ✅ |
| test_scheduler.py | 16 | ✅ |
| **Total** | **88** | ✅ |