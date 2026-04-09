# 📊 Current State — Bitcoin Trading Assistant

> **Dernière mise à jour :** 9 avril 2026
> **Version :** v1.9.4
> **Branche :** `master`
> **Dernier commit :** fix(short-balance): corriger surcorrection short + réduire pertes + rendre shorts sélectifs

---

## 1. Vue d'ensemble

Bitcoin Trading Assistant (alias **BTC Insight → INFINI v1**) est un outil d'aide à la lecture et à la **décision** sur le marché Bitcoin. Il collecte des données OHLCV depuis **Binance** (CoinGecko fallback), les agrège sur **14 timeframes**, calcule des indicateurs techniques, produit des signaux avec score composite, évalue des alertes, collecte des news avec analyse de sentiment, génère des recommandations explicables, valide empiriquement via backtesting et time-travel, gère le risque (SL/TP, kill switch), et simule le trading en temps réel via un paper trading multi-slot avec profils, levier auto, diagnostic, et trailing stop.

| Élément | Valeur |
|---------|--------|
| Version courante | **v1.9.4** |
| Backend | FastAPI 0.109 + SQLAlchemy 2.0 + Python 3.12 |
| Frontend | React 18 + TypeScript 5 + Vite 5 + MUI 5 + Framer Motion |
| Base de données | PostgreSQL (prod) / SQLite (tests) |
| Tests backend | **1291 tests**, tous passing ✅ |
| Frontend build | **tsc + vite build** sans erreur ✅ |
| Phase courante | **v1.9.4 livré** — Correction surcorrection short + sélectivité + contrôle des pertes |

### ⚠️ État de maturité honnête

L'Étape 2 (INFINI v1) est **fonctionnellement très avancée** côté simulation et observabilité. Cependant, **la validation opérationnelle n'est pas encore suffisante** pour justifier un passage vers l'exécution réelle (v2.0).

**Ce qui est solide :**
- Moteur de décision rule-based fonctionnel
- Backtesting et time-travel walk-forward
- Paper trading multi-slot avec profils et levier auto
- Diagnostic fréquence et opportunités manquées
- **Modèle de coûts de trading** (presets optimistic/realistic/stressed)
- **Audit de vérité** (expectancy nette, drawdown vérifié, impact levier/trailing, verdict)
- **Audit scalping dédié** (exit distribution, trailing, score saturation, long/short, levier)
- **Scalping recalibré v1.8.1** (trailing stop élargi, scoring plus sélectif, levier conservateur, short amélioré)
- **Protection Reset UI** (bouton Full Reset séparé avec confirmation typed "RESET")
- **Gate formelle v2.0** (8 critères objectifs, status READY/PARTIAL/NOT_READY)
- **[v1.9] Campagnes de validation (PaperRun)** — démarrer/arrêter/comparer des runs avec métriques brut+net
- **[v1.9] Smart Cooldown** — cooldown contextuel (réduit après stale/trailing flat, allongé après SL/perte)
- **[v1.9] Cooldown Diagnostic** — visibilité du cooldown dans le diagnostic (délais, distribution, signaux perdus)
- **[v1.9] Learning Layer explicable** — LearningSignal + StrategyFeedback, patterns, suggestions shadow, promote/rollback
- **[v1.9.1] Anti-micro-PnL** — TP/SL recalibrés au-dessus du cost model (0.5%/0.4%), min_hold_seconds (30s), sortie signal adoucie
- **[v1.9.1] Smart Cooldown anti-churn** — pénalise les réentrées après trades flat (×1.5 au lieu de ×0.5)
- **[v1.9.1] Learning économique** — catégories useful/insignificant/churn/loss_useful/loss_destructive, coûts estimés, PnL net
- **[v1.9.1] Suggestions anti-churn** — détection automatique du taux de churn + insignifiants → suggestions d'ajustement
- **[v1.9.2] Audit resets complet** — contrat métier clair pour Full Reset (purge totale : trades, ticks, learning, feedback, runs, risk) et Reset Perte Jour (daily loss only). Confirmation backend obligatoire (confirm="RESET"). Réponse détaillée avec compteurs de purge. Refresh frontend cohérent de tous les panels après reset.
- **[v1.9.3] Short Optimization** — Réduction des trades short sans valeur économique, augmentation de la valeur par trade
  - **Short exit score threshold** : seuil configurable pour signal contraire (20 au lieu de 10) — les shorts respirent
  - **Short min score** : filtre économique des shorts (score minimum 25 pour ouvrir un short mean-reversion)
  - **Short min hold** : durée minimale spécifique aux shorts (60s vs 30s) — empêche les fermetures-éclair
  - **Convergence boost** : boost non-linéaire du score quand les indicateurs convergent, compression si divisés — casse l'homogénéité 69-71
  - **Run Value Audit** : service + endpoint `/audit/run-value` — diagnostic complet de la valeur économique par trade
  - **Learning Layer v2** : suggestions short-spécifiques (short_min_score, short_exit_score_threshold, short_min_hold_seconds)
  - **Dataset stats short** : métriques short_trades_useful, short_trades_insignificant, pct_short_economically_useful
