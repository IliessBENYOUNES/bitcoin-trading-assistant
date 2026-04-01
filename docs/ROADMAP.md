# 🗺️ Roadmap — Bitcoin Trading Assistant → INFINI

> **Dernière mise à jour :** 1er avril 2026
> **Document de référence détaillé :** [ROADMAP_INFINI.md](./ROADMAP_INFINI.md) (976 lignes)

---

## Vision : 3 étapes vers INFINI

```
┌─────────────────────────────────────────────────────────────────────┐
│  ÉTAPE 1 — BTC Insight (v0.2 → v0.9)                               │
│  Assistant visuel, modulaire, pédagogique                           │
│  ├── Données marché temps réel          ✅ Livré (v0.2-v0.6)       │
│  ├── Indicateurs techniques             ✅ Livré (v0.3)            │
│  ├── Signaux & scoring                  ⬜ Prochaine étape (v0.7)  │
│  ├── Alertes visuelles                  ⬜ Planifié (v0.8)         │
│  └── News & sentiment                   ⬜ Planifié (v0.9)         │
│                                                                      │
│  ÉTAPE 2 — INFINI v1 (v1.0 → v1.5)                                 │
│  Assistant intelligent, décisionnel                                  │
│  ├── Moteur de décision / règles        ⬜ Planifié (v1.0)         │
│  ├── Backtesting engine                 ⬜ Planifié (v1.1)         │
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

## État actuel : v0.6.0 — Fin du Niveau 1 (Socle marché)

| Composant | Status |
|-----------|--------|
| Backend dual-jobs scheduler | ✅ Complet |
| 4 timeframes (30m, 1h, 4h, 1d) | ✅ Complet |
| Resample 30m→1h, 4h→1d | ✅ Complet |
| Frontend Dashboard | ✅ Complet |
| Indicateurs (RSI, MACD, SMA, Bollinger) | ✅ Complet |
| Chart Lightweight Charts | ✅ Complet |
| 110 tests backend | ✅ Tous passing |

---

## PROCHAINE ÉTAPE : v0.7 — Moteur de Signaux (Niveau 2)

> Le projet passe du **Niveau 1** (données + affichage) au **Niveau 2** (intelligence analytique).
> Le système commence à *interpréter* et *penser*.

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 7.1 `signal_service.py` | 🔴 Haute | 4h | Interpréter RSI/MACD/SMA/Bollinger → signaux structurés |
| 7.2 Schéma `SignalResponse` | 🔴 Haute | 1h | SignalItem, CompositeScore, consensus |
| 7.3 `GET /market/signals` | 🔴 Haute | 2h | Endpoint API retournant signaux + score |
| 7.4 Score composite | 🔴 Haute | 3h | Agrégation -100/+100, confiance, convergence |
| 7.5 `test_signals.py` | 🔴 Haute | 4h | Tests unitaires pour chaque interpréteur |
| 7.6 `SignalPanel.tsx` | 🟡 Moyenne | 4h | Jauge, liste signaux, badge consensus |
| 7.7 Hook `useSignals.ts` | 🟡 Moyenne | 1h | Fetch + types TypeScript |

**Livrable v0.7 :**
> L'utilisateur voit un panel qui dit : *"RSI en surachat (72), MACD croisé baissier, prix sous SMA50 → Score -65 (baissier, confiance haute)"* au lieu de juste voir des chiffres bruts.

---

## Phase v0.8 — Alertes & Notifications

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 8.1 Modèle Alert en DB | 🔴 Haute | 2h | SQLAlchemy: seuils prix, RSI, MACD, signaux |
| 8.2 API CRUD `/alerts` | 🔴 Haute | 3h | GET/POST/PUT/DELETE |
| 8.3 Service AlertChecker | 🔴 Haute | 4h | Job scheduler évaluant les conditions |
| 8.4 UI AlertPanel | 🟡 Moyenne | 4h | Formulaire + liste alertes actives |
| 8.5 Notifications browser | 🟡 Moyenne | 2h | Web Push ou polling |
| 8.6 Webhook Discord/Telegram | 🟢 Basse | 3h | Notifications externes |

---

## Phase v0.9 — News & Sentiment

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 9.1 Collecteur de news | 🔴 Haute | 4h | RSS, CryptoCompare, ou API news |
| 9.2 Classification sentiment | 🔴 Haute | 6h | Positif / neutre / négatif par article |
| 9.3 Score d'impact | 🟡 Moyenne | 3h | Fort / moyen / faible |
| 9.4 Intégration au scoring | 🟡 Moyenne | 4h | Pondérer le score composite avec le sentiment |
| 9.5 UI NewsPanel | 🟡 Moyenne | 4h | Fil d'actus classé avec filtres |

---

## Phase v1.0 — Moteur de Décision (INFINI v1)

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 10.1 Moteur de règles | 🔴 Haute | 8h | Conditions combinées paramétrables |
| 10.2 Scénarios multi-outcome | 🔴 Haute | 6h | "Hausse 65% / Stable 25% / Baisse 10%" |
| 10.3 Recommandations explicables | 🔴 Haute | 4h | Raison en langage naturel |
| 10.4 API `/market/decision` | 🔴 Haute | 3h | Endpoint structuré |
| 10.5 UI DecisionPanel | 🟡 Moyenne | 6h | Scénarios visuels + confiance |

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
│   └── [🔄] v0.7.0 — Moteur de signaux (PROCHAINE ÉTAPE)
│
├── Mai
│   ├── [ ] v0.8.0 — Alertes & Notifications
│   └── [ ] v0.9.0 — News & Sentiment
│
├── Juin
│   └── [ ] v1.0.0 — Moteur de Décision (INFINI v1 commence)
│
├── Juillet
│   ├── [ ] v1.1.0 — Backtesting
│   └── [ ] v1.2.0 — Multi-Assets
│
├── Août
│   ├── [ ] v1.3.0 — Risk Management
│   └── [ ] v1.4.0 — Paper Trading
│
├── Septembre
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
