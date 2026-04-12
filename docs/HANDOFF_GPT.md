# 🔄 HANDOFF GPT — v2.0.19

**Date :** 12 avril 2026  
**Intervention :** Analyse runtime 33 trades + 3 corrections critiques

---

## Problème

L'export de 33 trades paper trading a révélé 3 problèmes :
1. Le slot aggressive perd -$10.32 sur un trade qui dérive 3h sans protection
2. Le candle reversal exit (v2.0.18) n'a JAMAIS déclenché (0/32 trades)
3. Les trades override sont immédiatement fermés par signal contraire (churn)

## Diagnostic

### Problème 1 : Aggressive sans protection
- Le profil aggressive n'a ni trailing stop, ni gain erosion, ni stale négatif
- Le trade #597 (SHORT, score=-18, confiance LOW) a dérivé 180 min à -0.41% = -$10.32
- Seul le `stale_exit_minutes=180` a fini par le fermer — trop tard

### Problème 2 : Candle reversal jamais actif
- `detect_direction()` utilise `MIN_MOVE_PCT=0.002%` ($1.42 sur BTC)
- Avec des ticks à 5s et une fenêtre de 15s, seulement ~3 ticks
- Le prix bouge souvent < $1.42 en 15s → direction = "flat" → tracker reset
- Le reversal ne persiste jamais assez pour confirmer (3s)

### Problème 3 : Override churn
- Entry reason = "vendre | score=66" (pas préfixé `mean_reversion_`)
- La logique `is_reversal` ne protège que les `mean_reversion_*`
- Score 66 > short_exit_threshold (30) → signal contraire immédiat

## Cause racine

1. Profil aggressive conçu pour du swing long terme mais sans protection intermédiaire
2. Seuil fixe dans `detect_direction()` non adapté à la sensibilité nécessaire pour le reversal
3. L'ajout du tick_override (v2.0.14) n'avait pas mis à jour la logique de protection anti-churn

## Corrections appliquées

### Fichier `trading_profile_service.py`
- Profil `aggressive` : ajout `stale_negative_exit_minutes=60`, `trailing_stop_activation_pct=0.15`, `trailing_stop_drop_ratio=0.30`, `gain_erosion_ratio=0.50`
- Profil `scalping` : `candle_reversal_window_seconds` 15→30

### Fichier `tick_momentum_service.py`
- `detect_direction()` : nouveau paramètre `min_move_pct` (None=0.002% par défaut)
- `check_candle_reversal()` : passe `min_move_pct=0.001` pour sensibilité 2× supérieure

### Fichier `paper_trading_service.py`
- Entry reason des override trades : `tick_override_{direction} | score=...`
- `is_reversal` check : inclut désormais `tick_override_` (long ET short)

## Ce qui n'a PAS été touché

- Le mean reversion (scalping) fonctionne bien (+$15.91 net, non modifié)
- Le profil scalping (entrées, gates, trailing) inchangé sauf la fenêtre reversal
- Le profil conservative et balanced non modifiés
- Le frontend non modifié
- Aucune migration DB nécessaire (paramètres profil uniquement)

## Validations

- ✅ 1730 tests backend passent
- ✅ `tsc --noEmit` frontend sans erreur
- ✅ 2 tests mis à jour pour refléter les nouveaux params aggressive

## Documentation mise à jour

| Document | Changement |
|----------|-----------|
| `docs/CURRENT_STATE.md` | Version 2.0.19, 3 features ajoutées, phase mise à jour |
| `CHANGELOG.md` | Nouvelle entrée [2.0.19] avec Fixed/Changed/Technical |
| `docs/HANDOFF_GPT.md` | Ce fichier |
| `docs/ROADMAP.md` | Non modifié (pas de changement de phase) |
| `docs/requirements_traceability.md` | Non modifié (pas de nouvelles exigences) |

## Commit

`fix(trading): aggressive slot protection + candle reversal sensitivity + override anti-churn v2.0.19`

## État actuel

- **Version :** v2.0.19
- **Tests :** 1730 passing
- **Prochaine action :** Relancer le paper trading pour valider les 3 corrections en runtime

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v
cd frontend && npx tsc --noEmit
```