- **[v1.9.4] Correction surcorrection short** — Rebalancement complet long/short
  - **Mean reversion ≥2 signaux** : exige 2 oscillateurs convergents (RSI overbought + StochRSI overbought) au lieu d'1 seul. En marché haussier, 1 RSI overbought est normal, pas un signal de short.
  - **Short exit score threshold 35** (était 20) : en marché haussier, score 20+ est permanent → les shorts se faisaient tuer immédiatement. Avec 35, il faut un vrai signal haussier fort.
  - **Short min score 40** (était 25) : les shorts à abs(score)<40 sont rejetés. Plus sélectif sur la qualité des shorts.
  - **Short min hold 90s** (était 60s) : plus de temps pour le pullback se développer.
  - **SL resserré 0.35%** (était 0.4%) : ratio R/R amélioré de 1.25:1 à 1.43:1 (TP 0.5% / SL 0.35%). Pertes mieux contrôlées.
  - **Tech score seuil 95** (était 90) : moins de faux positifs de surachat.
- 1291 tests backend, tsc clean

**Ce qui manque structurellement avant v2.0 :**
- ⚠️ **Validation runtime prolongée** : Les métriques sont disponibles mais n'ont pas encore été validées sur un run de 30+ trades.
- ⚠️ **Gate v2.0 = NOT_READY** : La gate existe mais le système n'a pas encore assez de trades pour passer les critères.

---

## 2. Architecture

```
bitcoin-trading-assistant/
├── CLAUDE.md                   # Source unique de vérité agent IA
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
│   │   │   ├── verification.py # /backtest/history/*, /backtest/verify, /backtest/walk-forward
│   │   │   ├── sentiment.py    # /sentiment/history/*
│   │   │   ├── alerts.py       # CRUD /alerts + POST /alerts/check
│   │   │   ├── news.py         # GET /news, GET /news/sentiment, /news/history/*
│   │   │   ├── risk.py         # /risk/config, status, evaluate, kill-switch, record-loss
│   │   │   ├── paper_trading.py # /paper/* (14 endpoints)
│   │   │   ├── learning.py     # /learning/* (12 endpoints - runs, learning, patterns)
│   │   │   └── scheduler.py    # GET /scheduler/status, POST trigger
│   │   ├── models/             # Modèles SQLAlchemy (10 tables)
│   │   ├── schemas/            # Schémas Pydantic (15 fichiers)
│   │   ├── services/           # Logique métier (25 services)
│   │   ├── tasks/              # Jobs planifiés (APScheduler)
│   │   └── utils/              # Utilitaires
│   └── tests/                  # 1163+ tests pytest
├── frontend/src/               # React 18 + TypeScript
│   ├── components/             # Panels UI
│   ├── hooks/                  # Custom hooks React
│   ├── api/                    # Appels API typés
│   ├── pages/                  # Dashboard
│   └── types/                  # Types TypeScript
└── docs/                       # Documentation
```

---

## 3. Fonctionnalités livrées (résumé)

### 3.1 Backend — Endpoints (56 au total)

| Groupe | Count | Exemples |
|--------|-------|----------|
| Health | 2 | `/health`, `/health/db` |
| Market | 7 | candles, fetch, gaps, indicators, signals, price, info |
| Decision | 1 | `/market/decision` |
| Backtest | 6 | run, history/load, range, verify, walk-forward, integrity |
| Sentiment | 4 | history/load, range, coverage, at-date |
| Alerts | 6 | CRUD + check + notifications |
| News | 6 | list, sentiment, history/persist, range, coverage, at-date |
| Risk | 7 | config CRUD, status, evaluate, kill-switch, record-loss |
| Paper Trading | 14 | account, status, tick, trades, metrics, close, journal, style, profile, diagnostic, missed-opps, leverage-analysis |
| Scheduler | 3 | status, trigger/4h, trigger/30m |

### 3.2 Multi-Slot Paper Trading (v1.7)

