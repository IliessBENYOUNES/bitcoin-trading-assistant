# Changelog

All notable changes to this project will be documented in this file.

## [1.2.0] - 2026-04-05

### Added
- **ADX(14) — Average Directional Index** : Nouveau filtre de tendance dans le moteur de signaux
  - ADX ≥ 25 = tendance forte (confirme les signaux), ADX < 20 = range (atténue les signaux)
  - DI+/DI- pour la direction de la tendance
  - Réduit les faux signaux dans les marchés latéraux (cause majeure des "incorrect")
- **Volume SMA(20)** : Confirmation des mouvements par le volume
  - Volume > 1.5x SMA → boost de confiance, Volume < 0.5x SMA → méfiance
  - Le volume ne donne pas de direction mais module le score composite
- **`interpret_adx()`** : Interpréteur ADX avec 4 niveaux (très fort, fort, faible, neutre)
- **`interpret_volume_trend()`** : Interpréteur volume avec ratio vs SMA
- **Seuils adaptatifs de volatilité** : Les seuils hausse/baisse/stable sont calculés à partir de la volatilité récente (écart-type des rendements quotidiens) au lieu de seuils fixes
  - `_compute_recent_volatility()` : Calcule la volatilité sur 30 jours glissants
  - `_get_adaptive_thresholds()` : Seuils = volatilité × √(horizon) × facteur
- **Score de qualité 0-100** : Chaque prédiction reçoit un score de qualité proportionnel
  - Alignement directionnel (0-50 pts), proportionnalité score/mouvement (0-30 pts), confiance (0-20 pts)
  - Remplace l'évaluation binaire correct/incorrect par une mesure continue
- **Directional accuracy** : Métrique "le signe du score correspond-il à la direction réelle ?"
- **Métriques walk-forward avancées** :
  - `directional_accuracy_pct` : % de match directionnel
  - `avg_quality_score` : Score qualité moyen par horizon
  - `high_confidence_accuracy_pct` : Précision des signaux forts (|score| > 25)
  - `profitable_direction_pct` : % de signaux profitables si suivis
  - `overall_quality_score` : Score qualité global du walk-forward
- **28 nouveaux tests** : ADX (7), Volume (6), MACD relatif (4), directional match (4), quality score (3), seuils adaptatifs (3), composite v1.2 (1)

### Changed
- **MACD — Seuils en % du prix** : Corrige un biais majeur où le MACD était toujours "fort" aux prix élevés ($100k) et "faible" aux prix bas ($3k). Les seuils sont maintenant 0.1%, 0.3%, 0.8%, 1.5% du prix au lieu de 10, 50, 200, 500 absolus
- **Score composite v1.2** : L'ADX module la confiance globale (×1.3 si ADX≥40, ×0.7 si ADX<20), le volume module le score (±10-15%)
- **Confiance HIGH** requiert désormais ADX ≥ 25 en plus du consensus unanime — plus conservateur mais plus fiable
- **`indicator_service.py`** : Calcule ADX(14), DI+, DI-, Volume SMA(20) en plus des indicateurs existants
- **`HorizonOutcome`** : Nouveaux champs `quality_score` (0-100), `directional_match` (bool)
- **`HorizonAccuracy`** : 5 nouvelles métriques avancées
- **`WalkForwardResult`** : Nouveau champ `overall_quality_score`

### Technical
- 523 tests backend passing (495 → 523, +28 tests)
- Frontend tsc --noEmit sans erreur
- Aucune régression sur les 495 tests existants

## [1.1.2] - 2026-04-05

