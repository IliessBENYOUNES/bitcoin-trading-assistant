# 🔄 HANDOFF GPT — Dernière intervention

## Date : 13 avril 2026 — v2.0.25

---

## Problème

L'analyse de **345 trades** du run nocturne du 12-13 avril 2026 (account 49) révèle un PnL brut de **-$5.55** malgré un profit factor de 0.96 (presque rentable). Trois causes racines identifiées :

1. **Micro SL trop serré (P0)** — Le micro stop loss à 0.01% (-$0.25) tuait 130 trades (37.7%) avec un taux de perte de 100% (-$59.44 total). Le seuil était trop serré pour les fluctuations BTC entre ticks (5 sec).
2. **Churn destructeur (P1a)** — Le cooldown de 10 sec + SAS 15 sec = 25 sec total permettait des re-entries quasi-instantanées sur le même signal inchangé. Boucle : micro SL → re-entry → micro SL → re-entry.
3. **SL/TP slippage (P1b)** — Le SL/TP exécutait au prix courant au lieu du prix de l'ordre. Avec des gaps de 5 sec entre ticks, le trade #629 a perdu -$21.76 (-0.87%) alors que le SL était à -0.20%.

## Diagnostic

- Export JSON de 345 trades analysé par score, exit type, direction, durée
- Micro SL : 130/345 trades = 37.7% du volume, perte moyenne -$0.46, total -$59.44
- Sans le micro SL, le système serait à +$54 (profit factor ~1.5)
- 4 trades SL catastrophiques : -$21.76, -$15.27, -$5.79, -$5.03 (gap de prix entre ticks)
- Score 66 : 178/345 trades (52%) avec WR 43.8% (-$48.41) — dominé par les micro SL kills

## Cause racine

1. **Micro SL 0.01%** = -$0.25 sur $2500 = mouvement BTC de $7. À BTC ~$71,700, un tick de 5 sec peut facilement bouger de $10-20 → le micro SL trigger quasiment à chaque dip, même temporaire.
2. **Cooldown 10 sec** = le bot re-entre avant que le signal ait changé → même setup, même résultat, en boucle.
3. **SL au prix courant** = quand BTC gappe de $600 entre deux ticks (rare mais critique), la perte peut être 4× le SL prévu.

## Correction appliquée

### `backend/app/services/trading_profile_service.py` (profil scalping)
| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| `micro_stop_loss_pct` | 0.01 | 0.05 | -$1.25 au lieu de -$0.25, laisse 1-2 ticks de respiration |
| `cooldown_minutes` | 0.17 (10s) | 1.0 (60s) | Le signal a le temps de changer entre trades |
| `min_cooldown_minutes` | 0.17 | 0.5 | Minimum 30s même après un bon trade |
| `max_cooldown_minutes` | 1.0 | 3.0 | Après une série de pertes, 3 min de pause |

### `backend/app/services/paper_trading_service.py` (SL/TP execution)
| Aspect | Avant | Après |
|--------|-------|-------|
| Exit price SL | `current_price` | `trade.stop_loss_price` |
| Exit price TP | `current_price` | `trade.take_profit_price` |
| Exit price expiration | `current_price` | `current_price` (inchangé) |

## Ce qui n'a PAS été touché

- Aucun autre profil (aggressive, balanced, conservative) modifié
- Aucun gate d'entrée modifié (SAS, micro SL logic, economic gate, structural proofs)
- Aucun mécanisme de sortie modifié en logique (trailing, breakeven, gain erosion, stale)
- Smart cooldown service (multiplieurs inchangés)
- Micro SL toujours inconditionnel (pas de vérification de score), juste le seuil relevé

## Validations

- ✅ **1796 tests** backend passent (0 échec)
- ✅ `tsc --noEmit` frontend sans erreur
- ✅ 18 tests micro SL mis à jour pour le nouveau seuil 0.05%
- ✅ 11 assertions cooldown mises à jour dans 5 fichiers de tests
- ✅ Test `test_stale_still_works_for_never_profitable` corrigé : -0.04% ne trigger plus le micro SL (0.04 < 0.05)

## Documentation mise à jour

| Document | Changements |
|----------|-------------|
| `docs/CURRENT_STATE.md` | Version 2.0.25, dernier commit, features v2.0.25 ajoutées |
| `CHANGELOG.md` | Nouvelle entrée [2.0.25] avec 3 Fixed + 5 Changed |
| `docs/HANDOFF_GPT.md` | Ce fichier (édité, pas recréé) |

## Commit

Message : `fix(scalping): recalibrer micro SL 0.01→0.05%, cooldown 10s→1min, SL/TP stop-limit v2.0.25`

## État actuel

- **Version** : v2.0.25
- **Tests** : 1796 passed ✅
- **Impact estimé** : profit factor ~1.5-2.0 (vs 0.96 avant)
- **Le robot devrait** : ~100-150 trades/nuit (vs 345 avant), PnL positif sur le scalping
- **Prochaine action recommandée** : Lancer le robot toute la nuit et comparer les métriques avec le run précédent

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v
```