| Fonctionnalité | Status |
|----------------|--------|
| Positions parallèles (jusqu'à 3) | ✅ |
| Slots nommés (balanced, scalping, aggressive) | ✅ |
| Auto-mode multi-slot (balanced + scalping) | ✅ |
| Scalping mean reversion bidirectionnel | ✅ |
| SL/TP direction-aware (long + short) | ✅ |
| Per-slot cooldown et daily counter | ✅ |
| Trailing stop scalping (activation + trail) | ✅ |

### 3.3 Frontend — Composants principaux

Dashboard, PaperTradingPanel (multi-slot), JournalPanel, DiagnosticPanel, DecisionPanel, BacktestPanel, VerificationPanel, RiskPanel, SignalPanel, AlertPanel + Presets, NewsPanel, PriceTicker (WebSocket), CandlestickChart.

---

## 4. Tests

| Fichier | Tests |
|---------|-------|
| test_health.py | 3 |
| test_indicators.py | 35 |
| test_market.py | 4 |
| test_scheduler.py | 16 |
| test_scheduler_dual_jobs.py | 15 |
| test_scheduler_resample_1d.py | 7 |
| test_scheduler_resample_1h.py | 6 |
| test_scheduler_news.py | 11 |
| test_cryptocompare.py | 30 |
| test_signals.py | 88 |
| test_alerts.py | 48 |
| test_news.py | 43 |
| test_decision.py | 122 |
| test_backtest.py | 31 |
| test_verification.py | 79 |
| test_binance_and_router.py | 89 |
| test_news_history.py | 33 |
| test_sentiment_history.py | 42 |
| test_risk.py | 57 |
| test_price_service.py | 15 |
| test_time_buckets.py | 24 |
| test_paper_trading.py | 91 |
| test_journal_and_profiles.py | 84 |
| test_diagnostic.py | 55 |
| test_reality_gap.py | 48 |
| **TOTAL** | **1223** ✅ |

---

## 5. Vision : BTC Insight → INFINI

| Étape | Versions | Description | Status |
|-------|----------|-------------|--------|
| **1** BTC Insight | v0.2 → v0.9 | Assistant visuel, pédagogique | ✅ Complet |
| **2** INFINI v1 | v1.0 → v1.7 | Assistant décisionnel + simulation | ✅ Fonctionnel |
| **2b** Reality Gap | v1.8 | Coûts, campagnes, audit, gate v2.0 | 🔄 En cours |
| **3** INFINI v2 | v2.0+ | Robot autonome (sous contrôle humain) | ⬜ Bloqué par 2b |
| **4** INFINI v3 | v3.0+ | Modèle ML convergent | ⬜ Futur |

---

## 6. Prochaine étape : v1.8 — Reality Gap Closure

> **Objectif** : Fermer l'écart entre la sophistication fonctionnelle et la vérité opérationnelle.
> **Doctrine** : Pas d'exécution réelle tant que le reality gap n'est pas comblé.

| Sous-phase | Description | Status |
|------------|-------------|--------|
| v1.8.1 | TradingCostModel (frais, spread, slippage, presets) | ✅ Livré |
| v1.8.2 | PaperRun — Campagnes de validation organisées | ⬜ Futur |
| v1.8.3 | TruthAudit — Audit de vérité des métriques | ✅ Livré |
| v1.8.4 | V2Gate — Gate formelle avant exécution réelle | ✅ Livré |

---

## 7. Ce qui n'est PAS encore fait

| Feature | Priorité | Status |
|---------|----------|--------|
| **Modèle de coûts de trading** | 🔴 CRITIQUE | ✅ v1.8.0 |
| **Audit de vérité métriques** | 🔴 Haute | ✅ v1.8.0 |
| **Gate formelle v2.0** | 🔴 Haute | ✅ v1.8.0 |
| **Campagnes de validation (PaperRun)** | 🟠 Moyenne | ⬜ Futur |
| Robot autonome (connecteur exchange) | Haute | ⬜ v2.0 (bloqué) |
| Docker Compose / CI/CD / Auth JWT | Moyenne | ⬜ Futur |
| Multi-Assets (ETH, SOL...) | Basse | ⬜ Futur |

---

## 8. Problèmes connus

| # | Problème | Sévérité | Notes |
|---|----------|----------|-------|
| 1 | ~~Pas de modèle de coûts de trading~~ | ~~🔴 CRITIQUE~~ | ✅ Résolu v1.8.0 : TradingCostModel avec presets optimistic/realistic/stressed |
| 2 | ~~Pas de campagnes de validation~~ | ~~🟠 Haute~~ | ✅ Résolu v1.9.0 : PaperRun |
| 3 | ~~Métriques non auditées~~ | ~~🟠 Haute~~ | ✅ Résolu v1.8.0 : TruthAuditService |
| 4 | Warnings pytest `_fetch_and_store` non awaited | ⚠️ Low | Cosmétique |
| 5 | Vite build warning chunk > 500 kB | ⚠️ Low | Code-splitting possible |
| 6 | ~~Diagnostic "93% bloqué par positions" persistant après fermeture~~ | ~~🔴 Haute~~ | ✅ Résolu v1.9.2 : full reset purge toutes les tables + diagnostic filtre par date création compte |
| 7 | ~~P&L / RiskConfig non remis à zéro au reset~~ | ~~🔴 Haute~~ | ✅ Résolu v1.9.2 : full reset remet tout à zéro (daily_loss, kill_switch, portfolio_value, learning, runs) |
| 8 | ~~Full reset ne purgeait pas learning/feedback/runs~~ | ~~🔴 Haute~~ | ✅ Résolu v1.9.2 : full reset purge learning_signal, strategy_feedback, paper_run |
| 9 | ~~JournalPanel/DiagnosticPanel non rafraîchis après reset~~ | ~~🔴 Haute~~ | ✅ Résolu v1.9.2 : tradeVersion incrémenté après reset → refresh propagé |
| 10 | ~~RiskPanel non rafraîchi après full reset~~ | ~~🟠 Moyenne~~ | ✅ Résolu v1.9.2 : RiskPanel reçoit refreshTrigger |
| 11 | ~~Pas de confirmation backend pour full reset~~ | ~~🟠 Moyenne~~ | ✅ Résolu v1.9.2 : confirm="RESET" obligatoire |

---

## 9. Contrats Métier des Resets (v1.9.2)

### 9.1 Reset Perte Jour (`POST /risk/reset-daily-loss`)

**Périmètre strict — ne touche qu'au risque journalier :**

| Action | Détail |
|--------|--------|
| ✅ Remet `daily_loss_current` à 0.0 | Compteur de perte journalière remis à zéro |
| ✅ Met à jour `daily_loss_reset_date` | Aujourd'hui |
| ✅ Désactive kill switch SI "Perte journalière" | Seulement si `kill_switch_reason` contient "Perte journalière" |
| ✅ Nettoie `kill_switch_triggered_at` | Seulement si le kill switch est désactivé |
| ❌ NE touche PAS aux trades | Aucun trade supprimé |
| ❌ NE touche PAS au capital | Le compte reste identique |
| ❌ NE touche PAS au learning | Les learning_signal restent |
| ❌ NE touche PAS aux runs | Les paper_run restent |
| ❌ NE touche PAS aux tick_logs | Les tick_activity_log restent |
| ❌ NE désactive PAS un kill switch manuel | Si raison != "Perte journalière", il reste actif |

### 9.2 Full Reset (`POST /paper/account/reset`)

**Purge totale — repart de zéro :**

| Table | Action | Justification |
|-------|--------|---------------|
| `paper_trade` | 🗑️ Supprimé | Les trades sont liés à l'ancien compte |
| `paper_account` | 🗑️ Supprimé + recréé | Le compte est recréé avec le nouveau capital |
| `tick_activity_log` | 🗑️ Supprimé | Les ticks référencent l'ancien account_id, pollueraient le diagnostic |
| `learning_signal` | 🗑️ Supprimé | Les trade_id deviennent orphelins, les patterns sont obsolètes |
| `strategy_feedback` | 🗑️ Supprimé | Les suggestions sont basées sur des données mortes |
| `paper_run` | 🗑️ Supprimé | Les campagnes sont liées à l'ancien état |
| `risk_config` | 🔄 Réinitialisé | daily_loss=0, kill_switch=off, portfolio_value=nouveau capital |

**Sécurité :**
- Exige `confirm: "RESET"` dans le body de la requête
- Refus 400 si absent ou incorrect
- Retourne un `FullResetResponse` avec compteurs de purge détaillés

**Refresh frontend :**
- `tradeVersion` incrémenté → JournalPanel + DiagnosticPanel rafraîchis
- `onResetComplete` propagé → RiskPanel rafraîchi
- `lastTick` remis à null
- Auto-mode arrêté

---

## 10. Comment lancer

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v

# TypeScript check
cd frontend && npx tsc --noEmit
```
