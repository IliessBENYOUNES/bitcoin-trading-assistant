# 📊 Current State — Bitcoin Trading Assistant

> **Dernière mise à jour :** 2 avril 2026
> **Version :** v0.9.6
> **Branche :** `master`
> **Dernier commit :** feat(trading): all 14 Binance timeframes + live WebSocket price + fractional durations

---

## 1. Vue d'ensemble

Bitcoin Trading Assistant (alias **BTC Insight**) est un outil d'aide à la lecture du marché Bitcoin. Il collecte des données OHLCV depuis **Binance (prioritaire)** et CoinGecko (fallback), les stocke en base, les agrège sur **14 timeframes**, calcule des indicateurs techniques, **les interprète en signaux structurés avec un score composite**, **surveille des alertes configurables**, **collecte les news crypto avec analyse de sentiment**, affiche un **prix BTC temps réel via WebSocket Binance**, et affiche tout dans un dashboard interactif.

| Élément | Valeur |
|---------|--------|
| Version courante | **v0.9.6** |
| Backend | FastAPI 0.109 + SQLAlchemy 2.0 + Python 3.12 |
| Frontend | React 18 + TypeScript 5 + Vite 5 + MUI 5 + Framer Motion |
| Base de données | PostgreSQL (prod) / SQLite (tests) |
| Tests backend | **342 tests**, tous passing ✅ |
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
│   │   │   ├── news.py         # GET /news, GET /news/sentiment
│   │   │   └── scheduler.py    # GET /scheduler/status, POST trigger
│   │   ├── models/
│   │   │   ├── candle.py       # Modèle Candle (OHLCV + timeframe)
│   │   │   └── alert.py        # Modèle Alert (conditions + status)
│   │   ├── schemas/
│   │   │   ├── candle.py       # Schémas Pydantic candle
│   │   │   ├── signal.py       # Schémas SignalItem, CompositeScore, SignalResponse
│   │   │   ├── alert.py        # AlertCreate, AlertResponse, AlertCheck
│   │   │   └── news.py         # NewsItem, NewsSentimentSummary, NewsResponse
│   │   ├── services/
│   │   │   ├── binance_service.py     # Client HTTP Binance (14 intervalles natifs)
│   │   │   ├── data_source_router.py  # Routeur Binance/CoinGecko
│   │   │   ├── coingecko_service.py   # Client HTTP CoinGecko (fallback)
│   │   │   ├── indicator_service.py   # RSI, MACD, SMA, Bollinger
│   │   │   ├── signal_service.py      # Interprétation → signaux + score composite
│   │   │   ├── alert_service.py       # CRUD alertes + évaluation conditions
│   │   │   ├── news_service.py        # RSS + sentiment + impact
│   │   │   └── resample_service.py    # Agrégation multi-timeframe (14 niveaux)
│   │   ├── tasks/
│   │   │   └── scheduler.py    # APScheduler dual-jobs (4h + 30m) via DataSourceRouter
│   │   └── utils/
│   │       ├── time_buckets.py # Alignement UTC 14 timeframes, fenêtres glissantes
│   │       └── db_upsert.py    # Upsert dialect-aware
│   └── tests/                  # 342 tests pytest
│       ├── test_health.py
│       ├── test_indicators.py
│       ├── test_market.py
│       ├── test_scheduler.py
│       ├── test_scheduler_dual_jobs.py
│       ├── test_scheduler_resample_1d.py
│       ├── test_scheduler_resample_1h.py
│       ├── test_signals.py
│       ├── test_alerts.py
│       ├── test_news.py
│       ├── test_binance_and_router.py  # 66+ combinaisons paramétrées
│       └── test_time_buckets.py
│
├── frontend/                   # React SPA
│   └── src/
│       ├── App.tsx
│       ├── pages/
│       │   └── Dashboard.tsx   # Page principale (14 TF + 15 durées + live price)
│       ├── components/
│       │   ├── CandlestickChart.tsx   # Graphique Lightweight Charts
│       │   ├── IndicatorPanel.tsx     # Panel RSI/MACD/SMA/Bollinger
│       │   ├── SignalPanel.tsx        # Jauge score, signaux, consensus
│       │   ├── AlertPanel.tsx         # Formulaire + liste alertes
│       │   ├── AlertPresets.tsx       # 12 stratégies éprouvées en 1 clic
│       │   ├── NewsPanel.tsx          # News + sentiment + filtres
│       │   ├── GlowingCard.tsx        # Card animée premium
│       │   ├── SectionHeader.tsx      # Titre section avec gradient
│       │   ├── PriceTicker.tsx        # ← MAJ v0.9.6 — Prix BTC LIVE WebSocket + 24h stats
│       │   ├── StatusRow.tsx          # Barre de statut connectée
│       │   ├── StatusBar.tsx          # Barre de statut UI
│       │   ├── DataFreshnessChip.tsx  # ← MAJ v0.9.6 — Gestion NO_DATA
│       │   ├── SchedulerChip.tsx      # Chip ON/OFF scheduler
│       │   ├── PriceCard.tsx          # Carte prix courant
│       │   └── ErrorBoundary.tsx      # Error boundary graphique
│       ├── hooks/
│       │   ├── useCandles.ts          # Fetch candles API
│       │   ├── useIndicators.ts       # Fetch indicateurs API
│       │   ├── useMarketGaps.ts       # Fetch gaps API
│       │   ├── useSchedulerStatus.ts  # Fetch scheduler status
│       │   ├── useSignals.ts          # Fetch signaux API
│       │   ├── useAlerts.ts           # CRUD + check alertes
│       │   ├── useNews.ts             # Fetch news + polling
│       │   └── useLivePrice.ts        # ← NOUVEAU v0.9.6 — WebSocket Binance temps réel
│       ├── api/
│       │   ├── client.ts             # Axios instance
│       │   └── marketApi.ts          # API calls typées
│       └── types/
│           ├── api.ts               # Types TypeScript (+ MarketGapsResponse optionnel)
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
| POST | `/market/candles/fetch` | Fetch manuel (14 timeframes, jours fractionnels) | ✅ **MAJ v0.9.6** |
| GET | `/market/candles/gaps` | Analyse qualité données (fraîcheur + complétude) | ✅ **MAJ v0.9.6** |
| GET | `/market/indicators` | Indicateurs techniques (RSI, MACD, SMA, Bollinger) | ✅ **MAJ v0.9.6** |
| GET | `/market/signals` | Signaux de trading + score composite | ✅ **MAJ v0.9.6** |
| GET | `/market/price` | Prix courant | ✅ |
| GET | `/market/info` | Info marché | ✅ |
| GET | `/alerts` | Lister les alertes | ✅ |
| POST | `/alerts` | Créer une alerte | ✅ |
| GET | `/alerts/{id}` | Récupérer une alerte | ✅ |
| PUT | `/alerts/{id}` | Modifier une alerte | ✅ |
| DELETE | `/alerts/{id}` | Supprimer une alerte | ✅ |
| POST | `/alerts/check` | Évaluer les alertes actives | ✅ |
| GET | `/alerts/notifications` | Alertes récemment déclenchées | ✅ |
| GET | `/news` | Liste des news crypto avec sentiment | ✅ |
| GET | `/news/sentiment` | Résumé du sentiment global | ✅ |
| GET | `/scheduler/status` | État scheduler + dernier résultat par job | ✅ |
| POST | `/scheduler/trigger/4h` | Trigger manuel job 4h | ✅ |
| POST | `/scheduler/trigger/30m` | Trigger manuel job 30m | ✅ |

