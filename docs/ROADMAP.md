# 🗺️ Roadmap — Bitcoin Trading Assistant → INFINI

> **Dernière mise à jour :** 2 avril 2026
> **Document de référence détaillé :** [ROADMAP_INFINI.md](./ROADMAP_INFINI.md) (976 lignes)

---

## Vision : 3 étapes vers INFINI

```
┌─────────────────────────────────────────────────────────────────────┐
│  ÉTAPE 1 — BTC Insight (v0.2 → v0.9) ✅ COMPLET                    │
│  Assistant visuel, modulaire, pédagogique                           │
│  ├── Données marché temps réel          ✅ Livré (v0.2-v0.6)       │
│  ├── Indicateurs techniques             ✅ Livré (v0.3)            │
│  ├── Signaux & scoring                  ✅ Livré (v0.7)            │
│  ├── Alertes visuelles                  ✅ Livré (v0.8)            │
│  └── News & sentiment                   ✅ Livré (v0.9)            │
│                                                                      │
│  ÉTAPE 2 — INFINI v1 (v1.0 → v1.5)                                 │
│  Assistant intelligent, décisionnel                                  │
│  ├── Moteur de décision / règles        ✅ Livré (v1.0)             │
│  ├── Backtesting engine                 ⬜ Prochaine étape (v1.1)   │
│  ├── Multi-assets                       ⬜ Planifié (v1.2)         │
│  ├── Risk management engine             ⬜ Planifié (v1.3)         │
│  ├── Paper trading                      ⬜ Planifié (v1.4)         │
│  └── Production (Docker, CI/CD, Auth)   ⬜ Planifié (v1.5)         │
│                                                                      │
│  ÉTAPE 3 — INFINI v2 (v2.0+)                                       │
│  Assistant autonome (sous contrôle humain)                           │
│  ├── Exécution automatisée              ⬜ Futur                    │
│  ├── Mode fantôme (observer sans agir)  ⬜ Futur                    │
│  ├── Apprentissage de stratégies        ⬜ Futur                    │
│  └── Kill switch & audit trail          ⬜ Futur                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## État actuel : v1.0.0 — Moteur de Décision (Livré) ✅

| Composant | Status |
|-----------|--------|
| Backend dual-jobs scheduler | ✅ Complet |
| 14 timeframes (1m → 1w) | ✅ Complet |
| Resample multi-timeframe | ✅ Complet |
| Frontend Dashboard | ✅ Complet |
| Indicateurs (RSI, MACD, SMA, Bollinger) | ✅ Complet |
| Chart Lightweight Charts | ✅ Complet |
| Signal Engine (interprétation + score) | ✅ Complet (v0.7) |
| SignalPanel (jauge + liste + consensus) | ✅ Complet (v0.7) |
| Alert System (CRUD + check + notifications) | ✅ Complet (v0.8) |
| AlertPanel (formulaire + liste + polling) | ✅ Complet (v0.8) |
| News Service (RSS + sentiment + impact) | ✅ Complet (v0.9) |
| NewsPanel (jauge + articles + filtres) | ✅ Complet (v0.9) |
| **Decision Engine (règles + scénarios + recommandation)** | **✅ Complet (v1.0)** |
| **DecisionPanel (jauge + scénarios + recommandation)** | **✅ Complet (v1.0)** |
| 417 tests backend | ✅ Tous passing |

---

## ✅ LIVRÉ : v0.7 — Moteur de Signaux (Niveau 2)

> Le système interprète les indicateurs et génère des signaux structurés.

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 7.1 `signal_service.py` | 🔴 Haute | 4h | Interpréter RSI/MACD/SMA/Bollinger → signaux structurés | ✅ |
| 7.2 Schéma `SignalResponse` | 🔴 Haute | 1h | SignalItem, CompositeScore, consensus | ✅ |
| 7.3 `GET /market/signals` | 🔴 Haute | 2h | Endpoint API retournant signaux + score | ✅ |
| 7.4 Score composite | 🔴 Haute | 3h | Agrégation -100/+100, confiance, convergence | ✅ |
| 7.5 `test_signals.py` | 🔴 Haute | 4h | Tests unitaires pour chaque interpréteur (52 tests) | ✅ |
| 7.6 `SignalPanel.tsx` | 🟡 Moyenne | 4h | Jauge, liste signaux, badge consensus | ✅ |
| 7.7 Hook `useSignals.ts` | 🟡 Moyenne | 1h | Fetch + types TypeScript | ✅ |

**Livrable v0.7 :**
> ✅ L'utilisateur voit un panel qui dit : *"RSI en surachat (72), MACD croisé baissier, prix sous SMA50 → Score -65 (baissier, confiance haute)"* au lieu de juste voir des chiffres bruts.

---

## ✅ LIVRÉ : v0.8 — Alertes & Notifications

> Le système passe de "interpréter" à "alerter proactivement".

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 8.1 Modèle Alert en DB | 🔴 Haute | 2h | SQLAlchemy: seuils prix, RSI, MACD, signaux | ✅ |
| 8.2 API CRUD `/alerts` | 🔴 Haute | 3h | GET/POST/PUT/DELETE + check + notifications | ✅ |
| 8.3 Service AlertChecker | 🔴 Haute | 4h | Évaluation conditions vs données marché | ✅ |
| 8.4 UI AlertPanel | 🟡 Moyenne | 4h | Formulaire + liste alertes actives + notifications | ✅ |
| 8.5 Polling notifications | 🟡 Moyenne | 2h | Polling automatique toutes les 60s | ✅ |
| 8.6 48 tests backend | 🔴 Haute | 3h | CRUD, évaluation, récurrence, endpoints | ✅ |

**Livrable v0.8 :**
> ✅ L'utilisateur configure *"M'alerter si RSI > 75"* ou *"Prix > 70000$"* et reçoit une notification quand la condition est remplie. Les alertes peuvent être one-shot ou récurrentes.

---

## ✅ LIVRÉ : v0.9 — News & Sentiment

> Le système passe de "alerter" à "comprendre le contexte".

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 9.1 Collecteur RSS | 🔴 Haute | 4h | CoinTelegraph, CoinDesk, Bitcoin Magazine | ✅ |
| 9.2 Classification sentiment | 🔴 Haute | 4h | Keyword-based (bullish/bearish/neutral) | ✅ |
| 9.3 Score d'impact | 🟡 Moyenne | 2h | HIGH/MEDIUM/LOW basé sur mots-clés | ✅ |
| 9.4 Score global sentiment | 🟡 Moyenne | 2h | Agrégation pondérée -100/+100 | ✅ |
| 9.5 API /news endpoints | 🔴 Haute | 2h | GET /news + GET /news/sentiment | ✅ |
| 9.6 43 tests backend | 🔴 Haute | 3h | Sentiment, impact, RSS, résilience, endpoints | ✅ |
| 9.7 NewsPanel UI | 🟡 Moyenne | 4h | Jauge sentiment, articles, filtres, liens | ✅ |
| 9.8 Cache + résilience | 🟡 Moyenne | 1h | TTL 5min, timeout 10s, fallback | ✅ |

**Livrable v0.9 :**
> ✅ L'utilisateur voit les news crypto récentes avec un score de sentiment global, des articles classés positif/neutre/négatif, des niveaux d'impact, et peut filtrer par sentiment.

---

## ✅ LIVRÉ : v1.0 — Moteur de Décision (INFINI v1)

> Le système passe de "informer" à "recommander" avec des scénarios et des explications.

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 10.1 Moteur de règles | 🔴 Haute | 8h | 8 règles combinées (RSI, MACD, SMA, sentiment) | ✅ |
| 10.2 Scénarios multi-outcome | 🔴 Haute | 6h | Hausse/Stable/Baisse, probabilités normalisées | ✅ |
| 10.3 Recommandations explicables | 🔴 Haute | 4h | Acheter/Vendre/Attendre + raisons en français | ✅ |
| 10.4 API `/market/decision` | 🔴 Haute | 3h | Endpoint structuré avec mode dégradé | ✅ |
| 10.5 UI DecisionPanel | 🟡 Moyenne | 6h | Jauge combinée, barres scénarios, card recommandation | ✅ |
| 10.6 75 tests backend | 🔴 Haute | 4h | Règles, scénarios, recommandation, intégration, endpoint | ✅ |

**Livrable v1.0 :**
> ✅ L'utilisateur voit un panel de décision avec : un score combiné (70% technique + 30% sentiment), 3 scénarios avec probabilités, une recommandation explicable (Acheter / Vendre / Attendre) avec raisons, et les règles évaluées en détail.

---

## Phase v1.1 — Backtesting

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 11.1 Modèle Strategy | 🔴 Haute | 3h | Entry/exit rules en JSON |
| 11.2 Engine backtest | 🔴 Haute | 8h | Replay signaux/décisions sur historique |
| 11.3 Métriques performance | 🔴 Haute | 4h | Sharpe, Max Drawdown, Win Rate |
| 11.4 UI Backtest results | 🟡 Moyenne | 6h | Equity curve, trades table |

---

## Phase v1.2 — Multi-Assets

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 12.1 Dropdown symbole | 🔴 Haute | 2h | BTC/USD, ETH/USD, SOL/USD... |
| 12.2 Scheduler multi-symbol | 🔴 Haute | 4h | Loop sur liste configurable |
| 12.3 Dashboard comparatif | 🟡 Moyenne | 4h | Multi-charts ou tabs |
| 12.4 Heatmap corrélation | 🟢 Basse | 6h | Matrice inter-assets |

---

## Phase v1.3 — Risk Management

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 13.1 Stop-loss / Take-profit | 🔴 Haute | 4h | Configurables par position |
| 13.2 Limite d'exposition | 🔴 Haute | 3h | % max du portefeuille |
| 13.3 Limite perte journalière | 🔴 Haute | 3h | Kill switch si dépassé |
| 13.4 Dashboard risque | 🟡 Moyenne | 4h | Visualisation exposition |

---

## Phase v1.4 — Paper Trading

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 14.1 Carnet d'ordres fictif | 🔴 Haute | 6h | Market/Limit simulés |
| 14.2 Suivi positions | 🔴 Haute | 4h | PnL temps réel simulé |
| 14.3 Journal de trading | 🔴 Haute | 3h | Log toutes les décisions |
| 14.4 Mode fantôme | 🟡 Moyenne | 2h | Observer sans agir |

---

## Phase v1.5 — Production Ready

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 15.1 Docker Compose | 🔴 Haute | 3h | Backend + Frontend + PostgreSQL |
| 15.2 CI/CD GitHub Actions | 🟡 Moyenne | 4h | Tests + Build + Deploy |
| 15.3 Auth JWT | 🟡 Moyenne | 6h | Login/Register |
| 15.4 HTTPS + Reverse proxy | 🔴 Haute | 2h | Nginx/Caddy |
| 15.5 Monitoring | 🟢 Basse | 4h | Prometheus + Grafana |

---

## Phase v2.0+ — INFINI Mode Autonome ⚠️

> Ce mode ne sera activé qu'après validation complète par backtesting + paper trading.

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 20.1 Connecteur exchange | 🔴 Haute | 8h | Kraken/Binance via ccxt |
| 20.2 Exécution conditionnelle | 🔴 Haute | 10h | 3+ signaux convergents requis |
| 20.3 Trailing stop | 🔴 Haute | 4h | Stop-loss dynamique |
| 20.4 Audit trail complet | 🔴 Haute | 4h | Log chaque décision + raison |
| 20.5 Kill switch physique | 🔴 Haute | 2h | Bouton d'arrêt d'urgence |
| 20.6 Spécialisation stratégies | 🟢 Basse | 20h+ | Scalping, breakout, etc. |

---

## Vue Timeline

```
2026
├── Avril
│   ├── [✅] v0.6.0 — Socle marché complet (4 timeframes, dual-jobs)
│   ├── [✅] v0.7.0 — Moteur de signaux (LIVRÉ)
│   ├── [✅] v0.8.0 — Alertes & Notifications (LIVRÉ)
│   └── [✅] v0.9.0 — News & Sentiment (LIVRÉ)
│
├── Mai
│   ├── [✅] v1.0.0 — Moteur de Décision (LIVRÉ)
│   └── [🔄] v1.1.0 — Backtesting (PROCHAINE ÉTAPE)
│
├── Juin
│   └── [ ] v1.1.0 — Backtesting
│
├── Juillet
│   ├── [ ] v1.2.0 — Multi-Assets
│   └── [ ] v1.3.0 — Risk Management
│
├── Août
│   ├── [ ] v1.4.0 — Paper Trading
│   └── [ ] v1.5.0 — Production Ready
│
└── Q4 2026+
    └── [ ] v2.0.0 — INFINI Mode Autonome
```

---

## Principes directeurs

1. **Fiabilité des données avant tout** — Aucun signal ne vaut rien si les données sont fausses
2. **Intelligence progressive** — Pas de moteur de décision avant le moteur de signal
3. **Explicabilité permanente** — Chaque signal doit pouvoir être expliqué en une phrase
4. **Contrôle humain garanti** — L'automatisation est un outil, pas un pilote
5. **Itération rapide** — Chaque release apporte une valeur concrète et testable
