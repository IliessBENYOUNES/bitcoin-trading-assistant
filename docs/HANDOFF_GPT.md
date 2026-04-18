# 🔄 HANDOFF GPT — Dernière intervention (branche experimental)

## Date : 18 avril 2026 — v2.0.30 (experimental multi-strategy)

---

## Problème

Journal experimental du 17/04 : **-$468 net sur 46 trades** alors que BTC a fait +5.4%.
Frais cumulés **$442** contre perte brute de $26 : ratio **17×**. Le moteur multi-stratégie capturait des mouvements positifs en brut mais les frais détruisaient la performance net. 18 trades fermés en breakeven avaient un peak moyen de 0.13% (< frais 0.31%) → tous net-négatifs.

Parallèlement, l'audit du moteur MAIN sur 831 trades révèle des patterns systémiques transposables :
- Corrélation |score| vs pnl_pct = -0.134 (p=0.0001) : scores élevés = perdants
- Fenêtre 13-16h UTC = -$104 cum (US open + macro)
- Micro SL = destructeur net (184 coupures × -$1.98 = -$364)

## Diagnostic

Analyse statistique profonde des 2 journaux (détail dans le master). Les insights sont **transposables à l'architecture multi-stratégie** car :
- Mêmes données BTC (Binance klines)
- Mêmes horaires de trading
- Mêmes frais (0.31% RT Binance)
- Mêmes logiques de sortie (breakeven, trailing, micro_sl)

## Cause racine

L'architecture experimental (multi-strategy engine avec 5 stratégies routées par contexte de marché) est différente du master (multi-slot avec profils), mais partage les mêmes défauts exploitables :
1. **Pas de gate horaire** — les 5 stratégies tournent 24/7 y compris dans la fenêtre US open destructive
2. **Pas de gate structurel** — les chop ranges (ATR ratio < 1.5) laissent les stratégies churn sans amplitude
3. **Pas de cap score** — les signaux saturés (|score|>55) arrivent tard et font entrer au pire moment
4. **Breakeven trop permissif** — seuil `pnl <= 0` déclenche sur micro-bosses (peak 0.05-0.15%), garantissant la perte nette
5. **Micro_sl serré sur 3 strategies** — coupe avant que le trade puisse se développer

## Corrections appliquées

### Fichiers modifiés

| Fichier | Changement |
|---------|------------|
| `backend/app/services/multi_strategy_engine.py` | +3 gates globaux (BLOCKED_HOURS_UTC, MIN_ATR_RATIO, MAX_ABS_COMBINED_SCORE) en constantes de classe + injection dans `evaluate_tick()` + paramètre `skip_global_gates` pour les tests unitaires |
| `backend/app/services/paper_trading_service.py` | Durcissement breakeven : seuil peak = 2× frais (0.62%) AVANT activation + seuil sortie = frais (0.31%) au lieu de 0% |
| `backend/app/services/strategies/micro_scalping.py` | `micro_sl_pct`: 0.10 → 0.0 (désactivé) |
| `backend/app/services/strategies/scalping.py` | `micro_sl_pct`: 0.20 → 0.0 (désactivé) |
| `backend/app/services/strategies/aggressive.py` | `micro_sl_pct`: 0.50 → 0.0 (désactivé) |
| `backend/tests/test_multi_strategy.py` | 2 tests adaptés : `test_params` (micro_sl=0.0) + `test_evaluate_tick_with_range_series` (skip_global_gates=True) |
| `backend/tests/test_pivot_v200.py` | `test_breakeven_stop_protects_small_gains` marqué @pytest.mark.skip — test devenu obsolète car le breakeven ne protège plus les petits gains par design |

### Nouveaux gates globaux — MultiStrategyEngine

| Constante | Valeur | Application | Justification |
|-----------|--------|-------------|---------------|
| `BLOCKED_HOURS_UTC` | `{13,14,15,16}` | Rejet immédiat si `datetime.utcnow().hour` dans le set | Audit MAIN : -$104 cum sur ces 3h en 4j |
| `MIN_ATR_RATIO` | `1.5` | Rejet si `context.atr_ratio < 1.5` | Chop range = amplitude insuffisante pour 2× frais |
| `MAX_ABS_COMBINED_SCORE` | `55` | Si `|combined_score| > 55`, ne garder que micro_scalping (qui utilise micro_trend_score, pas combined) | Corrélation négative score↔pnl |
| `BREAKEVEN_MIN_PEAK_FEE_MULTIPLE` | `2.0` | Constante documentaire (consommée par paper_trading_service) | Évite breakevens net-négatifs |

### Paramètres modifiés — Stratégies

| Stratégie | Param | Avant | Après | Justification |
|-----------|-------|-------|-------|---------------|
| `micro_scalping` | `micro_sl_pct` | 0.10 | **0.0** | Audit master : 184 coupures = -$364 cum |
| `scalping` | `micro_sl_pct` | 0.20 | **0.0** | Même logique |
| `aggressive` | `micro_sl_pct` | 0.50 | **0.0** | Swings ont besoin de respiration |

