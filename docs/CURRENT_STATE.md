# 📊 Current State — Bitcoin Trading Assistant

> **Dernière mise à jour :** 2 avril 2026
> **Version :** v0.9.3
> **Branche :** `master`
> **Dernier commit :** 384463f — feat(news): add NewsPanel frontend + useNews hook + Dashboard integration v0.9

---

## 1. Vue d'ensemble

Bitcoin Trading Assistant (alias **BTC Insight**) est un outil d'aide à la lecture du marché Bitcoin. Il collecte des données OHLCV depuis CoinGecko, les stocke en base, les agrège sur 4 timeframes, calcule des indicateurs techniques, **les interprète en signaux structurés avec un score composite**, **surveille des alertes configurables**, **collecte les news crypto avec analyse de sentiment**, et affiche tout dans un dashboard interactif.

| Élément | Valeur |
|---------|--------|
| Version courante | **v0.9.0** |
| Backend | FastAPI 0.109 + SQLAlchemy 2.0 + Python 3.12 |
| Frontend | React 18 + TypeScript 5 + Vite 5 + MUI 5 |
| Base de données | PostgreSQL (prod) / SQLite (tests) |
| Tests backend | **253 tests**, tous passing ✅ |
| Frontend build | **tsc + vite build** sans erreur ✅ |

---

## 2. Architecture

