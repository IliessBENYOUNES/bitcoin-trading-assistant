# ðŸ”„ HANDOFF GPT â€” DerniÃ¨re intervention

## Date : 23 avril 2026 â€” v2.0.31 (Option A â€” batch 1/2)

> Session dÃ©clenchÃ©e par l'audit du run du 18-23/04 : **MAIN -$338 (WR net 0/51) + EXP -$436 (WR net 6/52)**.

---

## ProblÃ¨me

Audit des 2 nouveaux journaux (51 + 52 trades) post v2.0.30 :

- **MAIN (5173, profil auto)** : capital $10 000 â†’ $9 661 (**-3.38 %**), 51 trades en 8.9 h, **WR net = 0/51**, **WR brut = 67 %**, frais $292 = 86 % de la perte. **100 % des trades sortent via "Signal contraire"** avec gross +$0.04 â†’ net -$7.71 systÃ©matique.
- **EXP (5174, profil scalping)** : capital $10 000 â†’ $9 564 (**-4.36 %**), 52 trades en 105 h, WR net 11.5 %, frais $446 = 102 % de la perte. Bug : `account.total_fees=0` alors que sum(`trade.trading_fees`)=$446. Profil affichÃ© `scalping` mais trades Ã©tiquetÃ©s `aggressive`/`breakout`. Micro_sl Ã  0.15 % (= cout d'entree) ferme 24 trades pour -$304 net.

## Diagnostic

1. **BUG CRITIQUE auto-mode** : dans `paper_trading_service._tick_single_slot`, le profil utilisÃ© pour Ã©valuer la sortie d'une position Ã©tait re-rÃ©solu **Ã  chaque tick** via `auto_select_profile(score, confidence)` au lieu d'utiliser le profil d'entrÃ©e. ConsÃ©quence :
   - Trade ouvert sur slot **scalping** (min_hold=300, opposite_signal_exit=False)
   - 3 min plus tard, score=62 + confidence=high â†’ resolve = **aggressive** (qui n'avait pas de min_hold)
   - `trade_too_young = False` â†’ "Signal contraire" dÃ©clenche â†’ -$7.71 net
2. **Sortie "Signal contraire" = piÃ¨ge fees mÃ©canique** : la capture moyenne avant ce signal (0.04 % = $1) est < frais round-trip ($7.75) â‡’ chaque trade est une perte garantie mÃªme quand la direction est correcte.
3. **EXP** : micro_stop_loss aggressive (0.15 %) plus serrÃ© que le coÃ»t d'entrÃ©e (0.155 %) ; trailing drop 80 % laisse partir 80 % du gain ; bug d'agrÃ©gation total_fees cÃ´tÃ© account.

## Cause racine

Le mÃ©canisme de **re-rÃ©solution dynamique du profil** en mode auto a Ã©tÃ© introduit pour adapter les seuils d'entrÃ©e selon la force du signal. Il a Ã©tÃ© appliquÃ© par erreur **aussi pendant le monitoring**, ce qui faisait basculer un trade vers les params d'un autre profil sans respecter les contrats d'entrÃ©e (notamment `min_hold_seconds` et `opposite_signal_exit_enabled`).

## Corrections appliquÃ©es (v2.0.31 â€” Option A batch 1/2)

### Fichiers modifiÃ©s

| Fichier | Changement |
|---------|------------|
| `backend/app/schemas/journal.py` | +1 champ `TradingProfileParams.opposite_signal_exit_enabled: bool = True` |
| `backend/app/services/trading_profile_service.py` | `scalping.opposite_signal_exit_enabled = False` ; `aggressive.opposite_signal_exit_enabled = False`, `min_hold_seconds = 300`, `short_min_hold_seconds = 300` |
| `backend/app/services/paper_trading_service.py` | Mode `auto` â†’ utilise `PROFILE_PRESETS[open_pos.profile_type]` (slot d'entrÃ©e, fallback ancien si profile_type inconnu) ; bloc "Signal contraire" gatÃ© par `opposite_signal_exit_enabled` |

### Avant / AprÃ¨s â€” `_tick_single_slot` (extrait)

**Avant :**
```python
if is_auto_mode:
    resolved_profile = TradingProfileService.auto_select_profile(score, confidence)
    profile_params = PROFILE_PRESETS[resolved_profile]
```

**AprÃ¨s :**
```python
if is_auto_mode:
    entry_profile = (open_pos.profile_type or "").strip()
    if entry_profile in PROFILE_PRESETS:
        profile_params = PROFILE_PRESETS[entry_profile]
    else:
        # Fallback ancien comportement
        resolved_profile = TradingProfileService.auto_select_profile(score, confidence)
        profile_params = PROFILE_PRESETS[resolved_profile]
```

Et le bloc "Signal contraire" :
```python
opposite_signal_exit_enabled = bool(getattr(profile_params, "opposite_signal_exit_enabled", True))
if not opposite_signal_exit_enabled:
    pass  # skip toute la logique de sortie sur signal contraire
elif open_pos.direction == "long":
    ...
```

## Ce qui n'a PAS Ã©tÃ© touchÃ©

- âœ… Frontend (aucun changement UI dans cette intervention)
- âœ… Profils `conservative` et `balanced` (`opposite_signal_exit_enabled=True` par dÃ©faut â†’ comportement antÃ©rieur)
- âœ… SL / TP / trailing / breakeven / stale / micro_sl / gain_erosion / candle_reversal (tous intacts)
- âœ… Moteur expÃ©rimental (worktree `bitcoin-trading-v2-experiment`) â€” corrections F3-F7 prÃ©vues en batch 2
- âœ… Frais dÃ©jÃ  intÃ©grÃ©s (v2.0.29) â€” aucun changement de la formule `_close_position`
- âœ… SchÃ©mas Pydantic rÃ©tro-compatibles (`opposite_signal_exit_enabled` a un default `True`)

## Validations

- âœ… **1775 tests backend passent** (+2 vs baseline v2.0.30 1773)
- âœ… **33 failed** (-2 vs baseline 35) â€” aucune nouvelle rÃ©gression
- âœ… `tsc --noEmit` frontend exit 0
- âœ… Validation runtime des presets : `scalping.opposite_signal_exit_enabled=False`, `aggressive.opposite_signal_exit_enabled=False, min_hold_seconds=300, short_min_hold_seconds=300`, `balanced.opposite_signal_exit_enabled=True`

## Documentation mise Ã  jour

| Document | Changements |
|----------|-------------|
| `CHANGELOG.md` | EntrÃ©e [2.0.31] (Fixed : bug auto-mode ; Added : opposite_signal_exit_enabled + aggressive.min_hold ; Changed : _tick_single_slot ; Technical : 1775/33) |
| `docs/CURRENT_STATE.md` | Version 2.0.31, date 23/04, tests 1775/33, ligne phase courante |
| `docs/ROADMAP.md` | Ã‰tat actuel v2.0.31 + ligne timeline v2.0.31 |
| `docs/ENGINE_AUDIT.md` | Section 7 ajoutÃ©e â€” Audit run 23/04 + corrections v2.0.31 (option A batch 1/2) + plan batch 2 (F3-F7) |
| `docs/HANDOFF_GPT.md` | Ce fichier (Ã©ditÃ©, pas recrÃ©Ã©) |

## Ã‰tat actuel

- **Version** : v2.0.31
- **Tests backend** : 1775 passed / 33 failed (rÃ©gressions prÃ©existantes v2.0.29-v2.0.30)
- **Frontend** : tsc clean âœ…
- **StratÃ©gie** : Option A â€” itÃ©rative en 2 batches
  - **Batch 1 livrÃ© (v2.0.31)** : F1 (opposite_signal_exit toggle) + F2 (fix monitoring auto-mode) + F8 (min_hold aggressive)
  - **Batch 2 Ã  livrer aprÃ¨s validation 1 nuit** : F3 (micro_sl aggressive OFF), F4 (trailing drop 50% + min_peak 3Ã— fees), F5 (gate macro anti-SHORT en uptrend), F6 (capture â‰¥ 0.65%), F7 (bug total_fees EXP)

## Prochaine action recommandÃ©e

1. **Reset les comptes paper trading** des 2 moteurs (MAIN + EXP)
2. **Relancer 1 nuit** (au moins 12 h) en mode auto
3. **Exporter les journaux** au matin
4. **VÃ©rifier les mÃ©triques de succÃ¨s** :
   - 0 trade scalping/aggressive fermÃ© via "Signal contraire"
   - DurÃ©e moyenne scalping > 5 min (vs 326 s actuel)
   - WR net > 30 % (vs 0 % actuel)
   - PnL net > -$50 sur 24 h (vs -$338 actuel)
5. Si succÃ¨s â†’ enchaÃ®ner batch 2 (F3-F7). Sinon â†’ analyser les logs pour identifier le prochain destructeur de valeur.

## Commandes de relance

```powershell
# Voir docs/SERVERS.md pour la procÃ©dure complÃ¨te des 4 serveurs

# MAIN
Start-Process powershell -ArgumentList "-NoExit","-Command","cd C:\Users\ilies\git\bitcoin-trading-assistant\backend; .\venv\Scripts\activate; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit","-Command","cd C:\Users\ilies\git\bitcoin-trading-assistant\frontend; npx vite --port 5173"

# EXPERIMENTAL
Start-Process powershell -ArgumentList "-NoExit","-Command","cd C:\Users\ilies\git\bitcoin-trading-v2-experiment\backend; .\venv\Scripts\activate; python -m uvicorn app.main:app --host 127.0.0.1 --port 8001"
Start-Process powershell -ArgumentList "-NoExit","-Command","cd C:\Users\ilies\git\bitcoin-trading-v2-experiment\frontend; npx vite --port 5174"

# Tests
cd backend ; .\venv\Scripts\python.exe -m pytest tests/ -q --no-header --tb=no

# Reset paper trading + start robot autonome MAIN
curl -X POST http://localhost:8000/paper/account/reset
curl -X POST http://localhost:8000/paper/autonomous/start -H "Content-Type: application/json" -d '{"interval_seconds": 5, "profile": "auto"}'

# Export journal aprÃ¨s run
curl http://localhost:8000/paper/journal/export > docs/journaux/btc-trading-journal-2026-04-24-PORT5173.json
curl http://localhost:8001/paper/journal/export > docs/journaux/btc-trading-journal-2026-04-24-PORT5174.json
```
