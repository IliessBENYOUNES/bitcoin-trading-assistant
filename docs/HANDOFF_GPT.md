# HANDOFF_GPT — v2.0.18

## Date : 12 avril 2026

---

## Problème
L'utilisateur a observé que les trades profitables gardent la même couleur de pastille (entrée=sortie), tandis que les perdants changent de couleur. Il demande :
1. Que le changement de couleur de bougie devienne un **déclencheur de sortie ACTIF** (pas juste du learning)
2. Que le **délai entre le changement de couleur et la sortie** soit tracké pour le ML
3. Que le **layout UI** du TAB Trading soit restructuré (Risk compact, Paper pleine largeur)

## Diagnostic
- Pattern empirique confirmé : le seul trade profitable (+7.47$) avait la même couleur de pastille à l'entrée et à la sortie
- Tous les trades perdants avaient un changement de couleur → le momentum s'est inversé et le robot est resté trop longtemps
- Le TickMomentumService existant (v2.0.14) détecte déjà la direction du prix en temps réel → réutilisable pour la détection de reversal

## Cause racine
- Le robot n'avait aucun mécanisme pour détecter et réagir au changement de direction de la bougie PENDANT une position ouverte
- Les mécanismes de sortie existants (trailing stop, breakeven, stale) sont tous basés sur le PnL ou le temps, pas sur la direction du prix
- Le layout côte-à-côte Risk/Paper gaspillait de l'espace (Risk à 42% de largeur)

## Correction appliquée

### A. Candle Reversal Exit (backend)
- **`tick_momentum_service.py`** : Ajout de `_reversal_start` dict, `check_candle_reversal()` et `reset_reversal()`. La méthode compare la direction actuelle du prix (via `detect_direction()`) avec la couleur de bougie à l'entrée du trade. Si la couleur s'est inversée de manière défavorable et persiste ≥3 secondes, déclenche la sortie.
- **`paper_trading_service.py`** : Dans `_tick_single_slot`, nouveau check entre gain_erosion/breakeven et stale exit. Si `candle_reversal_exit_enabled=True` et que `check_candle_reversal()` retourne `should_exit=True`, ferme la position avec status `closed_candle_reversal`. Reset le tracker de reversal à l'ouverture et à la fermeture.
- **`trading_profile_service.py`** : Profil scalping activé avec `candle_reversal_exit_enabled=True`, `candle_reversal_min_seconds=3.0`, `candle_reversal_window_seconds=15.0`.

### B. Reversal Delay Tracking (backend + ML)
- **`paper_account.py`** : Nouveau champ `reversal_delay_seconds` (Float, nullable) sur `PaperTrade`
- **`learning.py`** : Nouveau champ `reversal_delay_seconds` (Float, nullable) sur `LearningSignal`
- **`learning_service.py`** : `record_sample()` copie le `reversal_delay_seconds` du trade. Pattern 9 : analyse fast (<5s) vs slow (≥5s), méta-pattern reversal vs normal exit.
- **`journal.py`** : 3 nouveaux params `TradingProfileParams` : `candle_reversal_exit_enabled`, `candle_reversal_min_seconds`, `candle_reversal_window_seconds`

### C. UI Layout (frontend)
- **`Dashboard.tsx`** : TAB 2 restructuré de `Grid lg={5}+lg={7}` côte-à-côte vers 4 `Grid xs={12}` empilés (Risk → Paper → Journal → Diagnostic)
- **`PaperTradingPanel.tsx`** : EXIT_TYPE_LABELS enrichi (+breakeven, +gain_erosion, +candle_reversal). `CandleDirectionDot` accepte `reversalDelay` prop. Tooltip de sortie affiche le délai de reversal.
- **`api.ts`** : `reversal_delay_seconds` ajouté à `PaperTradeItem` et `PaperTradeExportItem`

## Ce qui n'a PAS été touché
- Les profils conservative, balanced, aggressive (candle_reversal_exit_enabled=False par défaut)
- Le trailing stop, breakeven, gain erosion, stale exit (inchangés)
- Le scoring, les indicateurs, les signaux
- Le risk engine, le kill switch
- Les endpoints API (aucun nouveau endpoint)

## Validations
- ✅ **1730 tests** backend passent (1718 + 12 nouveaux)
- ✅ `tsc --noEmit` sans erreur (exit code 0)
- ✅ Migration `migrate_v2018.py` exécutée sur test.db
- ✅ 12 tests dédiés couvrent : détection reversal, annulation, timing, learning record, patterns

## Documentation mise à jour
| Document | Changement |
|----------|------------|
| `docs/CURRENT_STATE.md` | Version 2.0.18, 1730 tests, features v2.0.17-18 ajoutées |
| `CHANGELOG.md` | Entrée complète v2.0.18 (Added/Changed/Technical) |
| `docs/ROADMAP.md` | Pas de changement de phase |
| `docs/requirements_traceability.md` | Version 2.0.18, test_candle_reversal.py (12 tests), total 1730 |
| `docs/HANDOFF_GPT.md` | Ce fichier |

## Commit
- Message : `feat(trading): candle reversal exit + reversal_delay_seconds + UI layout v2.0.18`

## État actuel
- Version : v2.0.18
- Tests : 1730 passing
- TypeScript : 0 erreur
- Backend : doit être relancé pour charger les nouvelles colonnes et la logique de reversal exit
- Frontend : doit être relancé pour le nouveau layout

## Commandes de relance
```bash
# Backend
cd backend && .\venv\Scripts\activate && python migrate_v2018.py test.db && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev
```

## Prochaine action recommandée
- Observer les trades en temps réel pour valider que le `closed_candle_reversal` se déclenche correctement
- Analyser si le délai de 3 secondes est optimal (trop court = faux positifs sur bruit, trop long = pertes inutiles)
- Si les sorties reversal sont trop fréquentes, augmenter `candle_reversal_min_seconds` à 5s
- Si elles ne se déclenchent pas assez, réduire à 2s
