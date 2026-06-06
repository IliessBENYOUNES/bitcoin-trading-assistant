# 🔄 HANDOFF GPT — Dernière intervention (branche experimental)

## Date : 6 juin 2026 — v2.1.0 (gate économique pré-trade + recalibration multi-strategy)

> **Objectif** : rendre le moteur EXP multi-strategy *fee-positive par construction*. Livre les items F5/F6 reportés du Batch 2 et recalibre les 4 stratégies pour qu'aucun trade ne puisse s'ouvrir si son TP ne couvre pas 2× les frais round-trip.

---

## Problème

Audit EXP 25-27/04 (59 trades, port 5174 multi-strategy) : gross **+$2.32**, frais **$209.87**, **net -$207.55**, WR net 6.78%, 83 % de sorties "stale". Les frais écrasent un gross quasi-nul ; 21 trades brut-positifs sont devenus net-négatifs (gagnants rendus en stale-négatif).

## Diagnostic — 5 fuites économiques

| # | Fuite (preuve) | Correctif |
|---|----------------|-----------|
| 1 | Aucun gate économique pré-trade (plan §5.2.D jamais codé) | Gate universel : rejet si TP < 2× frais RT (0.62 %) |
| 2 | 21 trades brut+ → net- (gagnants rendus en stale-négatif) | Trailing fee-aware : plancher de sortie = niveau des frais |
| 3 | 83 % sorties stale (entrées de mauvaise qualité) | ↑ sélectivité (scalping 28, micro_trend 5, breakout conf 70 + score 30) |
| 4 | breakout = pire : TP plancher 0.50 % < frais utiles | TP dérivé du range + gate (ne trade que si range assez large) |
| 5 | 3 stratégies simultanées multiplient les frais | Cap à 2 stratégies éligibles/contexte |

## Cause racine

Le moteur multi-strategy n'avait aucun garde-fou économique pré-trade, et plusieurs TP planchers étaient calibrés sous le seuil de rentabilité (2× frais RT = 0.62 % avec le preset `realistic` à 0.31 %). Tout trade visant < 0.62 % était structurellement perdant même gagné.

## Correction appliquée (6 fichiers)

- **`multi_strategy_engine.py`** : constantes `MIN_EV_MULTIPLE=2.0`, `COST_PRESET="realistic"`, `MAX_ELIGIBLE_STRATEGIES=2`. Étape 7 de `evaluate_tick` = gate économique (boucle sur les signaux approuvés, rejette si `estimate_economic_viability()["is_viable"]` est faux). `_get_eligible_strategies` → cap `[:2]`.
- **`experimental_engine.py`** (`_manage_open_position`) : trailing fee-aware — armement `max(activation, 1.5× frais)`, seuil de sortie `max(peak×(1-drop), frais_RT)` → jamais de sortie net-négative depuis un gagnant.
- **`strategies/scalping.py`** : `MIN_SCORE` 20→28.
- **`strategies/micro_scalping.py`** : `MIN_MICRO_TREND` 3→5, TP 0.50→0.65 %, SL 0.25→0.30 %, trailing_activation 0.15→0.30 %, micro_sl 0.
- **`strategies/mean_reversion.py`** : TP = 0.7×demi-range, SL = 0.5×demi-range, micro_sl 0.
- **`strategies/breakout.py`** : trend-follow durci (conf≥70 ET |score|≥30), TP plancher 0.50→0.40 %, micro_sl 0.

## Ce qui n'a PAS été touché

- **WIP v2.0.32** (`trading_profile_service.py` + `paper_trading_service.py`, profils standard `balanced`/`aggressive`) : laissée **non-commitée**, orthogonale au moteur multi-strategy.
- `trading_cost_service.py`, `market_context_engine.py`, `multi_strategy_risk.py`, frontend : inchangés.
- Aucun schema, aucune migration DB.

## Validations

| Check | Résultat |
|-------|----------|
| `pytest tests/test_multi_strategy.py -q` | ✅ **56 passed** (49 + 7 nouveaux gate/cap) |
| `test_economic_value` + `test_scalping_audit` + `test_micro_stop_loss` + `test_pivot_v200` (WIP stashée) | ✅ **228 passed** |
| Isolation des 72 échecs du run complet | ✅ tous dans la WIP v2.0.32 (disparaissent quand elle est stashée) |
| Viabilité runtime des params réels | ✅ micro_scalping/scalping/aggressive + ranges larges viables ; ranges étroits rejetés |

