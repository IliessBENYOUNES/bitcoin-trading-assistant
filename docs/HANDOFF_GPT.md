# HANDOFF GPT — Trailing stop relatif v2.0.9

**Date :** 12 avril 2026  
**Version :** v2.0.9  
**Commit :** *en cours*

---

## Problème

Le trailing stop **perdait 50-60% des gains** sur les petits peaks (typiques en scalping). Avec un recul fixe de 0.06%, une position ayant atteint un peak de +0.12% sortait à +0.06% — la moitié du gain gaspillée. L'utilisateur a identifié que le trailing devait être basé sur la **valeur du gain**, pas sur un pourcentage fixe du prix BTC.

## Diagnostic

Le trailing stop utilisait un **recul absolu** :
```
if (peak_pct - current_pct) >= 0.06%:  → exit
```

Exemples de perte :
| Peak PnL | Exit absolu (0.06%) | % du gain perdu |
|----------|---------------------|-----------------|
| 0.10% | 0.04% | **60%** |
| 0.12% | 0.06% | **50%** |
| 0.15% | 0.09% | **40%** |
| 0.50% | 0.44% | **12%** |

Le seuil fixe pénalise les petits gains (les plus fréquents en scalping) et favorise les gros gains (rares).

## Cause racine

Le `trailing_stop_pct` (0.06%) était conçu comme un delta absolu. Pour les peaks proches de l'activation (0.10%), 0.06% de recul représente la majorité du gain. Le ratio gain-perdu/gain-total était inversement proportionnel à la taille du peak.

## Correction appliquée

**Nouveau paramètre : `trailing_stop_drop_ratio = 0.30`**

Le trailing est maintenant **proportionnel au pic de gain** :
```python
retention = 1.0 - 0.30  # = 0.70 → garder 70% du pic
min_gain_pct = peak_pct * retention
if unrealized_pct_now <= min_gain_pct:  → exit
```

Résultats :
| Peak PnL | Exit relatif (30%) | % du gain perdu | vs absolu |
|----------|-------------------|-----------------|-----------|
| 0.10% | 0.07% | **30%** | +30pp mieux |
| 0.12% | 0.084% | **30%** | +20pp mieux |
| 0.15% | 0.105% | **30%** | +10pp mieux |
| 0.50% | 0.35% | **30%** | gros gains respirent |

### Fichiers modifiés

| Fichier | Changement |
|---------|-----------|
| `schemas/journal.py` | Nouveau champ `trailing_stop_drop_ratio: Optional[float]` |
| `services/trading_profile_service.py` | Scalping preset : `trailing_stop_drop_ratio=0.30` |
| `services/paper_trading_service.py` | Logique trailing : mode relatif (prioritaire) + fallback absolu |
| `tests/test_pivot_v200.py` | 5 nouveaux tests `TestTrailingStopRelativeV209` |

## Ce qui n'a PAS été touché

- ❌ Breakeven stop, stale exit, SL/TP, momentum fade
- ❌ Reversal check, shorts bidirectionnels
- ❌ Frontend

## Validations

- ✅ **1622 tests** backend passent (5 ajoutés)
- ✅ `tsc --noEmit` clean

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ v2.0.9, 1622 tests, feature trailing relatif |
| `CHANGELOG.md` | ✅ Section v2.0.9 |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
cd backend && python -m pytest tests/test_pivot_v200.py::TestTrailingStopRelativeV209 -v
```
