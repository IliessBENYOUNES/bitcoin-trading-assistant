# 📊 Current State — Bitcoin Trading Assistant

> **Dernière mise à jour :** 1er avril 2026
> **Version :** v0.6.0
> **Branche :** `master`
> **Dernier commit :** `8d443e6` — fix: restore Dashboard.tsx

---

## 1. Vue d'ensemble

Bitcoin Trading Assistant (alias **BTC Insight**) est un outil d'aide à la lecture du marché Bitcoin. Il collecte des données OHLCV depuis CoinGecko, les stocke en base, les agrège sur 4 timeframes, calcule des indicateurs techniques, et affiche tout dans un dashboard interactif.

| Élément | Valeur |
|---------|--------|
| Version courante | **v0.6.0** |
| Backend | FastAPI 0.109 + SQLAlchemy 2.0 + Python 3.12 |
| Frontend | React 18 + TypeScript 5 + Vite 5 + MUI 5 |
| Base de données | PostgreSQL (prod) / SQLite (tests) |
| Tests backend | **110 tests**, tous passing ✅ |
| Frontend build | **tsc + vite build** sans erreur ✅ |

---

## 2. Architecture

```
bitcoin-trading-assistant/
├── backend/                    # API FastAPI
│   ├── app/
│   │   ├── main.py             # Point d'entrée, lifespan, CORS
│   │   ├── config.py           # Settings (pydantic-settings, .env)
│   │   ├── database.py         # Engine SQLAlchemy + session
│   │   ├── api/routes/
│   │   │   ├── health.py       # GET /health, /health/db
│   │   │   ├── market.py       # GET /market/candles, indicators, gaps, price
│   │   │   └── scheduler.py    # GET /scheduler/status, POST trigger
│   │   ├── models/
│   │   │   └── candle.py       # Modèle Candle (OHLCV + timeframe)
│   │   ├── schemas/
│   │   │   └── candle.py       # Schémas Pydantic
│   │   ├── services/
│   │   │   ├── coingecko_service.py  # Client HTTP CoinGecko
│   │   │   ├── indicator_service.py  # RSI, MACD, SMA, Bollinger
│   │   │   └── resample_service.py   # Agrégation 30m→1h, 4h→1d
│   │   ├── tasks/
│   │   │   └── scheduler.py    # APScheduler dual-jobs (4h + 30m)
│   │   └── utils/
│   │       ├── time_buckets.py # Alignement UTC, fenêtres glissantes
│   │       └── db_upsert.py    # Upsert dialect-aware
│   └── tests/                  # 110 tests pytest
│       ├── test_health.py
│       ├── test_indicators.py
│       ├── test_market.py
│       ├── test_scheduler.py
│       ├── test_scheduler_dual_jobs.py
│       ├── test_scheduler_resample_1d.py
│       ├── test_scheduler_resample_1h.py
│       └── test_time_buckets.py
│
├── frontend/                   # React SPA
│   └── src/
│       ├── App.tsx
│       ├── pages/
│       │   └── Dashboard.tsx   # Page principale
│       ├── components/
│       │   ├── CandlestickChart.tsx   # Graphique Lightweight Charts
│       │   ├── IndicatorPanel.tsx     # Panel RSI/MACD/SMA/Bollinger
│       │   ├── StatusRow.tsx          # Barre de statut connectée
│       │   ├── StatusBar.tsx          # Barre de statut UI
│       │   ├── DataFreshnessChip.tsx  # Chip FRESH/STALE/GAPS
│       │   ├── SchedulerChip.tsx      # Chip ON/OFF scheduler
│       │   ├── PriceCard.tsx          # Carte prix courant
│       │   └── ErrorBoundary.tsx      # Error boundary graphique
│       ├── hooks/
│       │   ├── useCandles.ts          # Fetch candles API
│       │   ├── useIndicators.ts       # Fetch indicateurs API
│       │   ├── useMarketGaps.ts       # Fetch gaps API
│       │   └── useSchedulerStatus.ts  # Fetch scheduler status
│       ├── api/
│       │   ├── client.ts             # Axios instance
│       │   └── marketApi.ts          # API calls typées
│       └── types/
│           └── api.ts               # Types TypeScript
│
└── docs/
    ├── CURRENT_STATE.md        # ← CE FICHIER
    ├── ROADMAP.md              # Roadmap par phases
    ├── ROADMAP_INFINI.md       # Vision long terme BTC Insight → INFINI
    └── requirements_traceability.md
```

---

## 3. Fonctionnalités livrées

### 3.1 Backend — API Endpoints

| Méthode | Endpoint | Description | Status |
|---------|----------|-------------|--------|
| GET | `/` | Route racine | ✅ |
| GET | `/health` | Health check | ✅ |
| GET | `/health/db` | Health check DB | ✅ |
| GET | `/market/candles` | Liste candles (filtres: timeframe, symbol, days, limit) | ✅ |
| POST | `/market/candles/fetch` | Fetch manuel CoinGecko | ✅ |
| GET | `/market/candles/gaps` | Analyse qualité données (fraîcheur + complétude) | ✅ |
| GET | `/market/indicators` | Indicateurs techniques (RSI, MACD, SMA, Bollinger) | ✅ |
| GET | `/market/price` | Prix courant | ✅ |
| GET | `/market/info` | Info marché | ✅ |
| GET | `/scheduler/status` | État scheduler + dernier résultat par job | ✅ |
| POST | `/scheduler/trigger/4h` | Trigger manuel job 4h | ✅ |
| POST | `/scheduler/trigger/30m` | Trigger manuel job 30m | ✅ |