## Documentation mise à jour

| Doc | Section |
|-----|---------|
| `CHANGELOG.md` | Nouvelle entrée `[2.1.0] - 2026-06-06` |
| `docs/CURRENT_STATE.md` | En-tête → v2.1.0 + section moteur |
| `docs/ROADMAP.md` | Batch 3 (gate éco F6) marqué livré |
| `docs/requirements_traceability.md` | FR gate économique + compteur tests |
| `docs/HANDOFF_GPT.md` | Ce fichier (édité, pas recréé) |

## Commit

```
feat(multi-strategy): gate economique pre-trade + trailing fee-aware + recalibration 4 strategies v2.1.0
```

## État actuel

- **Branche** : `experiment/v2-fees-and-1m`
- **Version** : v2.1.0
- **Tests moteur** : 56 passed (`test_multi_strategy`)
- **Mode utilisateur** : multi-strategy (frontend 5174 / backend 8001)
- **Prochaine action recommandée** : run paper multi-strategy live — vérifier 0 trade ouvert avec TP < 0.62 %, 0 trailing-out net-négatif depuis un gagnant.

## Commandes de relance

```powershell
# Backend EXPERIMENTAL (port 8001) — DSN nettoyé du suffixe ?schema Prisma
Start-Process powershell -ArgumentList "-Command","cd C:\Users\ilies\git\bitcoin-trading-v2-experiment\backend; .\venv\Scripts\activate; python -m uvicorn app.main:app --host 127.0.0.1 --port 8001"
# Frontend EXPERIMENTAL (port 5174)
Start-Process powershell -ArgumentList "-Command","cd C:\Users\ilies\git\bitcoin-trading-v2-experiment\frontend; npx vite --port 5174"
# Activer le multistrategy
# POST http://127.0.0.1:8001/paper-trading/engine-mode?mode=experimental
# POST http://127.0.0.1:8001/paper-trading/autonomous/start  {interval_seconds:60, profile:"scalping"}
```

---

> **Historique précédent** archivé ci-dessous.

---

## Date : 23 avril 2026 — v2.0.31-fees-batch2 (Batch 2 EXP réorienté)

> **Important — réorientation stratégique** : l'inspection du code a confirmé que le moteur EXP en mode `experimental` (multi-strategy, celui que l'utilisateur lance via le frontend port 5174) **n'emprunte PAS** `paper_trading_service._tick_single_slot` ni `PROFILE_PRESETS`. Tout passe par `ExperimentalPaperTradingService._experimental_tick()` → `_manage_open_position()` qui consomme les `StrategyParams` de `strategies/*.py`. Les fixes F1+F2+F8 du commit précédent (v2.0.31-fees) sont donc **inactifs en mode multi-strategy** ; ils restent en place comme filet de sécurité au cas où on bascule en mode standard. Ce batch corrige les **vrais** bugs du chemin multi-strategy.

---

## Problème

Journal EXP du 18/04 → 23/04 (52 trades, port 5174 multi-strategy) :
- **-$436 net** (-4.36%) alors que BTC montait
- WR net = **11.5%**, frais cumulés **$446** > 100% de la perte
- **24 trades fermés via "Micro stop loss : PnL latent -0.15%"** pour -$304 cum
- Plusieurs trailing-out net-négatifs (peak < 2× frais)

## Diagnostic — 2 bugs critiques dans `experimental_engine._manage_open_position`

### Bug F3 (CRITIQUE) — micro_sl `0.0` ferme à la moindre perte

```python
# AVANT (experimental_engine.py L394)
if unrealized_pct <= -params.micro_sl_pct:   # quand micro_sl_pct=0.0 → if pct <= 0
```

La "désactivation" v2.0.30 fixait `micro_sl_pct = 0.0` sur scalping/aggressive/micro_scalping en croyant désactiver le mécanisme. Mais la condition devient `if unrealized_pct <= -0.0` = `if unrealized_pct <= 0` → **fermeture instantanée dès que le PnL latent passe sous zéro**. Sur un tick 5s, la première lecture négative est typiquement -0.05 à -0.20% sur BTC → cohérent avec les 24 fermetures observées à -0.15%.