### 3.2 Backend — Services

| Service | Description | Status |
|---------|-------------|--------|
| **Binance Service** | Client HTTP async Binance, **14 intervalles natifs** (1m→1w), pagination auto | ✅ **MAJ v0.9.6** |
| **DataSource Router** | Routeur intelligent Binance (prioritaire) / CoinGecko (fallback) | ✅ |
| **CoinGecko Service** | Client HTTP async, mapping symboles, gestion timeouts (fallback) | ✅ |
| **Indicator Service** | RSI(14), MACD(12,26,9), SMA(20,50,200), Bollinger(20,2), **jours fractionnels** | ✅ **MAJ v0.9.6** |
| **Signal Service** | Interprétation indicateurs → signaux + score composite -100/+100, **jours fractionnels** | ✅ **MAJ v0.9.6** |
| **Alert Service** | CRUD alertes + évaluation conditions (prix, RSI, MACD, score) | ✅ |
| **News Service** | Collecte RSS + classification sentiment + score d'impact | ✅ |
| **Resample Service** | Agrégation OHLCV **14 timeframes**, idempotent via upsert | ✅ **MAJ v0.9.6** |
| **Scheduler Dual-Jobs** | Job 4h + Job 30m via DataSourceRouter | ✅ |

### 3.3 Backend — Timeframes supportés (v0.9.6)

| Timeframe | Source | Intervalle |
|-----------|--------|------------|
| **1m** | Binance direct | 1 minute |
| **3m** | Binance direct | 3 minutes |
| **5m** | Binance direct | 5 minutes |
| **15m** | Binance direct | 15 minutes |
| **30m** | Binance direct (CoinGecko fallback) | 30 minutes |
| **1h** | Binance direct ou Resample 30m→1h | 1 heure |
| **2h** | Binance direct | 2 heures |
| **4h** | Binance direct ou Resample | 4 heures |
| **6h** | Binance direct | 6 heures |
| **8h** | Binance direct | 8 heures |
| **12h** | Binance direct | 12 heures |
| **1d** | Binance direct ou Resample 4h→1d | 1 jour |
| **3d** | Binance direct | 3 jours |
| **1w** | Binance direct | 1 semaine |

> **v0.9.6 : 14 timeframes × 15 durées = toutes les combinaisons possibles**

