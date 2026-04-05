# 📊 Current State — Bitcoin Trading Assistant

> **Dernière mise à jour :** 5 avril 2026
> **Version :** v1.2.3a
> **Branche :** `master`
> **Dernier commit :** feat(news-history): persist RSS news in DB with model, service, endpoints, 33 tests

---

## 1. Vue d'ensemble

Bitcoin Trading Assistant (alias **BTC Insight → INFINI v1**) est un outil d'aide à la lecture et à la **décision** sur le marché Bitcoin. Il collecte des données OHLCV depuis **Binance (prioritaire)** et CoinGecko (fallback), les stocke en base, les agrège sur **14 timeframes**, calcule des indicateurs techniques, **les interprète en signaux structurés avec un score composite**, **surveille des alertes configurables**, **collecte les news crypto avec analyse de sentiment**, affiche un **prix BTC temps réel via WebSocket Binance**, **produit des recommandations explicables via un moteur de décision combinant analyse technique et sentiment**, **valide empiriquement les décisions via un moteur de backtesting**, et **vérifie les prédictions sur l'historique profond via un système de time-travel backtest + walk-forward**.

| Élément | Valeur |
|---------|--------|
| Version courante | **v1.2.3a** |
| Backend | FastAPI 0.109 + SQLAlchemy 2.0 + Python 3.12 |
| Frontend | React 18 + TypeScript 5 + Vite 5 + MUI 5 + Framer Motion |
| Base de données | PostgreSQL (prod) / SQLite (tests) |
| Tests backend | **620 tests**, tous passing ✅ |
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
│   │   │   ├── decision.py     # GET /market/decision
│   │   │   ├── backtest.py     # POST /backtest/run
│   │   │   ├── verification.py # ← NOUVEAU v1.1.1 — /backtest/history/*, /backtest/verify, /backtest/walk-forward
│   │   │   ├── sentiment.py    # ← NOUVEAU v1.2.1 — /sentiment/history/load, range, coverage, at-date
│   │   │   ├── alerts.py       # CRUD /alerts + POST /alerts/check
│   │   │   ├── news.py         # GET /news, GET /news/sentiment
│   │   │   └── scheduler.py    # GET /scheduler/status, POST trigger
│   │   ├── models/
│   │   │   ├── candle.py       # Modèle Candle (OHLCV + timeframe)
│   │   │   ├── alert.py        # Modèle Alert (conditions + status)
│   │   │   └── sentiment_history.py # ← NOUVEAU v1.2.1 — Modèle SentimentHistory (sentiment quotidien)
│   │   │   └── news_history.py     # ← NOUVEAU v1.2.3a — Modèle NewsHistory (articles RSS persistés)
│   │   ├── schemas/
│   │   │   ├── candle.py       # Schémas Pydantic candle
│   │   │   ├── signal.py       # Schémas SignalItem, CompositeScore, SignalResponse
│   │   │   ├── decision.py     # Scenario, RuleResult, Recommendation, DecisionResponse
│   │   │   ├── backtest.py     # BacktestConfig, BacktestMetrics, BacktestResponse
│   │   │   ├── verification.py # ← NOUVEAU v1.1.1 — HistoryLoadConfig, VerificationResult, WalkForwardResult
│   │   │   ├── sentiment.py    # ← NOUVEAU v1.2.1 — SentimentLoadConfig, SentimentAtDateResponse, etc.
│   │   │   ├── alert.py        # AlertCreate, AlertResponse, AlertCheck
│   │   │   └── news.py         # NewsItem, NewsSentimentSummary, NewsResponse
│   │   ├── services/
│   │   │   ├── verification_service.py # ← NOUVEAU v1.1.1 — Time-travel + walk-forward
│   │   │   ├── history_loader_service.py # ← NOUVEAU v1.1.1 — Chargement historique Binance 2017→now
│   │   │   ├── sentiment_history_service.py # ← NOUVEAU v1.2.1 — Fear & Greed historique + requête par date
│   │   │   ├── news_history_service.py  # ← NOUVEAU v1.2.3a — Persistance news RSS en DB
│   │   │   ├── backtest_service.py    # Moteur de replay historique
│   │   │   ├── decision_service.py    # Moteur de décision (règles + scénarios)
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
│   └── tests/                  # 481 tests pytest
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
│       ├── test_decision.py
│       ├── test_backtest.py            # 31 tests backtesting
│       ├── test_verification.py        # ← NOUVEAU v1.1.1 — 33 tests vérification historique
│       ├── test_binance_and_router.py
│       └── test_time_buckets.py
│
├── frontend/                   # React SPA
│   └── src/
│       ├── App.tsx
│       ├── pages/
│       │   └── Dashboard.tsx   # Page principale (14 TF + 15 durées + live price + décision + backtest)
│       ├── components/
│       │   ├── BacktestPanel.tsx        # Métriques + journal trades + config
│       │   ├── VerificationPanel.tsx    # ← NOUVEAU v1.1.1 — Charger historique + vérifier + walk-forward
│       │   ├── DecisionPanel.tsx        # Scénarios + recommandation + règles
│       │   ├── CandlestickChart.tsx
│       │   ├── IndicatorPanel.tsx
│       │   ├── SignalPanel.tsx
│       │   ├── AlertPanel.tsx
│       │   ├── AlertPresets.tsx
│       │   ├── NewsPanel.tsx
│       │   ├── GlowingCard.tsx
│       │   ├── SectionHeader.tsx
│       │   ├── PriceTicker.tsx
│       │   ├── StatusRow.tsx
│       │   ├── StatusBar.tsx
│       │   ├── DataFreshnessChip.tsx
│       │   ├── SchedulerChip.tsx
│       │   ├── PriceCard.tsx
│       │   └── ErrorBoundary.tsx
│       ├── hooks/
│       │   ├── useBacktest.ts           # Hook backtesting
│       │   ├── useDecision.ts
│       │   ├── useCandles.ts
│       │   ├── useIndicators.ts
│       │   ├── useMarketGaps.ts
│       │   ├── useSchedulerStatus.ts
│       │   ├── useSignals.ts
│       │   ├── useAlerts.ts
│       │   ├── useNews.ts
│       │   └── useLivePrice.ts
│       ├── api/
│       │   ├── client.ts
│       │   └── marketApi.ts          # + runBacktest()
│       └── types/
│           ├── api.ts               # + Backtest types
│           └── index.ts
│
└── docs/
    ├── CURRENT_STATE.md        # ← CE FICHIER
    ├── ROADMAP.md
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
| POST | `/market/candles/fetch` | Fetch manuel (14 timeframes, jours fractionnels) | ✅ |
| GET | `/market/candles/gaps` | Analyse qualité données (fraîcheur + complétude) | ✅ |
| GET | `/market/indicators` | Indicateurs techniques (RSI, MACD, SMA, Bollinger) | ✅ |
| GET | `/market/signals` | Signaux de trading + score composite | ✅ |
| GET | `/market/decision` | Moteur de décision (scénarios + recommandation) | ✅ |
| **POST** | **`/backtest/run`** | **Backtesting — replay historique + métriques** | **✅ v1.1** |
| **POST** | **`/backtest/history/load`** | **Chargement historique profond depuis Binance 2017→now** | **✅ NOUVEAU v1.1.1** |
| **GET** | **`/backtest/history/range`** | **Plage de dates disponible en base** | **✅ NOUVEAU v1.1.1** |
| **POST** | **`/backtest/verify`** | **Vérification ponctuelle à une date (time-travel)** | **✅ NOUVEAU v1.1.1** |
| **POST** | **`/backtest/walk-forward`** | **Analyse walk-forward complète (précision globale) + mode comparaison** | **✅ v1.1.1 + MAJ v1.2.2** |
| **GET** | **`/backtest/history/integrity`** | **Vérification intégrité données (complétude, gaps, grade qualité)** | **✅ NOUVEAU v1.2.2** |
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
| **POST** | **`/sentiment/history/load`** | **Charger le Fear & Greed Index (~2900 jours)** | **✅ NOUVEAU v1.2.1** |
| **GET** | **`/sentiment/history/range`** | **Plage de dates sentiment disponible** | **✅ NOUVEAU v1.2.1** |
| **GET** | **`/sentiment/history/coverage`** | **Couverture globale sentiment** | **✅ NOUVEAU v1.2.1** |
| **GET** | **`/sentiment/history/at-date`** | **Sentiment à une date donnée** | **✅ NOUVEAU v1.2.1** |
| **POST** | **`/news/history/persist`** | **Persister les news RSS actuelles en base** | **✅ NOUVEAU v1.2.3a** |
| **GET** | **`/news/history/range`** | **Plage de dates des news en base** | **✅ NOUVEAU v1.2.3a** |
| **GET** | **`/news/history/coverage`** | **Couverture news par source** | **✅ NOUVEAU v1.2.3a** |
| **GET** | **`/news/history/at-date`** | **Articles et sentiment agrégé à une date** | **✅ NOUVEAU v1.2.3a** |

