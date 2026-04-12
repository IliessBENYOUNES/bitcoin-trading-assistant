# HANDOFF GPT — Fix critique trailing stop prioritaire v2.0.8

**Date :** 12 avril 2026  
**Version :** v2.0.8  
**Commit :** (pending)

---

## Problème

Les positions scalping qui ÉTAIENT gagnantes (peak > 0.10%) retombaient en perte et étaient fermées à -$1.41 au lieu d'être protégées par le trailing stop. Le fix v2.0.7 (recalibration des seuils) ne suffisait pas.

## Diagnostic — Bug d'ordonnancement

L'ordre des vérifications de sortie dans `_tick_single_slot()` était :

```
1. SL/TP
2. Expiration
3. Update peak price
4. *** STALE EXIT *** ← vérifié EN PREMIER
5. Trailing stop  ← JAMAIS ATTEINT si stale fire
6. Momentum fade
```

Quand une position avec peak > activation (0.10%) retombe en négatif :
- **Stale négatif** : PnL < -0.03% ET elapsed ≥ 2 min → **FIRE, RETURN**
- **Trailing stop** : **JAMAIS ATTEINT** car le `return` du stale l'a court-circuité

## Cause racine

Le stale exit avait **priorité sur le trailing stop** dans l'ordre du code.

## Corrections appliquées

**Fichier : `backend/app/services/paper_trading_service.py`**

### 1. Réordonnancement des exit checks
```
Nouvel ordre :
1. SL/TP → 2. Expiration → 3. Update peak →
4. TRAILING STOP (priorité max) → 5. BREAKEVEN STOP (nouveau) →
6. Stale exit → 7. Momentum fade
```

### 2. Breakeven stop (nouveau mécanisme)
- **Activation** : peak ≥ trailing_activation / 2 (= 0.05%)
- **Trigger** : PnL retombe ≤ 0%
- **Effet** : ferme immédiatement au breakeven (~0$)

## Ce qui n'a PAS été touché

- ❌ Paramètres scalping (inchangés depuis v2.0.7)
- ❌ Aggressive (sanctuarisé)
- ❌ Frontend, logique d'entrée, SL/TP

## Validations

- ✅ **1608 tests** backend passent (4 ajoutés)
- ✅ `tsc --noEmit` clean

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ Version 2.0.8, 1608 tests |
| `CHANGELOG.md` | ✅ Entrée [2.0.8] |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## Tests ajoutés

- `TestTrailingStopPriorityV208::test_trailing_fires_before_stale_negative`
- `TestTrailingStopPriorityV208::test_breakeven_stop_protects_small_gains`
- `TestTrailingStopPriorityV208::test_stale_still_works_for_never_profitable`
- `TestTrailingStopPriorityV208::test_exit_priority_order`

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.8 |
| Tests backend | 1608 passing ✅ |
| TypeScript | tsc --noEmit clean ✅ |

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
cd backend && python -m pytest tests/test_pivot_v200.py::TestTrailingStopPriorityV208 -v
```