```
bitcoin-trading-assistant/
├── CLAUDE.md                   # Source unique de vérité agent IA
├── AGENT.md                    # Conservé pour compatibilité (pointe vers CLAUDE.md)
├── backend/                    # API FastAPI
│   ├── app/
│   │   ├── main.py             # Point d'entrée, lifespan, CORS
│   │   ├── config.py           # Settings (pydantic-settings, .env)
│   │   ├── database.py         # Engine SQLAlchemy + session
│   │   ├── api/routes/
│   │   │   ├── health.py       # GET /health, /health/db
│   │   │   ├── market.py       # GET /market/candles, indicators, gaps, price, signals
│   │   │   ├── alerts.py       # CRUD /alerts + POST /alerts/check
│   │   │   ├── news.py         # ← NOUVEAU (v0.9) — GET /news, GET /news/sentiment
│   │   │   └── scheduler.py    # GET /scheduler/status, POST trigger
│   │   ├── models/
│   │   │   ├── candle.py       # Modèle Candle (OHLCV + timeframe)
│   │   │   └── alert.py        # Modèle Alert (conditions + status)
│   │   ├── schemas/
│   │   │   ├── candle.py       # Schémas Pydantic candle
│   │   │   ├── signal.py       # Schémas SignalItem, CompositeScore, SignalResponse
│   │   │   ├── alert.py        # AlertCreate, AlertResponse, AlertCheck
│   │   │   └── news.py         # ← NOUVEAU (v0.9) — NewsItem, NewsSentimentSummary, NewsResponse
│   │   ├── services/
│   │   │   ├── coingecko_service.py  # Client HTTP CoinGecko
│   │   │   ├── indicator_service.py  # RSI, MACD, SMA, Bollinger
│   │   │   ├── signal_service.py     # Interprétation → signaux + score composite
│   │   │   ├── alert_service.py      # CRUD alertes + évaluation conditions
│   │   │   ├── news_service.py       # ← NOUVEAU (v0.9) — RSS + sentiment + impact
│   │   │   └── resample_service.py   # Agrégation 30m→1h, 4h→1d
│   │   ├── tasks/
│   │   │   └── scheduler.py    # APScheduler dual-jobs (4h + 30m)
│   │   └── utils/
│   │       ├── time_buckets.py # Alignement UTC, fenêtres glissantes
│   │       └── db_upsert.py    # Upsert dialect-aware
│   └── tests/                  # 253 tests pytest
│       ├── test_health.py
│       ├── test_indicators.py
│       ├── test_market.py
│       ├── test_scheduler.py
│       ├── test_scheduler_dual_jobs.py
│       ├── test_scheduler_resample_1d.py
│       ├── test_scheduler_resample_1h.py
│       ├── test_signals.py          # (v0.7)
│       ├── test_alerts.py           # (v0.8) — 48 tests alertes
│       ├── test_news.py             # ← NOUVEAU (v0.9) — 43 tests news
│       └── test_time_buckets.py
│
├── frontend/                   # React SPA
│   └── src/
│       ├── App.tsx
│       ├── pages/
│       │   └── Dashboard.tsx   # Page principale (+ SignalPanel + AlertPanel + NewsPanel)
│       ├── components/
│       │   ├── CandlestickChart.tsx   # Graphique Lightweight Charts
│       │   ├── IndicatorPanel.tsx     # Panel RSI/MACD/SMA/Bollinger
│       │   ├── SignalPanel.tsx        # (v0.7) — Jauge score, signaux, consensus
│       │   ├── AlertPanel.tsx         # (v0.8) — Formulaire + liste alertes
│       │   ├── NewsPanel.tsx          # ← NOUVEAU (v0.9) — News + sentiment + filtres
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
│       │   ├── useSchedulerStatus.ts  # Fetch scheduler status
│       │   ├── useSignals.ts          # (v0.7) — Fetch signaux API
│       │   ├── useAlerts.ts           # (v0.8) — CRUD + check alertes
│       │   └── useNews.ts            # ← NOUVEAU (v0.9) — Fetch news + polling
│       ├── api/
│       │   ├── client.ts             # Axios instance
│       │   └── marketApi.ts          # API calls typées (+ news)
│       └── types/
│           ├── api.ts               # Types TypeScript (+ News types)
│           └── index.ts             # Barrel exports
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
| GET | `/market/signals` | Signaux de trading + score composite | ✅ (v0.7) |
| GET | `/market/price` | Prix courant | ✅ |
| GET | `/market/info` | Info marché | ✅ |
| GET | `/alerts` | Lister les alertes | ✅ (v0.8) |
| POST | `/alerts` | Créer une alerte | ✅ (v0.8) |
| GET | `/alerts/{id}` | Récupérer une alerte | ✅ (v0.8) |
| PUT | `/alerts/{id}` | Modifier une alerte | ✅ (v0.8) |
| DELETE | `/alerts/{id}` | Supprimer une alerte | ✅ (v0.8) |
| POST | `/alerts/check` | Évaluer les alertes actives | ✅ (v0.8) |
| GET | `/alerts/notifications` | Alertes récemment déclenchées | ✅ (v0.8) |
| GET | `/news` | **Liste des news crypto avec sentiment** | ✅ **NOUVEAU v0.9** |
| GET | `/news/sentiment` | **Résumé du sentiment global** | ✅ **NOUVEAU v0.9** |
| GET | `/scheduler/status` | État scheduler + dernier résultat par job | ✅ |
| POST | `/scheduler/trigger/4h` | Trigger manuel job 4h | ✅ |
| POST | `/scheduler/trigger/30m` | Trigger manuel job 30m | ✅ |

### 3.2 Backend — Services

| Service | Description | Status |
|---------|-------------|--------|
| **CoinGecko Service** | Client HTTP async, mapping symboles, gestion timeouts | ✅ |
| **Indicator Service** | RSI(14), MACD(12,26,9), SMA(20,50,200), Bollinger(20,2) | ✅ |
| **Signal Service** | Interprétation indicateurs → signaux + score composite -100/+100 | ✅ (v0.7) |
| **Alert Service** | CRUD alertes + évaluation conditions (prix, RSI, MACD, score) | ✅ (v0.8) |
| **News Service** | **Collecte RSS + classification sentiment + score d'impact** | ✅ **NOUVEAU v0.9** |
| **Resample Service** | Agrégation OHLCV 30m→1h et 4h→1d, idempotent via upsert | ✅ |
| **Scheduler Dual-Jobs** | Job 4h (fetch 7j → 4h → resample 1d) + Job 30m (fetch 1j → 30m → resample 1h) | ✅ |

### 3.3 Backend — Moteur de Signaux (v0.7)

| Interpréteur | Logique | Status |
|--------------|---------|--------|
| **RSI** | Surachat (>70), survente (<30), zones intermédiaires | ✅ |
| **MACD** | Croisement haussier/baissier, force basée sur écart | ✅ |
| **SMA** | Position prix vs SMA20/50/200, comptage au-dessus/dessous | ✅ |
| **Bollinger** | Position dans les bandes, surachat/survente aux extrêmes | ✅ |
| **Score composite** | Agrégation pondérée -100/+100, confiance, consensus | ✅ |
| **Résumé lisible** | Génération automatique d'un résumé en français | ✅ |

### 3.4 Backend — Système d'Alertes (v0.8)

| Fonctionnalité | Description | Status |
|----------------|-------------|--------|
| **Modèle Alert** | Table SQLAlchemy (condition_type, operator, threshold, status, recurring) | ✅ |
| **CRUD complet** | Créer, lire, modifier, supprimer des alertes | ✅ |
| **Évaluation** | Évalue prix, RSI, MACD hist, score composite vs seuils | ✅ |
| **Conditions** | above (≥) et below (≤) | ✅ |
| **Récurrence** | Alertes one-shot ou récurrentes | ✅ |
| **Notifications** | Génération de messages de notification structurés | ✅ |

### 3.5 Backend — News & Sentiment (v0.9)

| Fonctionnalité | Description | Status |
|----------------|-------------|--------|
| **Collecte RSS** | 3 sources (CoinTelegraph, CoinDesk, Bitcoin Magazine) | ✅ |
| **Classifieur sentiment** | Keyword-based (bullish/bearish/neutral) | ✅ |
| **Score d'impact** | Détection mots-clés (HIGH/MEDIUM/LOW) | ✅ |
| **Cache mémoire** | TTL 5 minutes pour éviter de surcharger les sources | ✅ |
| **Résilience** | Timeout 10s, fallback liste vide si source échoue | ✅ |
| **Score global** | Agrégation pondérée -100/+100 avec impact | ✅ |
| **Filtre sentiment** | Filtrer par positive/negative/neutral | ✅ |

### 3.6 Backend — Timeframes supportés

| Timeframe | Source | Méthode |
|-----------|--------|---------|
| **30m** | CoinGecko direct | Job 30m fetch 1 jour |
| **1h** | Resample 30m→1h | Agrégation automatique |
| **4h** | CoinGecko direct | Job 4h fetch 7 jours |
| **1d** | Resample 4h→1d | Agrégation automatique |

### 3.7 Frontend — Composants

| Composant | Description | Status |
|-----------|-------------|--------|
| **Dashboard** | Page principale avec sélecteurs timeframe/historique | ✅ |
| **CandlestickChart** | Graphique chandeliers (Lightweight Charts) | ✅ |
| **IndicatorPanel** | Affichage RSI, MACD, SMA, Bollinger avec couleurs | ✅ |
| **SignalPanel** | Jauge score composite, liste signaux, consensus | ✅ (v0.7) |
| **AlertPanel** | Formulaire création + liste alertes + notifications | ✅ (v0.8) |
| **AlertPresets** | **12 stratégies éprouvées en 1 clic (Wilder, Appel, Elder, Brandt)** | ✅ **NOUVEAU v0.9.1** |
| **NewsPanel** | **News crypto + sentiment + filtres + jauge** | ✅ **NOUVEAU v0.9** |
| **StatusRow** | Barre de statut (fraîcheur + scheduler) | ✅ |
| **DataFreshnessChip** | Chip FRESH / STALE / GAPS | ✅ |
| **SchedulerChip** | Chip scheduler ON / OFF | ✅ |
| **ErrorBoundary** | Protection crash graphique | ✅ |

### 3.8 Frontend — Contrôles utilisateur

- Sélecteur timeframe : 30m, 1h, 4h, 1d
- Sélecteur historique : 1, 2, 7, 14, 30 jours
- Cap automatique à 1 jour pour 30m/1h (limite CoinGecko)
- Bouton "Fetch API" avec routing intelligent (trigger 30m ou 4h selon timeframe)
- Bouton "Actualiser" pour refresh local (inclut signaux + alertes + news)
- Affichage résultat fetch (inserted, updated, duplicates, resample)
- Panel signaux avec jauge, liste, confiance et consensus (v0.7)
- Panel alertes avec formulaire, liste, notifications polling (v0.8)
- **Panel news avec jauge sentiment, liste articles, filtres, liens cliquables** (v0.9)

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
| test_signals.py | 52 | RSI/MACD/SMA/Bollinger interpréteurs, composite, résumé, intégration, endpoint |
| test_alerts.py | 48 | CRUD, évaluation, récurrence, endpoints |
| **test_news.py** | **43** | **Sentiment, impact, RSS, résumé, résilience, endpoints** |
| test_time_buckets.py | 17 | Timeframes, normalisation, buckets, fenêtres |
| **TOTAL** | **253** | **Tous passing ✅** |

---

## 5. Stack technique

### Backend
- **Python 3.12**
- FastAPI 0.109.2
- Uvicorn 0.27.1
- SQLAlchemy 2.0.25
- Pydantic 2.6.1 + pydantic-settings 2.1.0
- httpx 0.26.0 (client HTTP async + sync pour RSS)
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

## 7. Vision : BTC Insight → INFINI

Le projet suit une trajectoire en 3 étapes (détails : [ROADMAP_INFINI.md](./ROADMAP_INFINI.md)) :

| Étape | Nom | Versions | Description | Status |
|-------|-----|----------|-------------|--------|
| **1** | BTC Insight | v0.2 → v0.9 | Assistant visuel, pédagogique | ✅ **Complet** |
| **2** | INFINI v1 | v1.0 → v1.5 | Assistant intelligent, décisionnel | ⬜ Non commencé |
| **3** | INFINI v2 | v2.0+ | Robot autonome (sous contrôle humain) | ⬜ Non commencé |

**Position actuelle :** **Fin Étape 1** — BTC Insight complet (données + indicateurs + signaux + alertes + news)

---

## 8. Prochaine étape : v1.0 — Moteur de Décision (INFINI v1)

Le système passe de "informer" à "recommander" :

| Fichier à créer | Description |
|-----------------|-------------|
| `backend/app/services/decision_service.py` | Moteur de règles combinées |
| `backend/app/schemas/decision.py` | Schémas Scenario, Recommendation |
| `backend/app/api/routes/decision.py` | GET /market/decision |
| `backend/tests/test_decision.py` | Tests unitaires décision |
| `frontend/src/components/DecisionPanel.tsx` | Scénarios visuels + confiance |
| `frontend/src/hooks/useDecision.ts` | Hook React |

**Résultat attendu :** L'utilisateur voit des scénarios (Hausse 65% / Stable 25% / Baisse 10%) avec des recommandations explicables.

---

## 9. Ce qui n'est PAS encore fait

| Feature | Phase | Status |
|---------|-------|--------|
| ~~Moteur de signaux~~ | ~~v0.7~~ | ✅ **Livré** |
| ~~Alertes & Notifications~~ | ~~v0.8~~ | ✅ **Livré** |
| ~~News & Sentiment~~ | ~~v0.9~~ | ✅ **Livré** |
| Dark/Light mode | v1.x | ❌ Non commencé |
| Responsive mobile | v1.x | ❌ Non commencé |
| Persistance localStorage | v1.x | ❌ Non commencé |
| Moteur de Décision | v1.0 | ❌ Non commencé |
| Backtesting engine | v1.1 | ❌ Non commencé |
| Multi-Assets (ETH, SOL...) | v1.2 | ❌ Non commencé |
| Paper trading | v1.4 | ❌ Non commencé |
| Docker Compose | v1.5 | ❌ Non commencé |
| CI/CD GitHub Actions | v1.5 | ❌ Non commencé |
| Auth JWT | v1.5 | ❌ Non commencé |

---

## 10. Problèmes connus

| # | Problème | Sévérité | Notes |
|---|----------|----------|-------|
| 1 | Warnings pytest : coroutine `_fetch_and_store` non attendue dans certains tests mockés | ⚠️ Low | Ne bloque pas les tests, cosmétique |
| 2 | Vite build warning : chunk > 500 kB | ⚠️ Low | Suggestion de code-splitting |
| 3 | News RSS peuvent être indisponibles (timeout) | ⚠️ Low | Géré par fallback + cache TTL 5min |