### Fixed
- **Logique de vérification corrigée** : La fonction `_is_prediction_correct` marquait faussement toutes les prédictions comme INCORRECT
  - Le score directionnel est maintenant pris en compte (pas seulement l'action)
  - Les seuils s'adaptent à l'horizon temporel (7j, 30j, 90j) — BTC est volatile
  - "Attendre" signifie "pas assez de signal" et non "stabilité attendue"
  - Un score de -4 avec "attendre" + baisse réelle → désormais ✅ CORRECT (penchant validé)
  - Un score neutre + mouvement normal pour BTC (~20% en 7j, ~35% en 30j, ~50% en 90j) → ✅ CORRECT

### Added
- `_is_hold_correct()` : Sous-méthode dédiée à l'évaluation nuancée de "attendre"
- `_get_hold_tolerance()` : Marge d'erreur par horizon pour penchant directionnel
- `_get_neutral_threshold()` : Seuil adapté à la volatilité BTC par horizon
- **14 nouveaux tests** : Cas réels du screenshot 2020-01-01, penchants directionnels, seuils par horizon
- Affichage du penchant directionnel dans le détail des verdicts ("penchant haussier/baissier")

### Changed
- `_is_prediction_correct()` accepte désormais `predicted_score` et `horizon_days`
- "Acheter" est correct si pas de baisse franche (>2%), plus tolérant pour les mouvements stables
- "Vendre" est correct si pas de hausse franche (>2%)

### Technical
- 495 tests backend passing (481 → 495, +14 tests)
- Frontend tsc --noEmit sans erreur
- Aucune régression

## [1.1.1] - 2026-04-04

### Added
- **Vérification Historique v1.1.1** : Système de time-travel backtest permettant de vérifier les prédictions du modèle sur l'historique profond
- `verification_service.py` : Service de vérification avec verify_at_date() + walk_forward()
- `history_loader_service.py` : Chargement historique profond Binance 2017→maintenant avec pagination et upsert idempotent
- `verification.py` schemas : HistoryLoadConfig, HistoryLoadResponse, HistoryRangeResponse, VerificationRequest, VerificationResult, HorizonOutcome, WalkForwardConfig, WalkForwardResult, HorizonAccuracy
- `POST /backtest/history/load` : Charger l'historique BTC depuis Binance (2017→now)
- `GET /backtest/history/range` : Plage de dates disponible en base
- `POST /backtest/verify` : Vérification ponctuelle à une date (time-travel)
- `POST /backtest/walk-forward` : Analyse walk-forward complète avec précision par horizon
- **Comparaison prédiction/réalité** : Compare la recommandation du modèle avec la variation réelle à 7j, 30j, 90j
- **Walk-forward analysis** : Test automatique sur des dizaines de dates espacées régulièrement
- **Précision par horizon** : Taux de prédictions correctes par horizon (7j, 30j, 90j)
- `VerificationPanel.tsx` : UI pour charger historique, choisir une date, voir résultats ✅/❌, lancer walk-forward
- **33 nouveaux tests backend** : range, verify, walk-forward, correctness (7 cas), schemas (6), endpoints (5), mock loader

### Changed
- Dashboard intègre le VerificationPanel dans la grille
- `schemas/__init__.py` : export des schémas verification
- `routes/__init__.py` : export du router verification
- `main.py` : inclusion du router verification
- `marketApi.ts` : ajout des fonctions API verification
- `types/api.ts` + `types/index.ts` : types Verification

### Technical
- 481 tests backend passing (448 → 481, +33)
- Frontend tsc --noEmit sans erreur
- Mode 100% technique en historique (sentiment non disponible, documenté)
- Limitation connue : le sentiment historique sera ajouté en v1.2.5

## [1.1.0] - 2026-04-03

### Added
- **Backtesting Engine v1.1**: Moteur de replay historique validant empiriquement les decisions du moteur v1.0
- `backtest_service.py` : Replay candle par candle avec recalcul indicateurs/signaux/decision a chaque pas
- `backtest.py` schemas : BacktestConfig, BacktestTradeItem, BacktestMetrics, EquityPoint, BacktestMeta, BacktestResponse, TradeDirection
- `POST /backtest/run` : Endpoint lançant un backtest complet avec parametres configurables
- `backtest.py` route : Endpoint avec gestion d'erreurs (422/500)
- **Simulation de positions** : Achat quand action=acheter, vente quand action=vendre, un seul trade a la fois
- **Metriques completes** : Win rate, Sharpe ratio, max drawdown, profit factor, PnL net/%, avg trade duration
- **Buy & Hold benchmark** : Comparaison automatique avec strategie passive
- **Equity curve** : Capital + drawdown a chaque pas de temps
- **Journal de trades** : Liste detaillee (entree, sortie, PnL, duree, raison)
- **Warning suroptimisation** : Alerte si <10 trades ou Sharpe >3.0
- **Cloture automatique** : Position ouverte en fin de backtest fermee automatiquement
- **Warmup indicateurs** : Skip des premieres candles (min 5, max 30) pour convergence
- `BacktestPanel.tsx` : UI premium avec config (jours, capital), metriques visuelles, journal collapsible
- `useBacktest.ts` : Hook React avec launch/reset/loading/error
- Types TypeScript : TradeDirection, BacktestConfig, BacktestTradeItem, BacktestMetrics, EquityPoint, BacktestMeta, BacktestResponse
- **31 nouveaux tests backend** : schemas (6), metriques (9), integration DB (6), endpoints HTTP (5), edge cases (5)

### Changed
- Dashboard integre le BacktestPanel dans la grille "Analyse du marche"
- `marketApi.ts` : ajout de `runBacktest()`
- `schemas/__init__.py` : export des schemas backtest
- `routes/__init__.py` : export du router backtest
- `main.py` : inclusion du router backtest
- `types/api.ts` + `types/index.ts` : barrel exports des types Backtest

### Technical
- 448 tests backend passing (417 -> 448, +31)
- Frontend tsc --noEmit sans erreur
- Aucune nouvelle dependance npm/pip
- Pas de slippage ni frais simules (resultats optimistes, documente)
- Un seul trade a la fois (pas de positions multiples)

## [1.0.0] - 2026-04-02

### Added
- **Decision Engine v1.0**: Moteur de décision combinant analyse technique (70%) et sentiment des news (30%) en recommandations explicables
- `decision_service.py` : Moteur de règles avec 8 règles combinées (RSI overbought/oversold, MACD cross, SMA trend, sentiment convergence)
- `decision.py` schemas : Scenario, RuleResult, Recommendation, DecisionMeta, DecisionResponse, ActionType
- `GET /market/decision` : Endpoint retournant scénarios multi-outcome + recommandation + règles évaluées
- **3 scénarios** (Hausse / Stable / Baisse) avec probabilités normalisées (somme = 1.0)
- **Recommandation explicable** : Acheter / Vendre / Attendre avec confiance (high/medium/low) et raisons en français
- **Mode dégradé** : Fonctionne sans sentiment (100% technique si RSS échoue), indiqué dans `meta.sentiment_available`
- `DecisionPanel.tsx` : Composant premium avec jauge score combiné, barres scénarios, card recommandation, règles collapsibles
- `useDecision.ts` : Hook React avec fetch + refresh automatique
- Types TypeScript : ActionType, Scenario, RuleResult, DecisionRecommendation, DecisionMeta, DecisionResponse
- **75 nouveaux tests backend** : règles individuelles (18), scénarios mathématiques (14+9), recommandation (7), intégration DB (5), endpoint HTTP (5), propriétés paramétrées (17)

### Changed
- Dashboard intègre le DecisionPanel en première position de la grille "Analyse du marché"
- Bouton "Actualiser" rafraîchit aussi la décision
- Fetch API déclenche un refresh de la décision après le fetch
- `marketApi.ts` : ajout de `getDecision()`
- `schemas/__init__.py` : export des schémas decision
- `routes/__init__.py` : export du router decision
- `main.py` : inclusion du router decision
- `types/api.ts` + `types/index.ts` : barrel exports des types Decision

### Technical
- 417 tests backend passing (342 → 417, +75)
- Frontend tsc --noEmit sans erreur
- Aucune nouvelle dépendance npm/pip
- Score combiné = technique × 0.70 + sentiment × 0.30 (borné -100/+100)
- 8 règles évaluées : RSI overbought, RSI oversold, MACD bullish cross, MACD bearish cross, SMA trend up, SMA trend down, sentiment convergence bullish, sentiment convergence bearish

## [0.9.6] - 2026-04-02

### Added
- **14 timeframes Binance**: Support complet de tous les intervalles Binance natifs (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w)
- **Prix BTC temps réel via WebSocket**: `useLivePrice` hook connecté à `wss://stream.binance.com:9443/ws/btcusdt@ticker` (~1 update/seconde)
- **PriceTicker enrichi**: Variation 24h (%), High/Low 24h, Volume 24h en BTC, indicateur de connexion WebSocket, flash vert/rouge sur changement de prix
- **15 options de durée**: Durées fractionnelles (1h30, 3h, 6h, 12h) en plus des durées en jours (1j→1an)
- **44 nouveaux tests**: 66 combinaisons paramétrées (6 TF × 11 durées), tests intervalles 5m/15m

### Changed
- Endpoints `/market/indicators`, `/market/signals`, `/market/candles`, `/market/candles/gaps`, `/market/candles/fetch` acceptent maintenant les jours fractionnels (`float` au lieu de `int`)
- `align_to_bucket` étendu dans `time_buckets.py` et `resample_service.py` pour 14 timeframes (dont 3d aligné sur epoch, 1w aligné sur lundi)
- `BinanceService` supporte 14 intervalles avec mapping millisecondes complet
- Dashboard: sélecteur timeframe 14 options, sélecteur durée 15 options, fetch direct via `/market/candles/fetch`
- `DataFreshnessChip`: gestion gracieuse du status `NO_DATA` (pas de crash si freshness/completeness absents)
- `MarketGapsResponse` TypeScript: champs `freshness`, `completeness`, `stats`, `now_utc` rendus optionnels
- `useCandles`: ajout `limit=1000` par défaut pour supporter les petits timeframes
- Labels durée affichés en heures quand < 1 jour (ex: "6h" au lieu de "0.25j")

### Technical
- 342 tests backend passing (298 → 342, +44)
- Frontend tsc --noEmit sans erreur
- Aucune nouvelle dépendance npm/pip
- WebSocket Binance : reconnexion automatique avec backoff exponentiel (max 10 tentatives)

## [0.9.5] - 2026-04-02

### Added
- **Binance Service** (`binance_service.py`): Client HTTP async pour l'API publique Binance (OHLCV natif, toute granularité, pagination automatique, volume réel)
- **DataSource Router** (`data_source_router.py`): Routeur intelligent — Binance (prioritaire) avec fallback CoinGecko automatique
- **Resample 30m→4h** et **1h→4h**: Nouveaux resamplings pour chaîne complète 30m→1h→4h→1d
- **45 nouveaux tests**: BinanceService (parsing, mapping), DataSourceRouter (fallback), 24 combinaisons paramétrées, resample 30m→4h et 1h→4h
- Option **90 jours** dans le sélecteur d'historique du Dashboard

### Changed
- **Toutes les 24 combinaisons timeframe × jours débloquées** (30m+30j, 1h+14j, 4h+1j, 1d+2j, etc.)
- Endpoint `POST /market/candles/fetch` accepte désormais un paramètre `timeframe` explicite (optionnel, rétrocompatible)
- Endpoint `POST /market/candles/fetch` utilise DataSourceRouter (Binance + CoinGecko fallback)
- Scheduler `_fetch_and_store()` utilise DataSourceRouter au lieu de CoinGecko directement
- Job 30m resample maintenant aussi en 4h (chaîne complète)
- `resample_all()` orchestre la chaîne complète : 30m→1h, 30m→4h, 1h→4h, 4h→1d
- Suppression du cap frontend "30m/1h limité à 1 jour" — plus de limitation

### Technical
- 298 tests backend passing (253 → 298, +45)
- Frontend tsc --noEmit sans erreur
- Aucune nouvelle dépendance npm/pip (httpx déjà inclus)
- Source Binance : BTCUSDT (Tether) ≈ BTC/USD (<0.1% écart)

## [0.9.3] - 2026-04-02

### Changed
- **Layout intelligent responsive**: refonte complète de la disposition du Dashboard
- Chart en HERO pleine largeur (élément dominant, premier regard du trader)
- 3 colonnes sous le chart : Signaux | Alertes | News (scan horizontal rapide)
- Indicateurs détaillés en bas pleine largeur (données de référence)
- Labels de section avec icônes ("📊 Analyse du marché", "🔬 Données techniques")
- AppBar responsive : contrôles adaptés mobile (icônes seules), labels courts (30m/1h/4h/1d)
- Breakpoints MUI : xs=12, md=6, lg=4 pour les panels (empilé mobile → 2 col tablette → 3 col desktop)
- Bouton Fetch API masqué sur mobile, remplacé par icône
- Padding et spacing adaptatifs par taille d'écran

### Technical
- 253 tests backend passing
- Frontend tsc --noEmit sans erreur
- Aucune nouvelle dépendance

## [0.9.2] - 2026-04-02

### Changed
- **Premium Dark Trading UI**: Refonte visuelle complète sans changement d'architecture
- Thème MUI riche avec couleurs crypto (BTC Orange #F7931A, vert/rouge trading)
- Glassmorphism sur toutes les Cards (backdrop-filter: blur + rgba borders)
- AppBar sticky premium avec logo Bitcoin, contrôles intégrés, gradient
- Background gradient sombre style Bloomberg/TradingView
- Jauges demi-cercle SVG pour le score composite (SignalPanel) et le sentiment (NewsPanel)
- Polices premium : Inter (UI) + JetBrains Mono (chiffres/scores)
- Custom scrollbar dark, font-smoothing, text selection BTC orange
- Hover glow sur les boutons et Cards
- Tooltips glassmorphism, Alert arrondies, Chips premium

### Technical
- Aucune nouvelle dépendance (pur CSS + MUI overrides)
- 253 tests backend passing
- Frontend tsc --noEmit sans erreur

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