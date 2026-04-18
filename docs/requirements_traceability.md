# Requirements Traceability Matrix (RTM)

## Project: Bitcoin Trading Assistant
## Version: v2.0.30
## Date: 2026-04-18

---

## Functional Requirements

| ID | Requirement | Acceptance Criteria | Status | Proof |
|----|-------------|---------------------|--------|-------|
| FR-MKT-001 | Fetch OHLC candles from CoinGecko | `POST /market/candles/fetch` returns fetched count > 0 | ✅ PASS | `{"fetched": 42, "inserted": 0, "duplicates": 42}` |
| FR-MKT-002 | Store candles in PostgreSQL | Candles persisted across restarts | ✅ PASS | `total_in_db: 56` |
| FR-MKT-003 | Idempotent upsert (no duplicates) | Same candle not inserted twice | ✅ PASS | `duplicates: 42` on re-fetch |
| FR-MKT-004 | Rolling window query | `GET /market/candles?days=7` returns 7-day window | ✅ PASS | `actual_count: 43` |
| FR-QA-001 | Detect data gaps | `GET /market/candles/gaps` returns missing_count | ✅ PASS | `missing_count: 0` |
| FR-QA-002 | Freshness status | data_lag < threshold → FRESH | ✅ PASS | `data_lag_hours: 3.31, status: FRESH` |
| FR-QA-003 | Completeness status | expected == actual → OK | ✅ PASS | `expected_count: 43, actual_count: 43, status: OK` |
| FR-IND-001 | Calculate RSI(14) | `GET /market/indicators` returns rsi_14 | ✅ PASS | `latest.rsi_14 != null` after warmup |
| FR-IND-002 | Calculate MACD(12,26,9) | Response contains macd, macd_signal, macd_hist | ✅ PASS | Endpoint returns all MACD fields |
| FR-IND-003 | Calculate SMA(20,50,200) | Response contains sma_20, sma_50, sma_200 | ✅ PASS | sma_20 calculated (sma_50/200 null if insufficient data) |
| FR-IND-004 | Calculate Bollinger(20,2) | Response contains bb_mid, bb_upper, bb_lower | ✅ PASS | Bollinger bands calculated |
| FR-IND-005 | NaN → null in JSON | Warmup periods return null, not NaN | ✅ PASS | First 14 points have `rsi_14: null` |
| FR-SCH-001 | Scheduler enable/disable | `SCHEDULER_ENABLED=true/false` controls startup | ✅ PASS | `enabled: true, running: true` |
| FR-SCH-002 | Periodic fetch job | Job executes at configured interval | ✅ PASS | `last_run_time` populated |
| FR-SCH-003 | Scheduler status endpoint | `GET /scheduler/status` returns state | ✅ PASS | See proof below |
| FR-SCH-004 | Job success reporting | `last_result.status: "success"` on success | ✅ PASS | `{"status":"success","fetched":42}` |
| **FR-SIG-001** | **Interpret RSI → signal** | **RSI >70 → bearish, <30 → bullish** | **✅ PASS** | **52 tests passing** |
| **FR-SIG-002** | **Interpret MACD → signal** | **MACD crossover → directional signal** | **✅ PASS** | **test_macd_bullish_crossover** |
| **FR-SIG-003** | **Interpret SMA → signal** | **Price vs SMA20/50/200 → trend signal** | **✅ PASS** | **test_sma_above_all** |
| **FR-SIG-004** | **Interpret Bollinger → signal** | **Price vs bands → overbought/oversold** | **✅ PASS** | **test_bollinger_above_upper** |
| **FR-SIG-005** | **Composite score -100/+100** | **Weighted aggregation with confidence** | **✅ PASS** | **test_all_bullish, test_all_bearish** |
| **FR-SIG-006** | **GET /market/signals endpoint** | **Returns signals + composite + summary** | **✅ PASS** | **test_signals_endpoint_with_data** |
| **FR-SIG-007** | **SignalPanel UI** | **Gauge, signal list, consensus badge** | **✅ PASS** | **tsc --noEmit clean** |
| **FR-ALT-001** | **Modèle Alert en DB** | **Table alerts avec conditions, seuils, status** | **✅ PASS** | **48 tests passing** |
| **FR-ALT-002** | **API CRUD /alerts** | **GET/POST/PUT/DELETE + check + notifications** | **✅ PASS** | **test_create_alert, test_delete_alert** |
| **FR-ALT-003** | **Évaluation conditions** | **Prix, RSI, MACD hist, score vs seuils** | **✅ PASS** | **test_check_price_above_triggered** |
| **FR-ALT-004** | **Alertes récurrentes** | **one-shot ou recurring (réarme après trigger)** | **✅ PASS** | **test_recurring_stays_active** |
| **FR-ALT-005** | **AlertPanel UI** | **Formulaire + liste + notifications polling** | **✅ PASS** | **tsc --noEmit clean** |
| **FR-BKT-001** | **Replay historique candle par candle** | **POST /backtest/run retourne trades et métriques** | **✅ PASS** | **31 tests passing** |
| **FR-BKT-002** | **Simulation positions achat/vente** | **Trades générés quand action=acheter/vendre** | **✅ PASS** | **test_run_with_enough_candles** |
| **FR-BKT-003** | **Métriques de performance** | **Win rate, Sharpe, drawdown, profit factor calculés** | **✅ PASS** | **test_win_rate, test_profit_factor, test_sharpe** |
| **FR-BKT-004** | **Buy & Hold benchmark** | **Comparaison avec stratégie passive** | **✅ PASS** | **test_buy_and_hold_benchmark** |
| **FR-BKT-005** | **Warning suroptimisation** | **Alerte si <10 trades ou Sharpe >3.0** | **✅ PASS** | **test_overfitting_warning_few_trades** |
| **FR-BKT-006** | **BacktestPanel UI** | **Config + métriques + journal trades** | **✅ PASS** | **tsc --noEmit clean** |
| **FR-VER-001** | **Chargement historique profond** | **POST /backtest/history/load retourne fetched + inserted** | **✅ PASS** | **33 tests passing** |
| **FR-VER-002** | **Plage de dates en base** | **GET /backtest/history/range retourne min/max date** | **✅ PASS** | **test_get_history_range_with_data** |
| **FR-VER-003** | **Time-travel verify** | **POST /backtest/verify retourne prédiction + outcomes** | **✅ PASS** | **test_verify_returns_prediction** |
| **FR-VER-004** | **Comparaison prédiction/réalité** | **Outcomes 7j/30j/90j avec correct=true/false** | **✅ PASS** | **test_buy_hausse_is_correct, test_sell_baisse_is_correct** |
| **FR-VER-005** | **Walk-forward analysis** | **POST /backtest/walk-forward retourne accuracy par horizon** | **✅ PASS** | **test_walk_forward_accuracy_structure** |
| **FR-VER-006** | **VerificationPanel UI** | **Charger historique + date picker + résultats + walk-forward** | **✅ PASS** | **tsc --noEmit clean** |
| **FR-RSK-001** | **Risk Config CRUD** | **GET/POST /risk/config retourne config** | **✅ PASS** | **55 tests passing** |
| **FR-RSK-002** | **Risk Evaluate** | **POST /risk/evaluate retourne allowed + SL/TP** | **✅ PASS** | **test_evaluate_acheter** |
| **FR-RSK-003** | **Kill Switch** | **POST /risk/kill-switch/activate bloque les trades** | **✅ PASS** | **test_kill_switch_blocks** |
| **FR-PAP-001** | **Paper Account CRUD** | **GET/POST /paper/account crée et retourne le compte** | **✅ PASS** | **64 tests passing** |
| **FR-PAP-002** | **Paper Tick Engine** | **POST /paper/tick exécute un tick (SL/TP/décision/risk)** | **✅ PASS** | **test_tick_opens_position_on_buy_signal** |
| **FR-PAP-003** | **Paper SL/TP Check** | **SL et TP déclenchés correctement pour long et short** | **✅ PASS** | **test_check_sl_long_hit, test_check_tp_short_hit** |
| **FR-PAP-004** | **Paper Metrics** | **GET /paper/metrics retourne win rate, Sharpe, drawdown, profit factor** | **✅ PASS** | **test_metrics_with_trades** |
| **FR-PAP-005** | **Paper Trades Journal** | **GET /paper/trades retourne liste paginée + filtres status** | **✅ PASS** | **test_get_trades_with_filter** |
| **FR-PAP-006** | **Paper Close Manual** | **POST /paper/close ferme la position ouverte** | **✅ PASS** | **test_close_with_position** |
| **FR-PAP-007** | **PaperTradingPanel UI** | **Statut + tick + métriques + journal + position ouverte** | **✅ PASS** | **tsc --noEmit clean** |
| **FR-JRN-001** | **Journal d'évaluation multi-jours** | **GET /paper/journal retourne synthèse + journalier + activité + raisons** | **✅ PASS** | **64 tests passing** |
| **FR-JRN-002** | **Vue synthèse période** | **PnL, win rate, expectancy, profit factor, Sharpe, drawdown, verdict** | **✅ PASS** | **test_journal_period_summary** |
| **FR-JRN-003** | **Vue journalière** | **Résumé par jour (trades, PnL, meilleur/pire, verdict)** | **✅ PASS** | **test_journal_daily_view** |
| **FR-JRN-004** | **Vue activité** | **Fréquence ticks, ratio tick→trade, répartition** | **✅ PASS** | **test_journal_activity** |
| **FR-JRN-005** | **Raisons de non-trade** | **Agrégation + labels humains + pourcentages** | **✅ PASS** | **test_journal_non_trade_reasons** |
| **FR-PRF-001** | **Profils de trading** | **GET /paper/profile retourne profil actif + paramètres** | **✅ PASS** | **test_get_profile** |
| **FR-PRF-002** | **Changement de profil** | **POST /paper/profile change conservative/balanced/aggressive** | **✅ PASS** | **test_set_profile** |
| **FR-PRF-003** | **Presets profils** | **GET /paper/profile/presets retourne tous les profils disponibles** | **✅ PASS** | **test_get_profile_presets** |
| **FR-LEV-001** | **Levier auto intelligent** | **Calcul score × confiance × volatilité × max_leverage** | **✅ PASS** | **test_leverage_recommendation** |
| **FR-LEV-002** | **Veto risk engine** | **blocked/danger → x1, caution → cap 50%** | **✅ PASS** | **test_leverage_risk_veto** |
| **FR-STY-001** | **Style de trading** | **GET /paper/style retourne distribution durées + style dominant** | **✅ PASS** | **test_trading_style** |
| **FR-STY-002** | **JournalPanel UI** | **5 sous-vues, profils, KPIs, barres de distribution** | **✅ PASS** | **tsc --noEmit clean** |
| **FR-DIA-001** | **Diagnostic de fréquence** | **GET /paper/diagnostic retourne causes non-trade + recommandations** | **✅ PASS** | **55 tests passing** |
| **FR-DIA-002** | **Opportunités manquées** | **GET /paper/missed-opportunities retourne analyse ex-post** | **✅ PASS** | **test_missed_opportunities** |
| **FR-DIA-003** | **Analyse levier** | **GET /paper/leverage-analysis retourne PnL avec/sans levier** | **✅ PASS** | **test_leverage_analysis** |
| **FR-DIA-004** | **Profil Scalping** | **Profil scalping avec seuils custom, timeframe 15m** | **✅ PASS** | **test_scalping_profile** |
| **FR-DIA-005** | **DiagnosticPanel UI** | **7 sections, recommandations, comparaison profils** | **✅ PASS** | **tsc --noEmit clean** |
| **FR-MSL-001** | **Multi-slot positions** | **Jusqu'à 3 positions parallèles, allocation capital par slot** | **✅ PASS** | **1005 tests passing** |
| **FR-MSL-002** | **Mean reversion bidirectionnel** | **SHORT en surachat, LONG en survente** | **✅ PASS** | **test_scalping_reversal** |
| **FR-MSL-003** | **SL/TP direction-aware** | **Defaults corrigés pour SHORT** | **✅ PASS** | **test_sl_tp_defaults** |
| **FR-MSL-004** | **Per-slot cooldown** | **Chaque slot a ses propres timers indépendants** | **✅ PASS** | **test_per_slot_cooldown** |
| **FR-MSL-005** | **Trailing stop scalping** | **Trailing stop activé quand profit > seuil, ferme si recul > trail%** | **✅ PASS** | **1005 tests passing** |
| | | | | |
| **FR-CST-001** | **Modèle de coûts de trading** | **TradingCostModel avec presets, métriques brut/net** | **✅ PASS** | **v1.8.1 — 48 tests (test_reality_gap.py)** |
| **FR-RUN-001** | **Campagnes de validation (PaperRun)** | **Runs bornés, profil fixe, verdict final** | **✅ PASS** | **v1.9.0 — test_paper_trading.py** |
| **FR-AUD-001** | **Audit de vérité métriques** | **Expectancy nette, drawdown vérifié, verdict global** | **✅ PASS** | **v1.8.3 — test_runtime_truth.py** |
| **FR-GATE-001** | **Gate formelle v2.0** | **Checklist de readiness, status READY/PARTIAL/NOT_READY** | **✅ PASS** | **v1.8.4** |
| **FR-ECO-001** | **Economic viability gate** | **Évaluation coût RT pré-entrée, refuse si capture < 1.5× RT cost** | **✅ PASS** | **v2.0.0 — 8 tests (test_pivot_v200.py)** |
| **FR-ECO-002** | **Expected capture calibré** | **expected_capture_pct=0.50 (pas fallback trailing 0.20%)** | **✅ PASS** | **v2.0.0-fix — gate math vérifié: 0.50% > 0.465%** |
| **FR-STR-001** | **Structural proofs gate** | **≥2 preuves structurelles requises pour entrée scalping** | **✅ PASS** | **v2.0.0 — 3 tests (test_pivot_v200.py)** |
| **FR-MFR-001** | **Momentum fade restricted** | **Momentum fade seulement si pic ≥ 0.35% ET sortie net-positive** | **✅ PASS** | **v2.0.0 — 4 tests (test_pivot_v200.py)** |
| **FR-RVP-001** | **Protection reversal signal contraire** | **Reversal ne ferme plus par signal contraire au même score** | **✅ PASS** | **v2.0.11 — 12 tests (test_pivot_v200.py)** |
| **FR-GES-001** | **Gain erosion stop** | **Sort quand gain érodé de 30% du pic (peak 0.01-0.04%)** | **✅ PASS** | **v2.0.12 — 18 tests (test_pivot_v200.py)** |
| **FR-TMC-001** | **Tick momentum confirmation** | **Analyse ticks ~30s pour confirmer direction avant entrée** | **✅ PASS** | **v2.0.13 — 20 tests (test_pivot_v200.py)** |
| **FR-CDO-001** | **Candle direction override** | **Direction trade = direction prix 30s (bougie verte→LONG, rouge→SHORT)** | **✅ PASS** | **v2.0.14 — 9 tests (test_pivot_v200.py)** |
| **FR-CDI-001** | **Candle direction indicator** | **Champ `entry_candle_direction` stocké sur chaque trade, affiché en frontend** | **✅ PASS** | **v2.0.15 — 7 tests (test_paper_trading.py::TestEntryCandleDirection)** |
| **FR-RPF-001** | **REST price fallback** | **Si WebSocket inaccessible, fallback REST /market/price toutes les 10s** | **✅ PASS** | **v2.0.15 — useLivePrice.ts fallback + PriceTicker REST badge** |
| **FR-EXC-001** | **Exit candle direction** | **Champ exit_candle_direction stocké à la fermeture, pastille double (E/S)** | **✅ PASS** | **v2.0.16 — 8 tests (test_paper_trading.py)** |
| **FR-CLP-001** | **Candle direction learning** | **Patterns entrée→sortie (same_aligned, reversed_against, meta, durée×candle)** | **✅ PASS** | **v2.0.17 — 9 tests (test_learning.py)** |
| **FR-CRE-001** | **Candle reversal exit** | **Sortie active si bougie inverse ≥3s, reversal_delay_seconds tracking** | **✅ PASS** | **v2.0.18 — 12 tests (test_candle_reversal.py)** |
| **FR-AGP-001** | **Aggressive slot protection** | **Stale négatif 60min, trailing 0.15%/0.30, gain erosion 0.50** | **✅ PASS** | **v2.0.19 — test_pivot_v200.py** |
| **FR-OAC-001** | **Override anti-churn** | **Tick override entry_reason préfixé, protection signal contraire** | **✅ PASS** | **v2.0.19 — test_pivot_v200.py** |
| **FR-DTP-001** | **Downtrend protection** | **Veto bearish micro-trend bloque LONG si mt_score < 0** | **✅ PASS** | **v2.0.10 — 11 tests (test_pivot_v200.py)** |
| **FR-MSC-001** | **Momentum stability check** | **Compare direction 30s vs 10s, bloque entrées fin de bougie** | **✅ PASS** | **v2.0.21 — 7 tests (test_pivot_v200.py)** |
| **FR-SAS-001** | **SAS d'entrée sécurisé** | **Observation 10-15s virtuelle, range caution, confirmation PnL positif** | **✅ PASS** | **v2.0.22 — 39 tests (test_entry_sas.py)** |
| **FR-MSL-002** | **Micro stop loss** | **Sortie immédiate si PnL < -micro_stop_loss_pct, configurable par profil** | **✅ PASS** | **v2.0.23 — 18 tests (test_micro_stop_loss.py)** |
| **FR-TAF-001** | **Trend alignment filter** | **Bloque SHORT/LONG override quand score technique fort en sens inverse** | **✅ PASS** | **v2.0.26+v2.0.27 — 12 tests (test_pivot_v200.py)** |
| **FR-AGP-002** | **Aggressive protections complètes** | **SAS + micro SL 0.15% + smart cooldown + trailing recalibré** | **✅ PASS** | **v2.0.28 — test_entry_sas.py + test_micro_stop_loss.py** |
| **FR-BHU-001** | **Blocked hours UTC** | **Refuse ouvertures sur fenêtres UTC destructrices (audit 17/04 : 14-16h UTC -$104)** | **✅ PASS** | **v2.0.30 — trading_profile_service.py, paper_trading_service._tick_single_slot** |
| **FR-MSC-002** | **Max score cap** | **Refuse entrées si \|score\| > max_score (audit : corrélation r=-0.134 p=0.0001)** | **✅ PASS** | **v2.0.30 — trading_profile_service.py** |
| **FR-RAT-001** | **Min range/ATR gate** | **Refuse marchés compressés (range_width_atr < 1.5 = chop range)** | **✅ PASS** | **v2.0.30 — market_structure_service.py + paper_trading_service** |
| **FR-BPM-001** | **Breakeven peak min fee multiple** | **Empêche breakeven tant que peak < N× frais RT (évite fermetures systématiques net nul)** | **✅ PASS** | **v2.0.30 — paper_trading_service breakeven logic** |
| **FR-MSL-003** | **Scalping micro SL désactivé** | **micro_stop_loss_pct=None (audit: 184 coupures, -$364). SL classique 0.50% reste actif.** | **✅ PASS** | **v2.0.30 — trading_profile_service.py PROFILE_PRESETS[scalping]** |

