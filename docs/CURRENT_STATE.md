# 📊 Current State — Bitcoin Trading Assistant

> **Dernière mise à jour :** 8 avril 2026
> **Version :** v1.8.0
> **Branche :** `master`
> **Dernier commit :** docs: reality gap closure — honest documentation rewrite

---

## 1. Vue d'ensemble

Bitcoin Trading Assistant (alias **BTC Insight → INFINI v1**) est un outil d'aide à la lecture et à la **décision** sur le marché Bitcoin. Il collecte des données OHLCV depuis **Binance** (CoinGecko fallback), les agrège sur **14 timeframes**, calcule des indicateurs techniques, produit des signaux avec score composite, évalue des alertes, collecte des news avec analyse de sentiment, génère des recommandations explicables, valide empiriquement via backtesting et time-travel, gère le risque (SL/TP, kill switch), et simule le trading en temps réel via un paper trading multi-slot avec profils, levier auto, diagnostic, et trailing stop.

| Élément | Valeur |
|---------|--------|
| Version courante | **v1.8.0** |
| Backend | FastAPI 0.109 + SQLAlchemy 2.0 + Python 3.12 |
| Frontend | React 18 + TypeScript 5 + Vite 5 + MUI 5 + Framer Motion |
| Base de données | PostgreSQL (prod) / SQLite (tests) |
| Tests backend | **1053 tests**, tous passing ✅ |
| Frontend build | **tsc + vite build** sans erreur ✅ |
| Phase courante | **Étape 2 fonctionnellement livrée** — Reality gap closure en cours avant v2.0 |

### ⚠️ État de maturité honnête

L'Étape 2 (INFINI v1) est **fonctionnellement très avancée** côté simulation et observabilité. Cependant, **la validation opérationnelle n'est pas encore suffisante** pour justifier un passage vers l'exécution réelle (v2.0).

**Ce qui est solide :**
- Moteur de décision rule-based fonctionnel
- Backtesting et time-travel walk-forward
- Paper trading multi-slot avec profils et levier auto
- Diagnostic fréquence et opportunités manquées
- **Modèle de coûts de trading** (presets optimistic/realistic/stressed)
- **Audit de vérité** (expectancy nette, drawdown vérifié, impact levier/trailing, verdict)
- **Gate formelle v2.0** (8 critères objectifs, status READY/PARTIAL/NOT_READY)
- 1053 tests backend, tsc clean

**Ce qui manque structurellement avant v2.0 :**
- ❌ **Campagnes de validation (PaperRun)** : Pas de concept de "run" borné pour comparer rigoureusement des profils sur des périodes identiques.
- ❌ **Validation runtime prolongée** : Les métriques sont disponibles mais n'ont pas encore été validées sur un run de 7+ jours.
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
│   │   │   └── scheduler.py    # GET /scheduler/status, POST trigger
│   │   ├── models/             # Modèles SQLAlchemy (7 tables)
│   │   ├── schemas/            # Schémas Pydantic (12 fichiers)
│   │   ├── services/           # Logique métier (22 services)
│   │   ├── tasks/              # Jobs planifiés (APScheduler)
│   │   └── utils/              # Utilitaires
│   └── tests/                  # 1005+ tests pytest
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
| test_paper_trading.py | 68 |
| test_journal_and_profiles.py | 84 |
| test_diagnostic.py | 55 |
| test_reality_gap.py | 48 |
| **TOTAL** | **1053** ✅ |

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
| 2 | **Pas de campagnes de validation** | 🟠 Haute | PaperRun non encore implémenté |
| 3 | ~~Métriques non auditées~~ | ~~🟠 Haute~~ | ✅ Résolu v1.8.0 : TruthAuditService |
| 4 | Warnings pytest `_fetch_and_store` non awaited | ⚠️ Low | Cosmétique |
| 5 | Vite build warning chunk > 500 kB | ⚠️ Low | Code-splitting possible |

---

## 9. Comment lancer

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
