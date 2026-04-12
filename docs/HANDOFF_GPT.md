# HANDOFF GPT — Exit Candle Direction + Timestamps + Run Duration v2.0.16

**Date :** 12 avril 2026  
**Version :** v2.0.16 (feature)  

---

## Problème

Seule la pastille d'entrée était affichée. Aucune info sur la couleur de bougie à la sortie, pas de timestamp précis, pas de durée du run visible. Le modèle ML ne pouvait pas apprendre des patterns entrée/sortie.

## Diagnostic

1. `_close_position()` ne déterminait pas la direction de la bougie à la fermeture → `exit_candle_direction` inexistant
2. Le journal affichait seulement la durée en heures (arrondi) → perte de précision pour les trades courts
3. Le `LearningSignal` ne stockait aucune info sur les couleurs de bougie → données ML incomplètes
4. Pas de compteur de durée du run visible en temps réel

## Cause racine

Feature manquante — le v2.0.15 avait posé la base avec `entry_candle_direction` mais sans l'équivalent côté sortie.

## Correction appliquée

| Fichier | Changement |
|---------|-----------|
| `backend/app/models/paper_account.py` | + colonne `exit_candle_direction VARCHAR(10)` |
| `backend/app/models/learning.py` | + colonnes `entry_candle_direction`, `exit_candle_direction` |
| `backend/app/schemas/paper_trading.py` | + `exit_candle_direction`, `duration_seconds`, `model_post_init` |
| `backend/app/services/paper_trading_service.py` | `_close_position` détermine exit candle (tick momentum + fallback prix) |
| `backend/app/services/learning_service.py` | `record_sample` copie les deux candle directions |
| `frontend/src/types/api.ts` | + `exit_candle_direction`, `duration_seconds` |
| `frontend/src/hooks/usePaperTrading.ts` | + `autoStartedAt` state |
| `frontend/src/components/PaperTradingPanel.tsx` | + `RunDurationTimer`, `formatPreciseTime`, `formatDurationSec`, CandleDirectionDot enrichi, TradeRow enrichi |
| `backend/migrate_v2016.py` | Migration DB |
| `backend/tests/test_paper_trading.py` | +8 tests |

## Ce qui n'a PAS été touché

- Logique d'ouverture de position inchangée
- `entry_candle_direction` existant inchangé (rétrocompat)
- Aucun autre service modifié
- Pas de changement d'endpoint API

## Validations

- ✅ **1709 tests** backend passent (0 régression, +8 nouveaux)
- ✅ `tsc --noEmit` sans erreur frontend
- ✅ Migration DB PostgreSQL réussie (3 colonnes ajoutées)

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ Version, tests, dernier commit |
| `CHANGELOG.md` | ✅ Nouvelle section v2.0.16 complète |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.16 |
| Tests | 1709 passing |
| Frontend | tsc clean |

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
```