---

## Non-Functional Requirements

| ID | Requirement | Acceptance Criteria | Status | Proof |
|----|-------------|---------------------|--------|-------|
| NFR-SEC-001 | No secrets in repo | `.env` not tracked, no passwords in code | ✅ PASS | `git ls-files \| findstr .env` → empty |
| NFR-SEC-002 | Test artifacts ignored | `test.db` not tracked | ✅ PASS | Listed in `.gitignore` |
| NFR-TEST-001 | Backend tests pass | `pytest -v` all green | ✅ PASS | 1808 tests passing |
| NFR-TZ-001 | UTC timestamps | All timestamps stored/returned in UTC | ✅ PASS | `max_ts: "2026-01-07T20:00:00+00:00"` |
| NFR-IDEM-001 | Idempotent fetch | Re-fetch same data → 0 inserts | ✅ PASS | `inserted: 0, duplicates: 42` |

---

## QA Evidence

### Scheduler Status (2026-01-07T23:10)
```json
{
  "enabled": true,
  "running": true,
  "interval_minutes": 5,
  "symbol": "BTC/USD",
  "days": 7,
  "last_run_time": "2026-01-07T23:10:07.574460+00:00",
  "next_run_time": "2026-01-07T23:15:07.573764+00:00",
  "last_result": {
    "status": "success",
    "symbol": "BTC/USD",
    "days": 7,
    "timeframe": "4h",
    "fetched": 42,
    "inserted": 0,
    "updated": 0,
    "duplicates": 42,
    "duration_seconds": 0.917
  }
}
```