### 3.2 Backend — Services

| Service | Description | Status |
|---------|-------------|--------|
| **Verification Service** | **Time-travel backtest + walk-forward + comparaison prédiction/réalité** | **✅ NOUVEAU v1.1.1** |
| **History Loader Service** | **Chargement historique profond Binance 2017→now, pagination, upsert idempotent** | **✅ NOUVEAU v1.1.1** |
| **News History Service** | **Persistance news RSS en DB, scoring par article, sentiment agrégé quotidien** | **✅ NOUVEAU v1.2.3a** |
| **Backtest Service** | **Replay historique des décisions + simulation de trades + métriques** | **✅ v1.1** |
| **Decision Service** | Moteur de décision combinant signaux techniques + sentiment → scénarios + recommandation | ✅ |
| **Binance Service** | Client HTTP async Binance, **14 intervalles natifs** | ✅ |
| **DataSource Router** | Routeur intelligent Binance / CoinGecko | ✅ |
| **CoinGecko Service** | Client HTTP async (fallback) | ✅ |
| **Indicator Service** | RSI(14), MACD(12,26,9), SMA(20,50,200), Bollinger(20,2) | ✅ |
| **Signal Service** | Interprétation indicateurs → signaux + score composite | ✅ |
| **Alert Service** | CRUD alertes + évaluation conditions | ✅ |
| **News Service** | Collecte RSS + classification sentiment + score d'impact | ✅ |
| **Resample Service** | Agrégation OHLCV 14 timeframes, idempotent | ✅ |
| **Scheduler Dual-Jobs** | Job 4h + Job 30m via DataSourceRouter | ✅ |

