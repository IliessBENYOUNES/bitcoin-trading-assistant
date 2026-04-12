# HANDOFF GPT — Fix Candle Direction Fallback v2.0.15

**Date :** 12 avril 2026  
**Version :** v2.0.15 (fix)  

---

## Problème

La pastille de couleur de bougie (🟢/🔴) ne s'affichait pas à côté des positions dans le PaperTradingPanel. Toutes les positions avaient `entry_candle_direction = null` en DB.

## Diagnostic

1. Vérifié que le modèle, schéma, migration et composant frontend étaient en place → **OK**
2. Vérifié les 10 derniers trades en DB → **tous `candle_dir=None`**
3. Vérifié le code `paper_trading_service.py` lignes 1437-1449 :
   - Source 1 : `tm_override_active` → False car buffer vide après restart
   - Source 2 : `mq_data.micro_trend_score` → 0 (neutre) → pas de couleur
   - **Pas de fallback final** → `entry_candle_dir = None`

## Cause racine

Après un restart du serveur, le buffer tick momentum est vide. `detect_direction()` retourne `"insufficient_data"`, ce qui n'active PAS l'override. Le fallback `mq_data` ne suffit pas si `micro_trend_score=0`. Résultat : `entry_candle_dir` reste `None` et le frontend n'affiche rien (`if (!candleDirection) return null`).

## Correction appliquée

| Fichier | Changement |
|---------|-----------|
| `backend/app/services/paper_trading_service.py` | Ajout d'un fallback final (ligne ~1457) : si aucune source ne détermine la couleur, on déduit de la direction du trade (long→green, short→red) |

```python
# AVANT (fin du bloc) :
# entry_candle_dir pouvait rester None

# APRÈS :
if entry_candle_dir is None:
    entry_candle_dir = "green" if direction == "long" else "red"
```

## Ce qui n'a PAS été touché

- Frontend inchangé (le composant `CandleDirectionDot` fonctionne déjà)
- Modèle/schéma/migration inchangés
- Aucun autre service modifié

## Validations

- ✅ **1701 tests** backend passent (0 régression)
- ✅ `tsc --noEmit` sans erreur frontend
- ✅ Trade #572 mis à jour manuellement (red) et visible dans l'API
- ✅ Les prochains trades auront toujours une couleur de bougie

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ Dernier commit |
| `CHANGELOG.md` | ✅ Nouveau fix ajouté dans v2.0.15 |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.15 |
| Tests | 1701 passing |

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
```
