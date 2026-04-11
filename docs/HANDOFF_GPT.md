# HANDOFF GPT — Mini-lot correctif scalping v2.0.3

**Date :** 11 avril 2026  
**Version :** v2.0.3

---

## Problème

L'audit du run nocturne montre un moteur scalping qui trade trop sur du bruit :
- 57 trades fermés
- 52 closed_stale = **91.2%**
- 4 closed_trailing_stop seulement (7%)
- Les 4 trailing stops portent l'essentiel de la valeur
- Le trailing stop est le seul vrai créateur de valeur
- Trop d'entrées scalping qui ne mènent nulle part

## Diagnostic

Le moteur entre en position dès que le score dépasse 25 (buy_threshold) avec le minimum de preuves structurelles, mais la grande majorité des trades n'a pas de tendance sous-jacente suffisante. Le prix stagne dans un range trop étroit pour atteindre le trailing stop activation (0.20%), et les trades meurent en stale après 15 minutes.

## Cause racine

1. **Seuils d'entrée trop bas** : buy_threshold=25 et min_score=25 laissent passer des signaux trop faibles
2. **Pas de filtre micro-tendance** : l'entrée se fait sans vérifier qu'il y a un mouvement directionnel en cours
3. **Trailing activation trop haute** : à 0.20%, la plupart des micro-mouvements n'activent jamais le trailing

## Correction appliquée

### 3 changements ciblés (+ 1 ajustement de cohérence) :

| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| `buy_threshold` | 25 | **30** | Exiger un signal directionnel plus fort |
| `min_score` | 25 | **30** | Relever le plancher de score composite |
| `trailing_stop_activation_pct` | 0.20% | **0.15%** | Rendre le trailing plus atteignable (91% de stale à 0.20%) |
| `min_micro_trend_long` | _(nouveau)_ | **2** | Gate micro-tendance obligatoire pour longs |
| `short_min_score` | 25 | **30** | Aligné avec min_score relevé (cohérence) |

### Fichiers modifiés :

| Fichier | Changement |
|---------|-----------|
| `backend/app/schemas/journal.py` | Ajout champ `min_micro_trend_long` à `TradingProfileParams` |
| `backend/app/services/trading_profile_service.py` | Preset scalping recalibré (4 params modifiés + 1 nouveau) |
| `backend/app/services/paper_trading_service.py` | Gate micro-trend dans la boucle d'entrée (~30 LOC) |
| `backend/app/services/journal_service.py` | Label `micro_trend_insufficient` ajouté à `REASON_LABELS` |
| `backend/tests/test_pivot_v200.py` | 14 tests ajoutés, 2 mis à jour |
| `backend/tests/test_scalping_audit.py` | 3 tests mis à jour |
| `backend/tests/test_diagnostic.py` | 2 tests mis à jour |
| `backend/tests/test_economic_value.py` | 1 test mis à jour |
| `backend/tests/test_paper_trading.py` | 1 test mis à jour |
| `backend/tests/test_short_optimization.py` | 3 tests mis à jour |
| `backend/tests/test_stability.py` | 4 tests mis à jour |

## Ce qui n'a PAS été touché

- ❌ Slot aggressive (sanctuarisé)
- ❌ Scoring global / DecisionService
- ❌ Stale exit logic (durées inchangées : 15min / 5min négatif)
- ❌ Momentum fade (mode restricted inchangé)
- ❌ Economic viability gate (paramètres inchangés)
- ❌ Structural proofs (toujours ≥2)
- ❌ TP/SL (0.8% / 0.20% inchangés)
- ❌ Market quality gate (50 inchangé)
- ❌ Frontend (aucun changement)

## Validations

- ✅ 1556 tests backend passent (14 ajoutés, 0 supprimé)
- ✅ Aucune régression
- ✅ Gate économique toujours valide (expected_capture 0.50% > 0.465%)
- ✅ Aggressive sanctuarisé (aucun paramètre v2.0.3 ne l'affecte)

## Documentation mise à jour

| Document | Changement |
|----------|-----------|
| `docs/CURRENT_STATE.md` | Version v2.0.3, tests 1556, description scalping recalibré |
| `CHANGELOG.md` | Entrée v2.0.3 complète (Changed, Added, Technical) |
| `docs/HANDOFF_GPT.md` | Ce fichier |

## État actuel

- **Version :** v2.0.3
- **Tests :** 1556 passing
- **Prochaine action :** Lancer un nouveau run nocturne pour valider l'impact des changements

## Impact attendu

| Métrique | Avant (audit) | Estimation après |
|----------|--------------|-----------------|
| Nombre de trades | 57 / nuit | ~25-35 (-40% à -55%) |
| % closed_stale | 91.2% (52/57) | ~65-75% |
| % closed_trailing_stop | 7% (4/57) | ~15-25% |
| Win rate net | ~7% | ~15-20% |
| Qualité moyenne | Entrées sur bruit | Entrées avec micro-tendance confirmée |

**Logique de l'estimation :**
- buy_threshold + min_score relevés : ~20-30% des entrées bruit filtrées
- Gate micro-trend ≥ 2 : filtre les longs sans tendance → ~30-40% de trades en moins
- Trailing activation 0.15% : plus de trades activent le trailing → doublement possible des trailing exits
- L'effet combiné est une réduction des entrées + augmentation proportionnelle des trailing

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Tests
cd backend && python -m pytest tests/ -v

# Frontend
cd frontend && npm run dev
```