### 3.4 Backend — Moteur de Signaux (v0.7)

| Interpréteur | Logique | Status |
|--------------|---------|--------|
| **RSI** | Surachat (>70), survente (<30), zones intermédiaires | ✅ |
| **MACD** | Croisement haussier/baissier, force basée sur écart | ✅ |
| **SMA** | Position prix vs SMA20/50/200, comptage au-dessus/dessous | ✅ |
| **Bollinger** | Position dans les bandes, surachat/survente aux extrêmes | ✅ |
| **Score composite** | Agrégation pondérée -100/+100, confiance, consensus | ✅ |
| **Résumé lisible** | Génération automatique d'un résumé en français | ✅ |

### 3.5 Backend — Système d'Alertes (v0.8)

| Fonctionnalité | Description | Status |
|----------------|-------------|--------|
| **Modèle Alert** | Table SQLAlchemy (condition_type, operator, threshold, status, recurring) | ✅ |
| **CRUD complet** | Créer, lire, modifier, supprimer des alertes | ✅ |
| **Évaluation** | Évalue prix, RSI, MACD hist, score composite vs seuils | ✅ |
| **Conditions** | above (≥) et below (≤) | ✅ |
| **Récurrence** | Alertes one-shot ou récurrentes | ✅ |
| **Notifications** | Génération de messages de notification structurés | ✅ |

### 3.6 Backend — News & Sentiment (v0.9)

| Fonctionnalité | Description | Status |
|----------------|-------------|--------|
| **Collecte RSS** | 3 sources (CoinTelegraph, CoinDesk, Bitcoin Magazine) | ✅ |
| **Classifieur sentiment** | Keyword-based (bullish/bearish/neutral) | ✅ |
| **Score d'impact** | Détection mots-clés (HIGH/MEDIUM/LOW) | ✅ |
| **Cache mémoire** | TTL 5 minutes pour éviter de surcharger les sources | ✅ |
| **Résilience** | Timeout 10s, fallback liste vide si source échoue | ✅ |
| **Score global** | Agrégation pondérée -100/+100 avec impact | ✅ |
| **Filtre sentiment** | Filtrer par positive/negative/neutral | ✅ |

### 3.7 Frontend — Composants

| Composant | Description | Status |
|-----------|-------------|--------|
| **Dashboard** | Page principale avec **14 TF + 15 durées** + live price | ✅ **MAJ v0.9.6** |
| **CandlestickChart** | Graphique chandeliers (Lightweight Charts) | ✅ |
| **IndicatorPanel** | Affichage RSI, MACD, SMA, Bollinger avec couleurs | ✅ |
| **SignalPanel** | Jauge score composite, liste signaux, consensus | ✅ |
| **AlertPanel** | Formulaire création + liste alertes + notifications | ✅ |
| **AlertPresets** | 12 stratégies éprouvées en 1 clic | ✅ |
| **NewsPanel** | News crypto + sentiment + filtres + jauge | ✅ |
| **PriceTicker** | **Prix BTC LIVE WebSocket Binance + variation 24h + high/low + volume** | ✅ **MAJ v0.9.6** |
| **DataFreshnessChip** | Chip FRESH / STALE / GAPS + **gestion NO_DATA** | ✅ **MAJ v0.9.6** |
| **StatusRow** | Barre de statut (fraîcheur + scheduler) | ✅ |
| **SchedulerChip** | Chip scheduler ON / OFF | ✅ |
| **ErrorBoundary** | Protection crash graphique | ✅ |

### 3.8 Frontend — Contrôles utilisateur

- Sélecteur timeframe : **1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w** (14 options)
- Sélecteur durée : **1h30, 3h, 6h, 12h, 1j, 2j, 3j, 5j, 7j, 14j, 30j, 60j, 90j, 180j, 1an** (15 options)
- **Prix BTC temps réel via WebSocket Binance** (~1 update/seconde)
- Variation 24h, High/Low 24h, Volume 24h dans le PriceTicker
- Bouton "Fetch API" appel direct `/market/candles/fetch` (tous timeframes)
- Bouton "Actualiser" pour refresh local (inclut signaux + alertes + news)
- Affichage résultat fetch (inserted, updated, duplicates, resample)
- Panel signaux avec jauge, liste, confiance et consensus
- Panel alertes avec formulaire, liste, notifications polling
- Panel news avec jauge sentiment, liste articles, filtres, liens cliquables

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
| test_news.py | 43 | Sentiment, impact, RSS, résumé, résilience, endpoints |
| **test_binance_and_router.py** | **89** | **Binance 14 intervalles, DataSourceRouter fallback, 66 combinaisons, resample** |
| test_time_buckets.py | 17 | Timeframes, normalisation, buckets, fenêtres |
| **TOTAL** | **342** | **Tous passing ✅** |

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
- Framer Motion 11.x

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

**Position actuelle :** **Fin Étape 1** — BTC Insight complet (données + indicateurs + signaux + alertes + news + prix live)

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