### 3.3 Backend — Moteur de Backtesting (v1.1)

| Fonctionnalité | Description | Status |
|----------------|-------------|--------|
| **Replay historique** | Itère candle par candle en recalculant indicateurs/signaux/décision | ✅ |
| **Simulation de positions** | Achat quand action=acheter, vente quand action=vendre | ✅ |
| **Warmup indicateurs** | Skip des premières candles pour laisser les indicateurs converger | ✅ |
| **Métriques complètes** | Win rate, Sharpe, max drawdown, profit factor, PnL net | ✅ |
| **Buy & Hold benchmark** | Comparaison avec stratégie passive | ✅ |
| **Equity curve** | Capital + drawdown à chaque pas de temps | ✅ |
| **Journal de trades** | Liste détaillée avec entrée, sortie, PnL, durée, raison | ✅ |
| **Warning suroptimisation** | Alerte si <10 trades ou Sharpe >3.0 | ✅ |
| **Clôture automatique** | Position ouverte en fin de backtest fermée automatiquement | ✅ |
| **Résumé lisible** | Synthèse texte des résultats | ✅ |

### 3.3b Backend — Vérification Historique / Time-Travel (v1.2 — amélioré)

| Fonctionnalité | Description | Status |
|----------------|-------------|--------|
| **Chargement historique profond** | Binance 2017→maintenant, pagination automatique, upsert idempotent | ✅ |
| **Time-travel verify** | Se positionner à n'importe quelle date, exécuter le moteur avec seulement les données antérieures | ✅ |
| **Comparaison prédiction/réalité** | Compare la recommandation du modèle avec la variation réelle à 7j, 30j, 90j | ✅ |
| **Walk-forward analysis** | Test automatique sur des dizaines/centaines de dates espacées régulièrement | ✅ |
| **Seuils adaptatifs** | **Seuils hausse/baisse/stable calculés à partir de la volatilité récente** | **✅ NOUVEAU v1.2** |
| **Score de qualité** | **Score 0-100 par prédiction (au lieu de binaire correct/incorrect)** | **✅ NOUVEAU v1.2** |
| **Directional accuracy** | **Le signe du score correspond-il à la direction réelle du marché ?** | **✅ NOUVEAU v1.2** |
| **Métriques haute confiance** | **Précision séparée pour les signaux forts (|score|>25)** | **✅ NOUVEAU v1.2** |
| **Profitabilité** | **% de prédictions où suivre le signal aurait été profitable** | **✅ NOUVEAU v1.2** |
| **Qualité globale** | **Score qualité moyen pondéré sur tous les horizons** | **✅ NOUVEAU v1.2** |
| **Mode 100% technique** | En historique, sentiment non dispo → mode dégradé documenté | ✅ |
| **Intégrité des données** | **Détection des gaps, complétude %, grade qualité (EXCELLENT/GOOD/WARNING/CRITICAL)** | **✅ NOUVEAU v1.2.2** |
| **Mode comparaison** | **Walk-forward : technique seul vs technique + sentiment, delta accuracy/qualité, verdict** | **✅ NOUVEAU v1.2.2** |