> 💡 Le moteur MAIN (`paper_trading_service._tick_single_slot` L455-456) gate déjà correctement avec `if micro_sl_pct is not None and micro_sl_pct > 0:`. Le bug est exclusif au chemin multi-strategy EXP.

### Bug F4 — Trailing s'active avant 2× frais

```python
# AVANT (experimental_engine.py L424)
if peak_pct >= params.trailing_activation_pct and unrealized_pct > 0:
```

Les `trailing_activation_pct` des strategies vont de 0.15% (micro_scalping) à 0.60% (aggressive). Avec frais RT = 0.31%, tout trailing activé en dessous de **0.62% (= 2 × frais)** garantit un trailing-out net-négatif (le pic ne couvre même pas les frais).

## Cause racine

Les commits v2.0.30 ont introduit l'idée "micro_sl=0.0 = désactivé" sans modifier la condition de gate, et le trailing n'a jamais eu de garde-fou économique.

## Correction appliquée

### Fichier modifié (1)

**`backend/app/services/experimental_engine.py`** (`_manage_open_position`) :

```python
# F3 — gate micro_sl uniquement si seuil strictement positif
if params.micro_sl_pct > 0 and unrealized_pct <= -params.micro_sl_pct:
    ...

# F4 — gate trailing min_peak = 2× round-trip fees
from app.services.trading_cost_service import get_cost_model
_fee_pct = get_cost_model("realistic").round_trip_cost_pct()  # ~0.31%
_trailing_min_peak = max(params.trailing_activation_pct, 2.0 * _fee_pct)  # ≥ 0.62%
if peak_pct >= _trailing_min_peak and unrealized_pct > 0:
    ...
```

## Ce qui n'a PAS été touché

- Aucune modification des `strategies/*.py` (les valeurs `micro_sl_pct=0.0` v2.0.30 restent telles quelles → simplement plus interprétées comme "désactivé")
- Aucune modification de `MultiStrategyEngine` (gates globaux v2.0.30 inchangés)
- Aucune modification du `_close_position()` ou du `trading_cost_service`
- Aucune modification de `TradingProfileService` / PROFILE_PRESETS
- Frontend non touché
- Bug F7 (`account.total_fees` agrégation visible dans le journal) **non corrigé** dans ce batch — c'est cosmétique (le PnL net est correct, seul l'agrégat affiché est faux). Reporté Batch 3.
- F5 (macro trend filter) et F6 (economic gate 0.65%) reportés Batch 3 après validation paper run F3+F4.

## Validations

| Check | Résultat |
|-------|----------|
| `pytest tests/ -q` | ✅ **1856 passed, 1 skipped, 0 failed** (baseline conservée) |
| `get_errors experimental_engine.py` | ✅ aucune erreur |
| Vérification MAIN ne souffre pas du même bug | ✅ MAIN gate déjà avec `if micro_sl_pct is not None and micro_sl_pct > 0` |

## Documentation mise à jour

| Doc | Section modifiée |
|-----|------------------|
| `CHANGELOG.md` (EXP) | Nouvelle entrée `[2.0.31-fees-batch2] - 2026-04-23` (Fixed F3/F4 + note réorientation) |
| `docs/HANDOFF_GPT.md` (EXP) | Ce fichier (édité, pas recréé) |
| `docs/CURRENT_STATE.md` (EXP) | Version → v2.0.31-fees-batch2 (à faire dans le commit) |

## Commit (à venir)

```
fix(multi-strategy): F3 bug micro_sl=0.0 + F4 trailing min_peak 2× fees v2.0.31-fees-batch2
```

## État actuel

- **Branche** : `experiment/v2-fees-and-1m`
- **Version** : v2.0.31-fees-batch2
- **Tests** : 1856 passed / 1 skipped / 0 failed
- **Mode utilisateur** : multi-strategy (port 5174) — F3+F4 sont actifs sur ce chemin ✅
- **Prochaine action recommandée** : laisser tourner le multi-strategy 1 nuit pour valider :
  - 0 trade fermé via "Micro stop loss" sur scalping/aggressive/micro_scalping (où `micro_sl_pct=0.0`)
  - 0 trailing-out avec peak < 0.62%
  - PnL net > -$50 sur 24h