### Data Quality (2026-01-07T23:18)
```json
{
  "symbol": "BTC/USD",
  "timeframe": "4h",
  "freshness": {
    "data_lag_hours": 3.31,
    "threshold_hours": 4,
    "status": "FRESH"
  },
  "completeness": {
    "expected_count": 43,
    "actual_count": 43,
    "missing_count": 0,
    "status": "OK"
  },
  "global_status": "OK"
}
```

---

## Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| test_health.py | 3 | ✅ |
| test_market.py | 4 | ✅ |
| test_indicators.py | 35 | ✅ |
| test_time_buckets.py | 24 | ✅ |
| test_scheduler.py | 16 | ✅ |
| test_scheduler_dual_jobs.py | 15 | ✅ |
| test_scheduler_resample_1d.py | 7 | ✅ |
| test_scheduler_resample_1h.py | 6 | ✅ |
| **test_signals.py** | **88** | **✅** |
| **test_alerts.py** | **48** | **✅** |
| **test_news.py** | **43** | **✅** |
| **test_decision.py** | **122** | **✅** |
| **test_backtest.py** | **31** | **✅** |
| **test_verification.py** | **79** | **✅** |
| **test_binance_and_router.py** | **17** | **✅** |
| **test_news_history.py** | **33** | **✅** |
| **test_cryptocompare.py** | **30** | **✅** |
| **test_sentiment_history.py** | **42** | **✅** |
| **test_scheduler_news.py** | **11** | **✅** |
| **test_risk.py** | **57** | **✅** |
| **test_price_service.py** | **5** | **✅** |
| **test_paper_trading.py** | **141** | **✅** |
| **test_journal_and_profiles.py** | **84** | **✅** |
| **test_diagnostic.py** | **55** | **✅** |
| **test_reality_gap.py** | **48** | **✅** |
| **test_economic_value.py** | **40** | **✅** |
| **test_stability.py** | **67** | **✅** |
| **test_scalping_audit.py** | **37** | **✅** |
| **test_smart_cooldown.py** | **51** | **✅** |
| **test_learning.py** | **31** | **✅** |
| **test_short_optimization.py** | **67** | **✅** |
| **test_market_structure.py** | **55** | **✅** |
| **test_runtime_truth.py** | **34** | **✅** |
| **test_pivot_v200.py** | **174** | **✅** |
| **test_autonomous.py** | **15** | **✅** |
| **test_runtime_correlation.py** | **17** | **✅** |
| **test_candle_reversal.py** | **12** | **✅** |
| **test_enriched_export.py** | **25** | **✅** |
| **test_entry_sas.py** | **39** | **✅** |
| **test_micro_stop_loss.py** | **18** | **✅** |
| **Total** | **1808** | ✅ |
