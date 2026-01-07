# Bitcoin Trading Assistant - Backend

FastAPI backend for Bitcoin market data analysis with automatic scheduling.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Tested on 3.12 |
| PostgreSQL | 14+ | Running on localhost:5432 |
| pip | Latest | Comes with Python |

## Quick Start

### 1. Create virtual environment
```powershell
cd C:\Users\ilies\git\bitcoin-trading-assistant\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install dependencies
```powershell
pip install -r requirements.txt
```

### 3. Configure environment

Copy `.env.example` to `.env` and edit:
```powershell
copy .env.example .env
notepad .env
```

Required variables:
```env
# Database
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/bitcoin_assistant

# App
DEBUG=true

# Scheduler
SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_MINUTES=240
SCHEDULER_SYMBOL=BTC/USD
SCHEDULER_DAYS=7
```

> ⚠️ Never commit `.env` to git!

### 4. Setup PostgreSQL
```sql
CREATE USER btc_user WITH PASSWORD 'your_password';
CREATE DATABASE bitcoin_assistant OWNER btc_user;
```

### 5. Run the server
```powershell
uvicorn app.main:app --reload
```

Server starts at: http://localhost:8000

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |
| GET | `/health/db` | Database connection check |
| GET | `/market/candles` | Get stored candles |
| POST | `/market/candles/fetch` | Fetch from CoinGecko |
| GET | `/market/candles/gaps` | Data quality analysis |
| GET | `/market/indicators` | Technical indicators |
| GET | `/market/price` | Current BTC price |
| GET | `/scheduler/status` | Scheduler state |

## Running Tests
```powershell
cd C:\Users\ilies\git\bitcoin-trading-assistant\backend
.\venv\Scripts\Activate.ps1
pytest -v
```

Expected: 88 tests passing.

## Scheduler

The scheduler automatically fetches candles at configured intervals.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEDULER_ENABLED` | false | Enable/disable scheduler |
| `SCHEDULER_INTERVAL_MINUTES` | 240 | Fetch interval (240 = 4h) |
| `SCHEDULER_SYMBOL` | BTC/USD | Trading pair |
| `SCHEDULER_DAYS` | 7 | History window |

### Dev Mode

For testing, use a short interval:
```env
SCHEDULER_INTERVAL_MINUTES=5
```

> ⚠️ With `uvicorn --reload`, the scheduler restarts on every file change. Set `SCHEDULER_ENABLED=false` during active development.

## Troubleshooting

### Timezone Issues

All timestamps are UTC. The API returns ISO8601 with `+00:00` suffix.

If you see timezone mismatches:
1. Check PostgreSQL timezone: `SHOW timezone;`
2. Ensure `normalize_to_utc()` is called on all datetime inputs

### Scheduler Not Starting

1. Check `SCHEDULER_ENABLED=true` in `.env`
2. Restart uvicorn (not just reload)
3. Check `/scheduler/status` endpoint

### Database Connection
```powershell
# Test PostgreSQL connection
psql -h localhost -U btc_user -d bitcoin_assistant -c "SELECT 1;"
```

## Project Structure
```
backend/
├── app/
│   ├── api/routes/       # FastAPI routers
│   ├── models/           # SQLAlchemy models
│   ├── services/         # Business logic
│   ├── tasks/            # Scheduler
│   ├── utils/            # Shared utilities
│   ├── config.py         # Pydantic settings
│   ├── database.py       # DB connection
│   └── main.py           # App entry point
├── tests/                # pytest tests
├── requirements.txt
└── .env.example
```