### 3.2 Backend — Services

| Service | Description | Status |
|---------|-------------|--------|
| **CoinGecko Service** | Client HTTP async, mapping symboles, gestion timeouts | ✅ |
| **Indicator Service** | RSI(14), MACD(12,26,9), SMA(20,50,200), Bollinger(20,2) | ✅ |
| **Resample Service** | Agrégation OHLCV 30m→1h et 4h→1d, idempotent via upsert | ✅ |
| **Scheduler Dual-Jobs** | Job 4h (fetch 7j → 4h → resample 1d) + Job 30m (fetch 1j → 30m → resample 1h) | ✅ |

### 3.3 Backend — Timeframes supportés

| Timeframe | Source | Méthode |
|-----------|--------|---------|
| **30m** | CoinGecko direct | Job 30m fetch 1 jour |
| **1h** | Resample 30m→1h | Agrégation automatique |
| **4h** | CoinGecko direct | Job 4h fetch 7 jours |
| **1d** | Resample 4h→1d | Agrégation automatique |

### 3.4 Frontend — Composants

| Composant | Description | Status |
|-----------|-------------|--------|
| **Dashboard** | Page principale avec sélecteurs timeframe/historique | ✅ |
| **CandlestickChart** | Graphique chandeliers (Lightweight Charts) | ✅ |
| **IndicatorPanel** | Affichage RSI, MACD, SMA, Bollinger avec couleurs | ✅ |
| **StatusRow** | Barre de statut (fraîcheur + scheduler) | ✅ |
| **DataFreshnessChip** | Chip FRESH / STALE / GAPS | ✅ |
| **SchedulerChip** | Chip scheduler ON / OFF | ✅ |
| **ErrorBoundary** | Protection crash graphique | ✅ |

### 3.5 Frontend — Contrôles utilisateur

- Sélecteur timeframe : 30m, 1h, 4h, 1d
- Sélecteur historique : 1, 2, 7, 14, 30 jours
- Cap automatique à 1 jour pour 30m/1h (limite CoinGecko)
- Bouton "Fetch API" avec routing intelligent (trigger 30m ou 4h selon timeframe)
- Bouton "Actualiser" pour refresh local
- Affichage résultat fetch (inserted, updated, duplicates, resample)

---

## 4. Tests

| Fichier | Tests | Couverture |
|---------|-------|------------|
| test_health.py | 3 | Routes health + root |
| test_indicators.py | 25 | Align bucket, NaN, freshness, indicateurs, intégration |
| test_market.py | 4 | Candles CRUD, filtres, limites |
| test_scheduler.py | 8 | Config, timeframe, lifecycle, fetch job, status |
| test_scheduler_dual_jobs.py | 13 | Dual config, jobs 4h/30m, erreurs |
| test_scheduler_resample_1d.py | 7 | Resample 4h→1d, OHLCV, idempotent |
| test_scheduler_resample_1h.py | 6 | Resample 30m→1h, OHLCV, idempotent |
| test_time_buckets.py | 17 | Timeframes, normalisation, buckets, fenêtres |
| **TOTAL** | **110** | **Tous passing ✅** |

---

## 5. Stack technique

### Backend
- **Python 3.12**
- FastAPI 0.109.2
- Uvicorn 0.27.1
- SQLAlchemy 2.0.25
- Pydantic 2.6.1 + pydantic-settings 2.1.0
- httpx 0.26.0 (client HTTP async)
- pandas 2.1.4 + pandas-ta-classic 0.3.14b0
- APScheduler ≥3.10.0
- pytest 7.4.4 + pytest-asyncio 0.23.4

### Frontend
- **React 18.2** + **TypeScript 5.3**
- Vite 5.0
- MUI (Material UI) 5.15
- Lightweight Charts 4.1
- Axios 1.6.5

### Infrastructure
- PostgreSQL (prod) / SQLite (tests)
- Virtualenv Python (backend/venv)
- npm (frontend/node_modules)

---

## 6. Comment lancer

### Backend
```bash
cd backend
.\venv\Scripts\activate        # Windows
source venv/bin/activate       # Linux/Mac
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

### Tests
```bash
cd backend
python -m pytest tests/ -v
```

---

## 7. Ce qui n'est PAS encore fait

| Feature | Phase | Status |
|---------|-------|--------|
| Dark/Light mode | v0.7 | ❌ Non commencé |
| Responsive mobile | v0.7 | ❌ Non commencé |
| Persistance localStorage | v0.7 | ❌ Non commencé |
| Alertes & Notifications | v0.8 | ❌ Non commencé |
| Multi-Assets (ETH, SOL...) | v0.9 | ❌ Non commencé |
| Backtesting engine | v1.0 | ❌ Non commencé |
| Paper trading | v1.1 | ❌ Non commencé |
| Docker Compose | v1.2 | ❌ Non commencé |
| CI/CD GitHub Actions | v1.2 | ❌ Non commencé |
| Auth JWT | v1.2 | ❌ Non commencé |

---

## 8. Problèmes connus

| # | Problème | Sévérité | Notes |
|---|----------|----------|-------|
| 1 | Warnings pytest : coroutine `_fetch_and_store` non attendue dans certains tests mockés | ⚠️ Low | Ne bloque pas les tests, cosmétique |
| 2 | Vite build warning : chunk > 500 kB | ⚠️ Low | Suggestion de code-splitting |
| 3 | CHANGELOG.md a des commandes shell en tête de fichier | ⚠️ Low | Nettoyage à faire |