### Logique breakeven durcie (paper_trading_service.py ligne ~590)

**Avant** :
```python
if peak_pct >= breakeven_activation and unrealized_pct_now <= 0:
```

**Après** :
```python
_be_fee_pct = get_cost_model("realistic").round_trip_cost_pct()  # ~0.31%
_be_peak_min = 2.0 * _be_fee_pct  # 0.62%
if peak_pct >= _be_peak_min and unrealized_pct_now <= _be_fee_pct:
```

## Ce qui n'a PAS été touché

- Les stratégies `breakout` et `mean_reversion` (pas de micro_sl modifié, les gates globaux s'appliquent au niveau engine)
- La logique de routing `CONTEXT_STRATEGY_MAP` (les 5 stratégies restent orchestrées par régime/zone)
- L'anti-collision long/short
- La limite max_simultaneous=3 positions
- La structure `StrategyParams` (pas de nouveau champ, les 3 gates vivent au niveau engine)
- Le frontend experimental (pas de changement visible côté UI)
- Les services `binance_service.py`, `coingecko_service.py`, etc. (diff CRLF uniquement)

## Validations

- ✅ **1854 tests backend passent** sur branche experimental (baseline 1855 - 1 skipped documenté)
- ✅ **2 failed** identiques à baseline (préexistants sur test_signals, sans rapport avec v2.0.30)
- ✅ `tsc --noEmit` frontend sans erreur (exit 0)
- ✅ Diff baseline/après : **0 régression nouvelle** introduite par v2.0.30
- ✅ Tests `test_evaluate_tick_with_range_series` et `test_breakeven_stop_protects_small_gains` adaptés pour refléter les nouveaux comportements volontaires

## Documentation mise à jour

| Document | Changements |
|----------|-------------|
| `docs/HANDOFF_GPT.md` (exp) | Ce fichier (édité, pas recréé) |

**Note** : CURRENT_STATE.md, CHANGELOG.md, ROADMAP.md, requirements_traceability.md de la branche experimental n'ont **PAS** été mis à jour (la branche n'a pas suivi le même cycle de versioning que master). Le prochain développeur qui reprend experimental doit décider s'il synchronise ces docs avec le master ou conserve sa propre timeline.

## État actuel

- **Branche** : `experiment/v2-fees-and-1m` (worktree à `C:\Users\ibenyounes\Git_Repository\bitcoin-trading-v2-experiment`)
- **Version** : alignée sur v2.0.30 master pour les principes, conserve sa propre architecture multi-strategy
- **Tests backend** : 1854 passed / 2 failed (préexistants) / 1 skipped (volontaire)
- **Frontend** : tsc clean ✅
- **Commit** : à faire
- **Prochaine action (Session 4 validation 7j)** : même procédure que master, voir `docs/VALIDATION_7J_V2030.md` (dans master)

## Commandes de relance (experimental)

```bash
# Backend (port 8001)
cd C:\Users\ibenyounes\Git_Repository\bitcoin-trading-v2-experiment\backend
.\venv\Scripts\activate
uvicorn app.main:app --port 8001

# Frontend (port 5174)
cd C:\Users\ibenyounes\Git_Repository\bitcoin-trading-v2-experiment\frontend
npm run dev -- --port 5174

# Tests
cd C:\Users\ibenyounes\Git_Repository\bitcoin-trading-v2-experiment\backend
venv\Scripts\python.exe -m pytest tests/ -q --no-header --tb=no

# Lancer le multi-strategy engine (mode headless)
curl -X POST http://localhost:8001/paper/multi-strategy/start -H "Content-Type: application/json"
```

---

## 🗂️ Historique — Intervention précédente (13 avril 2026, v2.0.28)

L'analyse du run v2.0.27 (58 trades, -$20.41, profit factor 0.64) révèle 3 problèmes structurels :

1. **Slot aggressive sans protections** : pas de SAS, pas de micro SL, pas de smart cooldown. Le trade #1108 a perdu 100% d'un pic de 0.705% ($0 PnL au lieu de +$17), le trade #1102 a perdu -$6.60.
2. **Cooldown scalping trop long** : le cooldown de 1 min (v2.0.25 anti-churn) est disproportionné maintenant que le micro SL est à 0.05% — les boucles churn sont cassées, le cooldown bloque inutilement.
3. **Gain erosion trop sensible** : se déclenche sur des peaks < $0.50 (bruit de tick), avec des sorties à +$0.12-$0.18 qui ne couvrent pas les frais.

## Diagnostic

- **58 trades analysés** dont ~50 scalping et ~8 aggressive
- Aggressive : gain erosion ferme sur des peaks de 0.02-0.08% → PnL de $0 à $0.40 (poussière)
- Aggressive : trailing activé trop tôt (0.15%) ou laissé filer (drop ratio 30% → perte de 100% du pic)
- Scalping : gain erosion sort sur des peaks de 0.01% ($0.25) — du bruit
- Scalping : cooldown de 1 min empêche de profiter d'opportunités rapides

