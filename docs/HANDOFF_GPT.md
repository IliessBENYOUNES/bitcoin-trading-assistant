# HANDOFF GPT — Anti-churn reversal + cooldown réduit v2.0.11

**Date :** 12 avril 2026  
**Version :** v2.0.11  
**Commit :** `7a7acc6`

---

## Problème

Deux problèmes runtime identifiés sur un run de 30 trades scalping :

1. **Boucle reversal-churn** : **30 trades identiques** `mean_reversion_short` avec score=66, chacun fermé après ~50sec par "Signal contraire : acheter (score=66, seuil=30)". Le même score qui créait le trade le détruisait → boucle infinie.

2. **Cooldown trop long** : le cooldown dynamique de 2 min empêchait de capter le prochain signal après un renversement de tendance. En 2 min, le marché peut déjà se retourner.

## Diagnostic

### Boucle reversal-churn
| Tick | Score | Entry reason | Exit reason | Durée |
|------|-------|-------------|-------------|-------|
| 1-30 | 66 | mean_reversion_short | Signal contraire : acheter (score=66, seuil=30) | ~50sec |

Le score 66 déclenche un short reversal (surachat). Après min_hold=45sec, le score est toujours 66. Le signal contraire ferme le short car 66 ≥ seuil 30. Cooldown → réouverture → même boucle × 30.

### Cooldown trop long
Le `bearish_veto` (v2.0.10) bloque maintenant les LONG en downtrend, rendant le long cooldown anti-churn redondant. On peut réduire sans risque.

## Cause racine

1. **Signal contraire aveugle aux reversals** : le seuil `short_exit_score_threshold=30` ne distinguait pas les trades classiques des reversals. Un reversal ouvert à score=66 était immédiatement éligible à la fermeture (66 > 30).
2. **Cooldown redondant** : le cooldown long (2 min base, 10 min max, 4 min floor stale) datait d'avant le `bearish_veto` qui protège maintenant en amont.

## Correction appliquée

### 1. Protection reversal signal contraire (SHORT)
```python
# AVANT : signal contraire ferme si score >= short_exit_th (30)
# APRÈS : pour les reversals, seuil relevé à entry_score + 1
is_reversal = (open_pos.entry_reason or "").startswith("mean_reversion_")
if is_reversal and open_pos.decision_score is not None:
    short_exit_th = max(short_exit_th, abs(open_pos.decision_score) + 1)
# Un short ouvert à score=66 ne ferme plus tant que score ≤ 66
```

### 2. Protection reversal signal contraire (LONG)
```python
# AVANT : signal contraire ferme dès que score < 0
# APRÈS : pour les reversals, ferme seulement si bearish a AUGMENTÉ
if is_reversal and open_pos.decision_score is not None:
    if abs(score) > abs(open_pos.decision_score):
        close_signal = True  # bearish intensifié
```

### 3. Cooldown réduit
| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| `cooldown_minutes` | 2 | **1** | bearish_veto protège en amont |
| `max_cooldown_minutes` | 10.0 | **5.0** | Même raison |
| `STALE_NEGATIVE_FLOOR` | 4.0 | **2.0** | Même raison |

### Fichiers modifiés

| Fichier | Changement |
|---------|-----------|
| `services/paper_trading_service.py` | Protection reversal dans signal contraire (SHORT + LONG) |
| `services/trading_profile_service.py` | `cooldown_minutes` 2→1, `max_cooldown_minutes` 10→5 |
| `services/smart_cooldown_service.py` | `STALE_NEGATIVE_FLOOR` 4→2 |
| `tests/test_pivot_v200.py` | 12 nouveaux tests `TestReversalSignalContraireProtection` |
| `tests/test_diagnostic.py` | Assertion cooldown_minutes 2→1 |
| `tests/test_scalping_audit.py` | Assertion cooldown_minutes 2→1 |
| `tests/test_smart_cooldown.py` | Assertions max_cooldown 10→5, cooldown_configured_min 2→1 |
| `tests/test_runtime_truth.py` | Assertions max_cooldown 10→5, stale floor 4→2 |

## Ce qui n'a PAS été touché

- ❌ Trailing stop relatif (v2.0.9)
- ❌ Breakeven stop, SL/TP, momentum fade
- ❌ Veto bearish (v2.0.10 — toujours actif)
- ❌ Profils aggressive/conservative/balanced
- ❌ Frontend
- ❌ Trades non-reversal → seuil signal contraire standard inchangé

## Validations

- ✅ **1647 tests** backend passent (12 ajoutés)
- ✅ Zéro régression sur les 1635 tests existants

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ v2.0.11, 1647 tests, feature anti-churn reversal |
| `CHANGELOG.md` | ✅ Section v2.0.11 (Fixed + Added + Technical) |
| `docs/ROADMAP.md` | ✅ État actuel v2.0.11 |
| `docs/requirements_traceability.md` | ✅ FR-RVP-001, total 1647 tests |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## Commit

```
7a7acc6 fix(scalping): anti-churn reversal + cooldown reduit v2.0.11
```

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.11 |
| Tests | 1647 passing |
| Phase | Anti-churn reversal + cooldown réduit livré |

## Prochaine action recommandée

1. **Full reset + nouveau run** : faire tourner le robot en scalping pendant 1-2h
2. **Vérifier que** :
   - Les shorts reversal vivent plus longtemps (pas fermés à 50sec par signal contraire)
   - Les sorties se font via trailing/stale/SL au lieu de signal contraire
   - Le cooldown de 1 min permet de capter les renversements
   - Le `bearish_veto` bloque toujours les LONG en downtrend
3. **Audit runtime** : `GET /audit/enriched-export` pour vérifier la distribution des exit_reason

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
cd backend && python -m pytest tests/test_pivot_v200.py::TestReversalSignalContraireProtection -v
```
