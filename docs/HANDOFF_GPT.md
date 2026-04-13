# 🔄 HANDOFF GPT — Dernière intervention

## Date : 13 avril 2026 — v2.0.24

---

## Problème

1. **Limite 30 trades/jour atteinte** — Le robot atteignait `max_trades_per_day=30` après quelques heures et s'arrêtait complètement. L'utilisateur n'avait jamais demandé cette limite.
2. **Cooldown trop long** — Le diagnostic de fréquence identifiait le cooldown comme goulot d'étranglement principal, empêchant le repositionnement rapide après une sortie.

## Diagnostic

- Le profil scalping dans `trading_profile_service.py` avait `max_trades_per_day=30` (ajouté en v2.0.0).
- Le cooldown était configuré à 1 min base, 0.5 min minimum, 5 min maximum.
- Le smart cooldown multipliait par 3x après un stale négatif avec plancher de 2 min.
- Avec le SAS (v2.0.22) et le micro SL (v2.0.23) maintenant en place, ces protections par le temps sont obsolètes.

## Cause racine

Les limites (30 trades/jour) et le cooldown long (1-5 min) avaient été ajoutés comme protection anti-churn AVANT que le SAS et le micro SL existent. Maintenant que :
- Le SAS filtre les mauvaises entrées (10-15s observation virtuelle)
- Le micro SL coupe instantanément à -0.01%

…le cooldown long n'est plus qu'un frein inutile au throughput.

## Correction appliquée

### `backend/app/services/trading_profile_service.py` (profil scalping)
| Paramètre | Avant | Après |
|-----------|-------|-------|
| `max_trades_per_day` | 30 | 999 |
| `cooldown_minutes` | 1 | 0.17 (~10s) |
| `min_cooldown_minutes` | 0.5 | 0.17 (~10s) |
| `max_cooldown_minutes` | 5.0 | 1.0 |

### `backend/app/services/smart_cooldown_service.py`
| Paramètre | Avant | Après |
|-----------|-------|-------|
| Multiplicateur `closed_stale` | 2.0 | 1.3 |
| Multiplicateur stale négatif | 3.0 | 1.5 |
| Plancher stale négatif | 2.0 min | 0.5 min |

### `backend/app/schemas/journal.py`
- `cooldown_minutes`: `int` → `float` (supporte les fractions de minute)

## Ce qui n'a PAS été touché

- Aucun autre profil (aggressive, balanced, conservative) modifié
- Aucun gate d'entrée modifié (SAS, micro SL, economic gate, structural proofs)
- Aucun mécanisme de sortie modifié (trailing, breakeven, gain erosion, stale)
- Aucune logique du smart cooldown modifiée (structure identique, seules les constantes changent)

## Validations

- ✅ **1796 tests** backend passent (0 échec, 12 warnings cosmétiques)
- ✅ 7 fichiers de tests mis à jour pour refléter les nouvelles valeurs
- ✅ Schéma Pydantic accepte les floats pour cooldown_minutes

## Documentation mise à jour

| Document | Changements |
|----------|-------------|
| `docs/CURRENT_STATE.md` | Version 2.0.24, dernier commit, feature v2.0.24 ajoutée |
| `CHANGELOG.md` | Nouvelle entrée [2.0.24] |
| `docs/HANDOFF_GPT.md` | Ce fichier (écrasé) |

## Commit

Message : `feat(scalping): suppression limite 30 trades/jour + cooldown ultra-court (10s) v2.0.24`

## État actuel

- **Version** : v2.0.24
- **Tests** : 1796 passed ✅
- **Le robot peut maintenant** : trader sans limite de nombre, se repositionner en ~10 secondes
- **Prochaine action recommandée** : Lancer le robot toute la nuit et observer le throughput

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v
```