- Si validé → Batch 3 (F5 macro trend filter, F6 economic gate 0.65%, F7 fix `account.total_fees` agrégation cosmétique)

## Commandes de relance

```powershell
# Kill tout
taskkill /F /IM python.exe 2>$null ; taskkill /F /IM node.exe 2>$null ; Start-Sleep 2

# Backend EXPERIMENTAL (port 8001)
Start-Process powershell -ArgumentList "-Command","cd C:\Users\ilies\git\bitcoin-trading-v2-experiment\backend; .\venv\Scripts\activate; python -m uvicorn app.main:app --host 127.0.0.1 --port 8001"

# Frontend EXPERIMENTAL (port 5174)
Start-Process powershell -ArgumentList "-Command","cd C:\Users\ilies\git\bitcoin-trading-v2-experiment\frontend; npx vite --port 5174"

# Vérifier
netstat -ano | findstr "LISTENING" | findstr "8001"
netstat -ano | findstr "LISTENING" | findstr "5174"
```

---

> **Historique précédent** archivé ci-dessous (intervention v2.0.31-fees du 23/04 — Batch 1, fixes désormais inactifs en mode multi-strategy mais conservés comme filet pour le mode standard).

---

## Date : 23 avril 2026 — v2.0.31-fees (Option A, Batch 1/2 sur EXP)

> Application au moteur EXPERIMENTAL des fixes F1+F2+F8 déjà livrés sur le moteur MAIN (v2.0.31, commit `master`). Les deux moteurs convergent désormais sur la même logique de Signal contraire.

---

## Problème

Journal EXP du 18/04 13h → 22/04 22h (52 trades) : **-$436 net** alors que BTC montait. WR net = **11.5%**, frais cumulés **$446** > 100% de la perte. 50/52 trades fermés via "Signal contraire" sur scalping/aggressive (audit `docs/ENGINE_AUDIT.md` §7).

Causes racines identifiées (audit §7.3) :
1. **Bug auto-mode** : `_tick_single_slot` re-résolvait le profil à chaque tick sur une position déjà ouverte. Trade ouvert sur scalping (`min_hold=300s`) → 3 min plus tard, score=62 résoud "aggressive" (sans `min_hold` historique) → fermeture immédiate Signal contraire.
2. **Sortie "Signal contraire" = piège fees mécanique** : capture moyenne 0.04% brut = $1 → -$6.75 NET après frais $7.75. Plus le moteur a raison sur la direction, plus il perd net.

## Diagnostic

Cross-référence du log JSON `btc-trading-journal-2026-04-22-Moteur Expérimental.json` avec `paper_trading_service._tick_single_slot` (ligne 836-840 pré-fix) → confirmation que `auto_select_profile(score, confidence)` est appelé sur position ouverte. Tous les trades scalping/aggressive fermés via Signal contraire correspondent à des ouvertures min_hold mais re-résolution → perte du min_hold.

## Cause racine

```python
# AVANT (paper_trading_service.py L836-840)
if is_auto_mode:
    resolved_profile = TradingProfileService.auto_select_profile(score, confidence)
    profile_params = PROFILE_PRESETS[resolved_profile]   # ← change le profil sur position ouverte
    profile_name = f"auto→{resolved_profile}"
```

## Correction appliquée

### Fichiers modifiés (3)

1. **`backend/app/schemas/journal.py`** — Nouveau champ schema :
   ```python
   opposite_signal_exit_enabled: bool = Field(default=True, ...)
   ```

2. **`backend/app/services/trading_profile_service.py`** :
   - `scalping.opposite_signal_exit_enabled = False`
   - `aggressive.opposite_signal_exit_enabled = False`
   - `aggressive.min_hold_seconds = 300` (F8 — defense en profondeur)
   - `aggressive.short_min_hold_seconds = 300`