### 3.4 Backend — Moteur de Décision (v1.0)

| Fonctionnalité | Description | Status |
|----------------|-------------|--------|
| **8 règles combinées** | RSI overbought/oversold, MACD cross, SMA trend, sentiment convergence | ✅ |
| **3 scénarios** | Hausse / Stable / Baisse avec probabilités normalisées (somme = 1.0) | ✅ |
| **Recommandation** | Acheter / Vendre / Attendre avec confiance et explication en français | ✅ |
| **Score combiné** | Pondération 70% technique + 30% sentiment | ✅ |
| **Mode dégradé** | Fonctionne sans sentiment (100% technique si RSS échoue) | ✅ |
| **Raisons explicables** | Liste des raisons de la décision en langage naturel | ✅ |

### 3.5 Backend — Timeframes supportés (v0.9.6)

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

### 3.6 Backend — Moteur de Signaux (v1.2 — amélioré)

| Interpréteur | Logique | Status |
|--------------|---------|--------|
| **RSI** | Surachat (>70), survente (<30), zones intermédiaires | ✅ |
| **MACD** | Croisement haussier/baissier, **seuils en % du prix** (corrige biais $3k→$100k) | ✅ **MAJ v1.2** |
| **SMA** | Position prix vs SMA20/50/200, comptage au-dessus/dessous | ✅ |
| **Bollinger** | Position dans les bandes, surachat/survente aux extrêmes | ✅ |
| **ADX(14)** | **Force de la tendance : ADX≥25=tendance forte, ADX<20=range (filtre faux signaux)** | **✅ NOUVEAU v1.2** |
| **Volume** | **Confirmation par volume vs SMA(20) : volume élevé=confirmation, faible=méfiance** | **✅ NOUVEAU v1.2** |
| **Score composite** | Agrégation pondérée -100/+100, **ADX module la confiance, Volume module le score** | ✅ **MAJ v1.2** |
| **Résumé lisible** | Génération automatique d'un résumé en français | ✅ |

### 3.7 Backend — Système d'Alertes (v0.8)

| Fonctionnalité | Description | Status |
|----------------|-------------|--------|
| **Modèle Alert** | Table SQLAlchemy (condition_type, operator, threshold, status, recurring) | ✅ |
| **CRUD complet** | Créer, lire, modifier, supprimer des alertes | ✅ |
| **Évaluation** | Évalue prix, RSI, MACD hist, score composite vs seuils | ✅ |
| **Conditions** | above (≥) et below (≤) | ✅ |
| **Récurrence** | Alertes one-shot ou récurrentes | ✅ |
| **Notifications** | Génération de messages de notification structurés | ✅ |

