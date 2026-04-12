# 🔄 HANDOFF GPT — Dernière intervention

## Titre et date
**feat(scalping): Micro Stop Loss — Sortie immédiate à -0.01% PnL** — 13 avril 2026

## Problème
Le journal des trades montrait des pertes catastrophiques sur certaines positions scalping (ex: -0.87% PnL = -$21.76). Même avec le SAS d'entrée (v2.0.22) qui filtre les mauvaises entrées, le prix peut se retourner APRÈS l'ouverture et dériver vers le SL classique (-0.20% = -$5). L'utilisateur veut zéro tolérance aux pertes.

## Diagnostic
Analyse du journal des trades : les trades les plus destructeurs ont un PnL de -0.87% ($-21.76). Le SL classique à -0.20% est 20× trop large pour l'objectif "quasi-zéro perte". Il faut un garde-fou ultra-serré qui coupe dès le premier signe de perte.

## Cause racine
Aucun mécanisme ne coupait les positions en perte AVANT le trailing stop (qui ne s'active qu'en profit) ou le stale exit (qui attend 2 minutes). Entre l'entrée et ces protections, la perte pouvait grossir librement.

## Correction appliquée

| Fichier | Modification |
|---------|-------------|
| `app/schemas/journal.py` | Ajout du champ `micro_stop_loss_pct: Optional[float]` dans `TradingProfileParams` |
| `app/services/trading_profile_service.py` | Ajout de `micro_stop_loss_pct=0.01` sur le profil scalping |
| `app/services/paper_trading_service.py` | Ajout du check micro SL dans `_tick_single_slot` (après highest/lowest update, avant trailing stop) |
| `tests/test_micro_stop_loss.py` | 18 tests dédiés (profils, calcul PnL, intégration, non-régression) |
| `tests/test_pivot_v200.py` | Adapté `test_stale_still_works_for_never_profitable` et `test_exit_priority_order` |

### Code ajouté (paper_trading_service.py, après ligne 437)
```python
# [v2.0.23] MICRO STOP LOSS — PRIORITÉ ABSOLUE (avant trailing stop)
micro_sl_pct = getattr(profile_params, "micro_stop_loss_pct", None) if profile_params else None
if micro_sl_pct is not None and micro_sl_pct > 0:
    micro_unrealized = self._calc_unrealized_pnl(open_pos, current_price)
    micro_unrealized_pct = (micro_unrealized / open_pos.position_size_usd * 100) if open_pos.position_size_usd > 0 else 0
    if micro_unrealized_pct <= -micro_sl_pct:
        # Sortie immédiate, inconditionnelle
        closed = self._close_position(open_pos, current_price, micro_reason, "closed_micro_sl")
        return PaperTickResult(action_taken="closed_micro_sl", ...)
```

## Ce qui n'a PAS été touché
- Aucune modification du frontend
- Aucune modification de la DB (pas de migration)
- Aucune modification des autres profils (balanced, aggressive, conservative)
- Aucune modification du SAS d'entrée (v2.0.22)
- Le trailing stop, breakeven, stale exit, momentum fade : inchangés (mais le micro SL passe AVANT)

## Validations
- ✅ 1796 tests backend passent (1778 existants + 18 nouveaux)
- ✅ 0 échecs, 10 warnings cosmétiques préexistants
- ✅ Ordre de priorité vérifié par test `test_exit_priority_order`

## Documentation mise à jour
| Document | Ce qui a changé |
|----------|----------------|
| `docs/CURRENT_STATE.md` | Version 2.0.23, tests 1796, nouvelle feature documentée |
| `CHANGELOG.md` | Nouvelle entrée [2.0.23] avec Added/Changed/Technical |
| `docs/HANDOFF_GPT.md` | Ce fichier (écrasé) |

## Commit
`feat(scalping): micro stop loss — sortie immédiate à -0.01% PnL v2.0.23`

## État actuel
| Élément | Valeur |
|---------|--------|
| Version | v2.0.23 |
| Tests | 1796 passing |
| Phase | Micro stop loss déployé |
| Prochaine action | Observer le comportement en runtime : le micro SL devrait réduire drastiquement les pertes. Ajuster le seuil si nécessaire (0.01% peut être trop serré → augmenter à 0.02-0.05% si trop de sorties prématurées). |

## Commandes de relance
```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v
```
