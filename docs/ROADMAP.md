# 🗺️ Roadmap — Bitcoin Trading Assistant

## État actuel (v0.6.0)

| Composant | Status |
|-----------|--------|
| Backend dual-jobs scheduler | ✅ Complet |
| 4 timeframes (30m, 1h, 4h, 1d) | ✅ Complet |
| Resample 30m→1h, 4h→1d | ✅ Complet |
| Frontend Dashboard | ✅ Complet |
| Indicateurs (RSI, MACD, SMA, Bollinger) | ✅ Complet |
| Chart Lightweight Charts | ✅ Complet |

---

## Phase 3 : Améliorations UX (v0.7)

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 3.1 Cap effectiveDays 30m/1h | 🔴 Haute | 1h | Éviter faux GAPS (Option A - en cours) |
| 3.2 Dark/Light mode toggle | 🟡 Moyenne | 2h | ThemeProvider MUI |
| 3.3 Responsive mobile | 🟡 Moyenne | 3h | Breakpoints, menu hamburger |
| 3.4 Persistance localStorage | 🟢 Basse | 1h | Sauvegarder timeframe/days préférés |

---

## Phase 4 : Alertes & Notifications (v0.8)

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 4.1 Modèle Alert en DB | 🔴 Haute | 2h | SQLAlchemy model: price, RSI, MACD thresholds |
| 4.2 API CRUD /alerts | 🔴 Haute | 3h | GET/POST/PUT/DELETE |
| 4.3 Service AlertChecker | 🔴 Haute | 4h | Job scheduler qui évalue les conditions |
| 4.4 UI AlertPanel | 🟡 Moyenne | 4h | Formulaire création + liste alertes actives |
| 4.5 Notifications browser | 🟡 Moyenne | 2h | Web Push API ou polling |
| 4.6 Webhook/Discord/Telegram | 🟢 Basse | 3h | Notifications externes |

---

## Phase 5 : Multi-Assets (v0.9)

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 5.1 Dropdown symbole | 🔴 Haute | 2h | BTC/USD, ETH/USD, SOL/USD... |
| 5.2 Scheduler multi-symbol | 🔴 Haute | 4h | Loop sur liste configurable |
| 5.3 Dashboard comparatif | 🟡 Moyenne | 4h | Vue multi-charts ou tabs |
| 5.4 Heatmap correlation | 🟢 Basse | 6h | Matrice de corrélation entre assets |

---

## Phase 6 : Backtesting (v1.0)

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 6.1 Modèle Strategy | 🔴 Haute | 3h | Entry/exit rules en JSON ou Python |
| 6.2 Engine backtest | 🔴 Haute | 8h | Simuler trades sur historique |
| 6.3 Métriques performance | 🔴 Haute | 4h | Sharpe, Max Drawdown, Win Rate |
| 6.4 UI Backtest results | 🟡 Moyenne | 6h | Equity curve, trades table |
| 6.5 Optimisation paramètres | 🟢 Basse | 8h | Grid search sur indicateurs |

---

## Phase 7 : Trading Live (v1.1) ⚠️

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 7.1 Intégration exchange API | 🔴 Haute | 8h | Kraken/Binance via ccxt |
| 7.2 Paper trading mode | 🔴 Haute | 6h | Simulation sans argent réel |
| 7.3 Execution engine | 🔴 Haute | 10h | Market/Limit orders |
| 7.4 Position management | 🔴 Haute | 6h | Stop-loss, take-profit |
| 7.5 Risk management | 🔴 Haute | 4h | Max position size, daily loss limit |
| 7.6 Audit trail | 🔴 Haute | 4h | Log toutes les décisions |

---

## Phase 8 : Déploiement Production (v1.2)

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 8.1 Docker Compose | 🔴 Haute | 3h | Backend + Frontend + PostgreSQL |
| 8.2 CI/CD GitHub Actions | 🟡 Moyenne | 4h | Tests + Build + Deploy |
| 8.3 PostgreSQL migration | 🔴 Haute | 2h | Remplacer SQLite |
| 8.4 Auth JWT | 🟡 Moyenne | 6h | Login/Register |
| 8.5 HTTPS + Reverse proxy | 🔴 Haute | 2h | Nginx/Caddy |
| 8.6 Monitoring | 🟢 Basse | 4h | Prometheus + Grafana |

---

## Vue Timeline

```
2026
├── Avril
│   ├── [✅] v0.5 - UI stable 4h
│   ├── [✅] v0.5.1 - Resample 4h→1d
│   ├── [✅] v0.6.0 - Dual jobs + tous timeframes
│   └── [🔄] v0.7.0 - UX improvements (en cours)
│
├── Mai
│   ├── [ ] v0.8.0 - Alertes & Notifications
│   └── [ ] v0.9.0 - Multi-Assets
│
├── Juin
│   └── [ ] v1.0.0 - Backtesting
│
├── Juillet
│   └── [ ] v1.1.0 - Paper Trading
│
└── Août
    └── [ ] v1.2.0 - Production Ready
```

---

## Priorités immédiates (semaine du 31 mars 2026)

| # | Tâche | Fichiers | Temps |
|---|-------|----------|-------|
| 1 | ✅ Cap effectiveDays 30m/1h | Dashboard.tsx | 30 min |
| 2 | ✅ Commit v0.6.0 | git tag | 5 min |
| 3 | Dark/Light mode | theme.ts, App.tsx | 2h |
| 4 | Tests E2E basiques | Playwright/Cypress | 4h |