## Cause racine

Le profil aggressive manquait de toutes les protections développées pour le scalping (SAS v2.0.22, micro SL v2.0.23, smart cooldown v2.0.24). Le profil scalping avait un cooldown calibré pour un micro SL de 0.01%, devenu obsolète avec le recalibrage à 0.05%.

## Corrections appliquées

### Fichiers modifiés

| Fichier | Changement |
|---------|------------|
| `backend/app/services/trading_profile_service.py` | Profil aggressive : +SAS, +micro SL 0.15%, +smart cooldown, trailing 0.25%/20%, gain erosion 0.70, cooldown 5 min. Profil scalping : cooldown 0.5 min, min 0.25, max 2.0, gain erosion 0.40 |
| `backend/app/services/paper_trading_service.py` | Gain erosion min peak 0.01%→0.02% |
| `backend/tests/test_smart_cooldown.py` | 4 assertions mises à jour |
| `backend/tests/test_pivot_v200.py` | 7 assertions mises à jour |
| `backend/tests/test_scalping_audit.py` | 1 assertion mise à jour |
| `backend/tests/test_diagnostic.py` | 1 assertion mise à jour |
| `backend/tests/test_runtime_truth.py` | 1 assertion mise à jour |
| `backend/tests/test_entry_sas.py` | 1 test renommé/corrigé (aggressive SAS activé) |
| `backend/tests/test_micro_stop_loss.py` | 1 test renommé/corrigé (aggressive micro SL activé) |

### Paramètres modifiés — Scalping

| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| `cooldown_minutes` | 1.0 | **0.5** | micro SL 0.05% casse les boucles churn |
| `min_cooldown_minutes` | 0.5 | **0.25** | SAS protège en amont |
| `max_cooldown_minutes` | 3.0 | **2.0** | micro SL + SAS suffisent |
| `gain_erosion_ratio` | 0.30 | **0.40** | plus de marge pour développer les gains |

### Paramètres modifiés — Aggressive

| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| `cooldown_minutes` | 15 | **5** | 3× plus d'opportunités intraday |
| `trailing_stop_activation_pct` | 0.15 | **0.25** | laisse les swings se développer |
| `trailing_stop_drop_ratio` | 0.30 | **0.20** | protège 80% au lieu de 70% |
| `gain_erosion_ratio` | 0.50 | **0.70** | les swings oscillent, besoin de respiration |
| `entry_sas_enabled` | ❌ | **✅** | filtre mauvaises entrées (10s/5s) |
| `micro_stop_loss_pct` | None | **0.15** | coupe à -$3.75 au lieu de -$25 |
| `smart_cooldown_enabled` | ❌ | **✅** | cooldown adaptatif (1-5 min) |

### Paramètre global modifié

| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| Gain erosion min peak | 0.01% | **0.02%** | peaks < $0.50 = bruit |

## Ce qui n'a PAS été touché

- Le frontend (aucun changement)
- Les profils conservative et balanced
- Les mécanismes de sortie existants (trailing, breakeven, stale, SL/TP)
- Le SAS d'entrée scalping (15s/10s inchangé)
- Le micro SL scalping (0.05% inchangé)
- Les gates économiques, structural proofs, trend alignment
- Le tick momentum / candle direction override

## Validations

- ✅ **1808 tests** backend passent (0 échec, 12 warnings cosmétiques)
- ✅ `tsc --noEmit` frontend sans erreur
- ✅ Non-régression complète (0 test supprimé)

## Documentation mise à jour

| Document | Changements |
|----------|-------------|
| `docs/CURRENT_STATE.md` | Version 2.0.28, features v2.0.28, tests 1808, section 5 Vision Reality Gap ✅ Complet, section 6 phases v1.8-v2.0 mises à jour, section 7 PaperRun ✅, table tests complète (40 fichiers) |
| `CHANGELOG.md` | Entrée [2.0.28] complète (Added + Changed + Technical) |
| `docs/ROADMAP.md` | État actuel v2.0.28, 1808 tests, timeline v2.0.1-v2.0.28 ajoutée |
| `docs/requirements_traceability.md` | Version v2.0.28, date 13/04, 12 FRs ajoutés (v2.0.10-v2.0.28), NFR tests 1808, table test coverage complète (40 fichiers) |
| `docs/HANDOFF_GPT.md` | Ce fichier (édité, pas recréé) |

## État actuel

- **Version** : v2.0.28
- **Tests** : 1808 passed ✅
- **Frontend** : tsc clean ✅
- **Prochaine action** : Lancer un run en mode auto (scalping + aggressive) pendant 1-2h pour valider les nouvelles protections aggressive et le cooldown réduit scalping

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v

# Lancer le robot (mode headless)
curl -X POST http://localhost:8000/paper/autonomous/start -H "Content-Type: application/json" -d '{"interval_seconds": 5, "profile": "scalping"}'
```
