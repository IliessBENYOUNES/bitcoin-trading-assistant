# Changelog

All notable changes to this project will be documented in this file.

## [0.9.1] - 2026-04-02

### Added
- **Smart Alert Presets**: 12 stratégies d'alertes éprouvées activables en 1 clic
- `AlertPresets.tsx` : composant avec 3 catégories (Accumulation, Protection, Avancées)
- Stratégies basées sur les travaux de Wilder (RSI), Appel (MACD), Elder, Brandt
- RSI Survente (< 30), RSI Capitulation (< 20), MACD Haussier, Score Convergence (> 60)
- RSI Surachat (> 70), RSI Euphorie (> 80), MACD Baissier, Score Baissier (< -60)
- DCA Intelligent (Saylor), Euphorie Maximale (> 80), Capitulation Totale (< -80), RSI Pullback (< 45)
- Bouton "Tout activer" par catégorie ou global
- Détection automatique des presets déjà actifs (pas de doublons)
- Description détaillée avec contexte historique et preuves de performance pour chaque stratégie

### Changed
- AlertPanel intègre le composant AlertPresets entre le formulaire et la liste

### Technical
- 253 tests backend passing (aucun changement backend)
- Frontend tsc --noEmit sans erreur

## [0.9.0] - 2026-04-02

### Added
- **News & Sentiment System**: Collecte de news crypto avec analyse de sentiment et score d'impact
- `news_service.py` : collecteur RSS (CoinTelegraph, CoinDesk, Bitcoin Magazine) avec cache mémoire TTL 5min
- Classifieur de sentiment keyword-based (30+ mots bullish, 30+ mots bearish)
- Score d'impact (HIGH/MEDIUM/LOW) basé sur détection de mots-clés institutionnels/réglementaires
- Score de sentiment global -100/+100 pondéré par l'impact
- `news.py` schemas : NewsItem, NewsSentimentSummary, NewsResponse, SentimentType, ImpactLevel
- `GET /news` : liste des articles récents avec sentiment, impact et mots-clés (filtrable par sentiment)
- `GET /news/sentiment` : résumé du sentiment global uniquement
- `NewsPanel.tsx` : jauge de sentiment, liste d'articles avec liens, filtres, compteurs
- `useNews.ts` : hook React avec fetch + polling automatique (5min)
- Types TypeScript : NewsItem, NewsSentimentSummary, NewsResponse, SentimentType, ImpactLevel
- 43 nouveaux tests backend (sentiment, impact, RSS parsing, résilience, endpoints)
- Parser RSS intégré (pas de dépendance externe feedparser)

### Changed
- Dashboard intègre le NewsPanel sous AlertPanel
- Bouton "Actualiser" rafraîchit aussi les news
- `marketApi.ts` : ajout de `getNews()` et `getNewsSentiment()`
- `schemas/__init__.py` : export des schémas news
- `routes/__init__.py` : export du router news
- `main.py` : inclusion du router news
- `types/api.ts` + `types/index.ts` : barrel exports des types News

### Technical
- 253 tests backend passing (210 existants + 43 nouveaux)
- Frontend tsc --noEmit sans erreur
- Aucune dépendance ajoutée (utilise httpx existant pour RSS)
- Cache mémoire évite de surcharger les sources RSS
- Résilience : timeout 10s, fallback liste vide si source échoue

## [0.8.0] - 2026-04-02

### Added
- **Alert System**: Système complet d'alertes configurables avec évaluation automatique
- Modèle Alert en base (condition_type, operator, threshold, status, recurring)
- API CRUD complète : `GET/POST/PUT/DELETE /alerts` + `POST /alerts/check` + `GET /alerts/notifications`
- `alert_service.py` : CRUD + évaluation prix, RSI, MACD hist, score composite vs seuils
- `alert.py` schemas : AlertCreate, AlertUpdate, AlertResponse, AlertNotification, AlertCheckResponse
- Conditions supportées : `price`, `rsi`, `macd_hist`, `score` avec opérateurs `above` (≥) / `below` (≤)
- Alertes one-shot ou récurrentes (se réarment après déclenchement)
- `AlertPanel.tsx` : formulaire de création, liste des alertes, notifications polling
- `useAlerts.ts` : hook React avec CRUD + check + polling automatique (60s)
- Types TypeScript : AlertItem, AlertCreate, AlertNotification, AlertCheckResponse
- 48 nouveaux tests backend (CRUD, évaluation, récurrence, endpoints)
- `CLAUDE.md` : source unique de vérité pour l'agent IA (fusionne AGENT.md)

### Changed
- Dashboard intègre l'AlertPanel entre SignalPanel et IndicatorPanel
- Bouton "Actualiser" rafraîchit aussi les alertes
- Bouton "Fetch API" déclenche un check des alertes après le fetch
- `marketApi.ts` : ajout des fonctions `getAlerts()`, `createAlert()`, `deleteAlert()`, `checkAlerts()`
- `AGENT.md` : pointe désormais vers `CLAUDE.md` comme source de vérité
- `schemas/__init__.py` : export des schémas alert
- `models/__init__.py` : export du modèle Alert
- `main.py` : inclusion du router alerts

### Technical
- 210 tests backend passing (162 existants + 48 nouveaux)
- Frontend tsc --noEmit sans erreur
- Aucune dépendance ajoutée (utilise l'existant)

## [0.7.0] - 2026-04-02

### Added
- **Signal Engine**: Moteur d'interprétation des indicateurs techniques en signaux structurés
- `GET /market/signals` endpoint retournant signaux + score composite -100/+100
- `signal_service.py` : interpréteurs RSI, MACD, SMA, Bollinger → direction + force + message
- `signal.py` schemas : SignalItem, CompositeScore, ConfidenceLevel, SignalResponse
- Score composite avec confiance (high/medium/low) et consensus (unanimous/majority/divided)
- Résumé lisible auto-généré (ex: "RSI en surachat (72), MACD croisé baissier → Score -65")
- `SignalPanel.tsx` : jauge de score, liste signaux détaillés, badges consensus/confiance
- `useSignals.ts` : hook React pour fetch des signaux
- Types TypeScript : SignalItem, CompositeScore, MarketSignalsResponse
- 52 nouveaux tests backend (interpréteurs, composite, intégration, endpoint)

### Changed
- Dashboard intègre le SignalPanel au-dessus de l'IndicatorPanel
- Bouton "Actualiser" rafraîchit aussi les signaux
- `marketApi.ts` : ajout de `getSignals()`
- `schemas/__init__.py` : export des schémas signal

### Fixed
- Nettoyage du CHANGELOG.md (suppression des commandes shell en tête de fichier)

### Technical
- 162 tests backend passing (110 existants + 52 nouveaux)
- Frontend tsc --noEmit sans erreur
- Aucune dépendance ajoutée (utilise l'existant)

## [0.6.0] - 2026-04-01

### Added
- Dual-jobs scheduler (4h + 30m) avec resample automatique
- 4 timeframes supportés : 30m, 1h, 4h, 1d
- Frontend : sélecteur timeframe + historique, cap CoinGecko
- `StatusRow`, `DataFreshnessChip`, `SchedulerChip`
- Documentation CURRENT_STATE.md et AGENT.md

### Technical
- 110 tests backend passing

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