### 3.8 Backend — News & Sentiment (v0.9)

| Fonctionnalité | Description | Status |
|----------------|-------------|--------|
| **Collecte RSS** | 3 sources (CoinTelegraph, CoinDesk, Bitcoin Magazine) | ✅ |
| **Classifieur sentiment** | Keyword-based (bullish/bearish/neutral) | ✅ |
| **Score d'impact** | Détection mots-clés (HIGH/MEDIUM/LOW) | ✅ |
| **Cache mémoire** | TTL 5 minutes pour éviter de surcharger les sources | ✅ |
| **Résilience** | Timeout 10s, fallback liste vide si source échoue | ✅ |
| **Score global** | Agrégation pondérée -100/+100 avec impact | ✅ |
| **Filtre sentiment** | Filtrer par positive/negative/neutral | ✅ |

### 3.9 Frontend — Contrôles utilisateur

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
- **Panel backtesting avec config, métriques, journal de trades** ← v1.1
- **Panel vérification historique avec chargement, date picker, walk-forward** ← NOUVEAU v1.1.1

### 3.10 Frontend — Composants (v1.1.1)

| Composant | Description | Status |
|-----------|-------------|--------|
| **VerificationPanel** | **Charger historique + intégrité données + vérifier date + walk-forward + mode comparaison** | **✅ v1.1.1 + MAJ v1.2.2** |
| **BacktestPanel** | **Config + métriques (PnL, Sharpe, DD, Win Rate) + journal trades** | **✅ v1.1** |
| **DecisionPanel** | Scénarios visuels + recommandation + règles collapsibles | ✅ |
| **QuickMetricsBar** | **Barre KPIs rapides (Décision, Score, Tendance, Signaux, Sentiment)** | **✅ NOUVEAU** |
| **Dashboard** | Page principale avec 14 TF + 15 durées + live price + décision + backtest + vérification + FAB + raccourcis clavier + footer | ✅ **MAJ** |
| **CandlestickChart** | Graphique chandeliers (Lightweight Charts) | ✅ |
| **IndicatorPanel** | Affichage RSI, MACD, SMA, Bollinger avec couleurs | ✅ |
| **SignalPanel** | Jauge score composite, liste signaux, consensus | ✅ |
| **AlertPanel** | Formulaire création + liste alertes + notifications | ✅ |
| **AlertPresets** | 12 stratégies éprouvées en 1 clic | ✅ |
| **NewsPanel** | News crypto + sentiment + filtres + jauge | ✅ |
| **PriceTicker** | Prix BTC LIVE WebSocket Binance + variation 24h + high/low + volume | ✅ |
| **DataFreshnessChip** | Chip FRESH / STALE / GAPS + gestion NO_DATA | ✅ |
| **StatusRow** | Barre de statut (fraîcheur + scheduler) | ✅ |
| **SchedulerChip** | Chip scheduler ON / OFF | ✅ |
| **ErrorBoundary** | Protection crash graphique | ✅ |

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
| test_signals.py | **71** | **RSI/MACD/SMA/Bollinger/ADX/Volume interpréteurs, MACD relatif, composite v1.2, résumé** |
| test_alerts.py | 48 | CRUD, évaluation, récurrence, endpoints |
| test_news.py | 43 | Sentiment, impact, RSS, résumé, résilience, endpoints |
| test_decision.py | 75 | Règles, scénarios, recommandation, intégration, endpoint |
| test_backtest.py | 31 | Schémas, métriques, intégration DB, endpoints, edge cases |
| **test_verification.py** | **82** | **Range, verify, walk-forward, correctness v1.2, directional match, quality score, seuils adapatifs, integrity, compare mode, endpoints** |
| test_binance_and_router.py | 89 | Binance 14 intervalles, DataSourceRouter, combinaisons |
| **test_news_history.py** | **33** | **Modèle, scoring, persist idempotent, queries, range, coverage, endpoints** |
| test_time_buckets.py | 17 | Timeframes, normalisation, buckets, fenêtres |
| **TOTAL** | **620** | **Tous passing ✅** |

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

