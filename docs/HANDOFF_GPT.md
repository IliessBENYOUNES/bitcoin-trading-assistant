# HANDOFF GPT — Recalibration sorties scalping v2.0.7

**Date :** 12 avril 2026  
**Version :** v2.0.7  
**Commit :** (pending)

---

## Problème

Les positions scalping restent ouvertes trop longtemps et perdent tous les gains accumulés. Exemple concret : position atteint +$3.51 (peak 0.14%), puis retombe à +$2.23 après 10 minutes, et continue à dériver. L'utilisateur constate que les gains fondent systématiquement dans un marché en range.

## Diagnostic — Audit runtime exhaustif

Analyse du trade scalping #448 (premier trade après déblocage du gate micro-trend en v2.0.6) :

| Métrique | Valeur |
|----------|--------|
| Entry | $72,909 @ 02:05:02 |
| Peak price | $73,011 (0.1403%) |
| Peak PnL | +$3.51 |
| Trailing activation threshold | 0.15% |
| Peak vs activation | **0.14% < 0.15% → JAMAIS ACTIVÉ** |
| Stale exit | 15 min (pas encore atteint à 10 min) |
| Position size | $2,500, levier 1.0x |

**20 ticks analysés :** PnL oscille entre +$0.42 et +$3.51, aucun mécanisme de sortie ne se déclenche.

## Cause racine (2 problèmes combinés)

1. **Trailing activation trop haute (0.15%)** — Dans un marché en range serré (amplitude ~0.14%), le peak n'atteint jamais le seuil d'activation. Le trailing stop est configuré mais ne s'active JAMAIS.
2. **Stale exit trop lent (15 min)** — 15 minutes est une durée de swing trading, pas de scalping. Le slot reste bloqué pendant que les gains fondent, empêchant la rotation vers de meilleures opportunités.

## Corrections appliquées

**Fichier : `backend/app/services/trading_profile_service.py`**

| Paramètre | Avant | Après | Effet |
|-----------|-------|-------|-------|
| `stale_exit_minutes` | 15 | **5** | Rotation 3× plus rapide |
| `stale_negative_exit_minutes` | 5 | **2** | Pertes coupées encore plus vite |
| `trailing_stop_activation_pct` | 0.15% | **0.10%** | Le peak à 0.14% aurait activé le trailing |
| `trailing_stop_pct` | 0.10% | **0.06%** | Recul max depuis le peak : 0.06% au lieu de 0.10% |

**Capture minimale garantie :** 0.10% - 0.06% = 0.04% ($1.00 sur $2,500)

## Ce qui n'a PAS été touché

- ❌ Aggressive (sanctuarisé — stale 180 min, pas de trailing)
- ❌ Scoring global
- ❌ TP/SL (toujours 0.8%/0.20%)
- ❌ Economic gate (toujours actif)
- ❌ Structural proofs (toujours 2 requis)
- ❌ Momentum fade (toujours restricted, seuil 0.35%)
- ❌ buy_threshold (reste à 30)
- ❌ Micro-trend gate (reste à 0 = désactivé)
- ❌ Frontend (aucune modification)

## Validations

- ✅ **1604 tests** backend passent (6 ajoutés)
- ✅ `tsc --noEmit` clean
- ✅ Audit runtime confirme le diagnostic

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ Version 2.0.7, 1604 tests, feature documentée |
| `CHANGELOG.md` | ✅ Nouvelle entrée [2.0.7] avec détails complets |
| `docs/ROADMAP.md` | — (pas de changement de phase) |
| `docs/requirements_traceability.md` | — (pas de nouvelles exigences formelles) |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## Tests ajoutés

- `TestScalpingV207FastExit::test_stale_exit_reduced_to_5`
- `TestScalpingV207FastExit::test_stale_negative_reduced_to_2`
- `TestScalpingV207FastExit::test_trailing_activation_lowered_to_010`
- `TestScalpingV207FastExit::test_trailing_trail_tightened_to_006`
- `TestScalpingV207FastExit::test_min_capture_positive`
- `TestScalpingV207FastExit::test_aggressive_not_affected`

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.7 |
| Tests backend | 1604 passing ✅ |
| TypeScript | tsc --noEmit clean ✅ |
| Stale exit scalping | 5 min (was 15) |
| Stale négatif | 2 min (was 5) |
| Trailing activation | 0.10% (was 0.15%) |
| Trailing trail | 0.06% (was 0.10%) |

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests complets
cd backend && python -m pytest tests/ -v

# Tests spécifiques v2.0.7
cd backend && python -m pytest tests/test_pivot_v200.py::TestScalpingV207FastExit -v

# Relancer un run propre
curl -X POST http://localhost:8000/paper/account/reset -H "Content-Type: application/json" -d "{\"initial_capital\": 10000}"
curl -X POST http://localhost:8000/paper/profile -H "Content-Type: application/json" -d "{\"profile\": \"scalping\"}"
curl -X POST http://localhost:8000/paper/autonomous/start -H "Content-Type: application/json" -d "{\"interval_seconds\": 5, \"profile\": \"scalping\"}"
```
