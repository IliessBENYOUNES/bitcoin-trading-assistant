# HANDOFF GPT — Tick Momentum Confirmation v2.0.13

**Date :** 12 avril 2026  
**Version :** v2.0.13  
**Commit :** `pending`

---

## Problème

Les shorts scalping entraient pendant que le prix montait réellement. Le moteur se basait sur des indicateurs 15 min (lagging) et un cooldown fixe de 1 min entre les trades. Résultat : les shorts étaient immédiatement en négatif dès l'ouverture, restaient négatifs pendant 2 min, puis sortaient via `stale_negative_exit` avec une perte systématique. Le bot ne vérifiait pas la **direction réelle du prix** au moment de l'entrée.

## Diagnostic

| Scénario | Direction signal | Direction prix réelle | Résultat |
|----------|-----------------|----------------------|----------|
| Score -45 (bearish) | SHORT | Prix monte (+$60/10s) | Perte → stale -2 min |
| Score -45 (bearish) | SHORT | Prix descend (-$60/10s) | ✅ Entrée correcte |
| Score +65 (bullish) | LONG | Prix descend (-$30/10s) | Perte → stale -2 min |
| Score +65 (bullish) | LONG | Prix monte (+$30/10s) | ✅ Entrée correcte |

Le problème : le score technique est en **retard** (basé sur des candles 15 min) et peut rester bearish/bullish pendant que le prix va dans l'autre sens. Le cooldown fixe de 1 min ne résout rien car il bloque par le TEMPS, pas par la DIRECTION.

## Cause racine

Absence de vérification de la direction **temps réel** du prix avant l'ouverture de position. Le moteur de décision produit des signaux lagging (15 min) qui ne reflètent pas le mouvement instantané du prix.

## Correction appliquée

### Tick Momentum Confirmation Gate

Nouveau service `TickMomentumService` qui :
1. **Enregistre** le prix à chaque tick dans un buffer circulaire en mémoire
2. **Analyse** les ticks des dernières ~10 secondes avant d'ouvrir
3. **Confirme** ou **rejette** l'entrée selon la direction du prix :
   - SHORT → le prix doit être en **baisse** sur la fenêtre
   - LONG → le prix doit être en **hausse** sur la fenêtre
   - FLAT (< 0.001% de variation) → entrée **rejetée** (bruit)

**Logique :** On prend le premier et le dernier tick dans la fenêtre de 10 sec. Si price_end > price_start → "up". Si price_end < price_start → "down". Si variation < 0.001% → "flat". On calcule aussi le ratio ticks montants/descendants pour le diagnostic.

### Fichiers modifiés

| Fichier | Changement |
|---------|-----------|
| `services/tick_momentum_service.py` | **NOUVEAU** — Service complet (buffer, record, check_direction) |
| `schemas/journal.py` | 3 nouveaux champs : `tick_momentum_enabled`, `window_seconds`, `min_ticks` |
| `services/paper_trading_service.py` | Import TickMomentumService + record_tick à chaque tick + gate avant entrée |
| `services/trading_profile_service.py` | tick_momentum activé sur profil scalping (window=10s, min_ticks=2) |
| `services/journal_service.py` | Label `tick_momentum_mismatch` dans REASON_LABELS |
| `tests/test_pivot_v200.py` | 20 nouveaux tests (service + intégration) |

## Ce qui n'a PAS été touché

- ❌ Cooldown (toujours présent, vérifié APRÈS le tick momentum)
- ❌ Trailing stop, breakeven, gain erosion (inchangés)
- ❌ Bearish veto (inchangé, complémentaire au tick momentum)
- ❌ Market quality gate (inchangé)
- ❌ Profils aggressive/conservative/balanced (tick_momentum_enabled=False)
- ❌ Frontend
- ❌ SL/TP, stale exit, signal contraire

## Validations

- ✅ **1685 tests** backend passent (20 ajoutés)
- ✅ Zéro régression sur les 1665 tests existants
- ✅ `tsc --noEmit` sans erreur frontend

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ v2.0.13, 1685 tests, feature tick momentum |
| `CHANGELOG.md` | ✅ Section v2.0.13 (Added + Changed + Technical) |
| `docs/ROADMAP.md` | ✅ État actuel v2.0.13 |
| `docs/requirements_traceability.md` | ✅ FR-TMC-001, total 1685 tests |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## Commit

```
pending — feat(scalping): tick momentum confirmation v2.0.13
```

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.13 |
| Tests | 1685 passing |
| Phase | Tick momentum confirmation livré |

## Prochaine action recommandée

1. **Full reset + nouveau run** : faire tourner le robot en scalping pendant 1-2h
2. **Vérifier que** :
   - Les shorts ne s'ouvrent QUE quand le prix descend réellement (log "✅ Momentum SHORT confirmé")
   - Les entrées bloquées par tick momentum apparaissent dans les logs ("tick_momentum_mismatch")
   - Le nombre de shorts stagnants/négatifs diminue significativement
   - Le PnL moyen par trade s'améliore
3. **Audit runtime** : `GET /audit/enriched-export` pour vérifier la distribution des non_trade_reason
4. **Si trop de blocages** : ajuster `tick_momentum_window_seconds` (réduire de 10→5 sec) ou `MIN_MOVE_PCT` (réduire de 0.001→0.0005%)

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
cd backend && python -m pytest tests/test_pivot_v200.py::TestTickMomentumServiceV2013 -v
cd backend && python -m pytest tests/test_pivot_v200.py::TestTickMomentumIntegrationV2013 -v
```