| Étape | Nom | Versions | Description | Status |
|-------|-----|----------|-------------|--------|
| **1** | BTC Insight | v0.2 → v0.9 | Assistant visuel, pédagogique | ✅ **Complet** |
| **2** | INFINI v1 | v1.0 → v1.6 | Assistant intelligent, décisionnel (BTC-first) | 🔄 **En cours (v1.1.1 livré)** |
| **3** | INFINI v2 | v2.0+ | Robot autonome (sous contrôle humain) | ⬜ Non commencé |

**Position actuelle :** **Étape 2 en cours** — Moteur de décision (v1.0) + Backtesting (v1.1) + Vérification historique (v1.1.1) + Sentiment historique (v1.2.1) + Intégrité & Compare mode (v1.2.2) + Persistance news RSS (v1.2.3a) livrés, prochaine étape : CryptoCompare News historique (v1.2.3b)

---

## 8. Prochaine étape : v1.2.3b — CryptoCompare News historique

> **Objectif** : Ajouter CryptoCompare comme 4ᵉ source de news historiques (depuis 2015, gratuit) pour enrichir le corpus de sentiment en DB.

Le système enrichit son moteur de décision avec des news historiques :

| Fonctionnalité | Description |
|-----------------|-------------|
| CryptoCompare News API | Client pour récupérer les news crypto historiques depuis 2015 (gratuit) |
| Intégration sentiment multi-source | Combiner Fear & Greed + sentiment news pour un score plus robuste |
| Walk-forward multi-source | Tester technique seul vs technique + FnG vs technique + FnG + news |

---

## 9. Ce qui n'est PAS encore fait

| Feature | Phase | Status |
|---------|-------|--------|
| ~~Moteur de signaux~~ | ~~v0.7~~ | ✅ **Livré** |
| ~~Alertes & Notifications~~ | ~~v0.8~~ | ✅ **Livré** |
| ~~News & Sentiment~~ | ~~v0.9~~ | ✅ **Livré** |
| ~~Moteur de Décision~~ | ~~v1.0~~ | ✅ **Livré** |
| ~~Backtesting engine~~ | ~~v1.1~~ | ✅ **Livré** |
| ~~Vérification historique~~ | ~~v1.1.1~~ | ✅ **Livré** |
| ~~Sentiment historique Fear & Greed~~ | ~~v1.2.1~~ | ✅ **Livré** |
| ~~Intégrité données + mode comparaison~~ | ~~v1.2.2~~ | ✅ **Livré** |
| ~~Persistance news RSS en DB~~ | ~~v1.2.3a~~ | ✅ **Livré** |
| CryptoCompare News historique | v1.2.3b | ❌ **Prochaine étape** |
| Risk management engine | v1.3 | ❌ Non commencé |
| Paper trading | v1.4 | ❌ Non commencé |
| Docker Compose | v1.5 | ❌ Non commencé |
| CI/CD GitHub Actions | v1.5 | ❌ Non commencé |
| Auth JWT | v1.5 | ❌ Non commencé |
| Multi-Assets (ETH, SOL...) | v1.6 | ❌ Après validation BTC |

---

## 10. Problèmes connus

| # | Problème | Sévérité | Notes |
|---|----------|----------|-------|
| 1 | Warnings pytest : coroutine `_fetch_and_store` non attendue dans certains tests mockés | ⚠️ Low | Ne bloque pas les tests, cosmétique |
| 2 | Vite build warning : chunk > 500 kB | ⚠️ Low | Suggestion de code-splitting |
| 3 | News RSS peuvent être indisponibles (timeout) | ⚠️ Low | Géré par fallback + cache TTL 5min |
| 4 | Backtest sans frais/slippage | ⚠️ Low | Résultats optimistes, documenté dans le code |
| ~~5~~ | ~~Vérification marquait toutes les prédictions INCORRECT~~ | ~~🔴 High~~ | ~~✅ Corrigé v1.1.2 + v1.2.0 — seuils adapatifs + ADX + quality score~~ |