3. **`backend/app/services/paper_trading_service.py`** (`_tick_single_slot`, monitoring branch) :
   - F2 : auto-mode lit désormais `open_pos.profile_type` (profil d'entrée) au lieu de re-résoudre à chaque tick. Fallback sur l'ancien comportement si le profil d'entrée est inconnu.
   - F1 : nouveau gate `opposite_signal_enabled = getattr(profile_params, "opposite_signal_exit_enabled", True)`. Si `False`, les blocs `if direction=="long"` / `elif direction=="short"` sont skippés entièrement → SL/TP/trailing/breakeven/stale en aval restent actifs.

## Ce qui n'a PAS été touché

- Aucune modification du modèle de coûts (`trading_cost_service.py`)
- Aucune modification du `_close_position()` (calcul net inchangé)
- Aucune modification de `decision_service`, `signal_service`, `tick_momentum_service`
- Aucune migration DB nécessaire (pas de nouvelle colonne)
- Frontend non touché (le toggle n'est pas exposé en UI pour l'instant)
- Profils `conservative` et `balanced` non modifiés (gardent `opposite_signal_exit_enabled=True` par défaut)

## Validations

| Check | Résultat |
|-------|----------|
| Import `PROFILE_PRESETS` | ✅ scalping.opposite_signal_exit_enabled = False |
|  | ✅ aggressive.opposite_signal_exit_enabled = False |
|  | ✅ aggressive.min_hold_seconds = 300 |
|  | ✅ aggressive.short_min_hold_seconds = 300 |
| `pytest tests/ -q` | ✅ **1856 passed, 1 skipped, 0 failed** (vs baseline 1856 — aucune régression) |
| `get_errors` 3 fichiers | ✅ aucune erreur |

## Documentation mise à jour

| Doc | Section modifiée |
|-----|------------------|
| `CHANGELOG.md` | Nouvelle entrée `[2.0.31-fees] - 2026-04-23` (Fixed F1/F2/F8 + Technical) |
| `docs/CURRENT_STATE.md` | Header version 2.0.28 → 2.0.31-fees, tests 1808 → 1856, branche `master` → `experiment/v2-fees-and-1m` |
| `docs/HANDOFF_GPT.md` | Ce fichier (édité, jamais recréé) |
| `docs/ENGINE_AUDIT.md` (repo MAIN) | Section 7 déjà à jour côté MAIN ; Batch 2 EXP à venir (F3/F4/F5/F6/F7) |

## Commit

```
fix(profiles): F1+F2+F8 EXP — désactiver Signal contraire scalping/aggressive + fix bug auto-mode v2.0.31-fees
```

## État actuel

- Version : **v2.0.31-fees** (branche `experiment/v2-fees-and-1m`)
- Tests : 1856 passed / 1 skipped / 0 failed
- Prochaine action recommandée : **lancer 1 nuit de paper trading** (port 8001/5174) pour valider :
  - 0 trade scalping/aggressive fermé via "Signal contraire"
  - Durée moyenne scalping > 5 min (vs 326 s actuel)
  - WR net > 30% (vs 11.5% actuel)
  - PnL net > -$50 sur 24h
- Si validé → livrer Batch 2 (F3 micro_sl OFF aggressive, F4 trailing 50% + min_peak 3× fees, F5 macro trend filter, F6 economic gate 0.65%, F7 fix `account.total_fees` agrégation).

## Commandes de relance

```powershell
# Kill tout
taskkill /F /IM python.exe 2>$null ; taskkill /F /IM node.exe 2>$null ; Start-Sleep 2

# Backend EXPERIMENTAL (port 8001)
Start-Process powershell -ArgumentList "-Command","cd C:\Users\ilies\git\bitcoin-trading-v2-experiment\backend; .\venv\Scripts\activate; python -m uvicorn app.main:app --host 127.0.0.1 --port 8001"

# Frontend EXPERIMENTAL (port 5174)
Start-Process powershell -ArgumentList "-Command","cd C:\Users\ilies\git\bitcoin-trading-v2-experiment\frontend; npx vite --port 5174"

# Vérifier
netstat -ano | findstr "LISTENING" | findstr "8001"
netstat -ano | findstr "LISTENING" | findstr "5174"
```

---

> **Historique précédent** archivé ci-dessous (intervention v2.0.30 du 18/04).

---

## Date : 18 avril 2026 — v2.0.30 (experimental multi-strategy)

> **Push test 2026-04-18 01:28 UTC** — Identité IliessBENYOUNES confirmée sur experiment/v2-fees-and-1m.

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
