# HANDOFF GPT — Candle Direction Override v2.0.14

**Date :** 12 avril 2026  
**Version :** v2.0.14  
**Commit :** `399da2a`

---

## Problème

Deux problèmes majeurs identifiés en observation runtime :

1. **Fenêtre tick momentum trop courte (10 sec)** — Avec des ticks toutes les 5 sec, seulement 2-3 points de données. En pleine volatilité d'une bougie, ça ne suffisait pas pour déterminer si le prix monte ou descend réellement.

2. **Biais 100% short** — Le decision service utilise des indicateurs 15 min (lagging) qui restaient bearish en marché ranging, produisant UNIQUEMENT des recommendations SHORT (score < -20). Le buy_threshold=30 était rarement atteint. Le bearish_veto bloquait les rares tentatives de LONG (micro_trend < 0). Résultat : aucun LONG observé pendant plus d'une heure, même quand le BTC alternait entre montées et baisses.

## Diagnostic

| Condition | Score technique | Direction prix 30s | Avant v2.0.14 | Après v2.0.14 |
|-----------|----------------|-------------------|---------------|---------------|
| Score -30, prix monte | SHORT | UP | SHORT → perte | LONG ✅ |
| Score -30, prix descend | SHORT | DOWN | SHORT | SHORT ✅ |
| Score +15 (attendre), prix monte | HOLD | UP | Pas de trade | LONG ✅ |
| Score +15 (attendre), prix descend | HOLD | DOWN | Pas de trade | SHORT ✅ |
| Score +35, prix descend | LONG | DOWN | LONG → perte | SHORT ✅ |
| Score -25, prix flat | SHORT | FLAT | SHORT → risque | Pas de trade ✅ |

## Cause racine

1. Les indicateurs 15 min sont **lagging** : le score reste bearish pendant des minutes alors que le prix alterne haut/bas.
2. Les seuils BUY/SELL sont **asymétriques** (BUY=30, SELL=20) : plus facile de shorter que de longer.
3. Le bearish_veto bloque les LONG quand micro_trend < 0, mais rien ne bloque les SHORT quand le prix monte.
4. Le check "attendre" empêche tout trade quand le score est modéré (-20 à +30), même si le prix bouge clairement.

## Correction appliquée

### Candle Direction Override

En scalping, la direction du trade est maintenant déterminée par la direction **RÉELLE du prix** sur les 30 dernières secondes :

- **Bougie verte** (prix monte) → entre **LONG**
- **Bougie rouge** (prix descend) → entre **SHORT**
- **Bougie neutre** (flat < 0.002%) → **pas de trade**

Le score technique n'est plus qu'un **filtre de qualité** (|score| >= 10 quand override actif) — il vérifie que le marché est actif, mais ne détermine plus la direction.

### Fichiers modifiés

| Fichier | Changement |
|---------|-----------|
| `services/tick_momentum_service.py` | Ajout `detect_direction()`, buffer 200→500, MIN_MOVE 0.001→0.002% |
| `schemas/journal.py` | 2 nouveaux champs : `tick_momentum_override_direction`, `tick_momentum_min_score` |
| `services/paper_trading_service.py` | Override direction TÔT dans le pipeline + skip bearish_veto/reversal/attendre |
| `services/trading_profile_service.py` | window 10→30s, min_ticks 2→3, override=True, min_score=10 |
| `services/journal_service.py` | Labels `tick_momentum_no_direction`, `tick_momentum_override` |
| `tests/test_pivot_v200.py` | 9 nouveaux tests + mise à jour tests existants |

### Pipeline de gates modifié

```
1. Decision (score, action) — lagging 15 min
2. Market quality computation
3. ★ CANDLE DIRECTION OVERRIDE ★ (NOUVEAU — v2.0.14)
   - Si override actif : detect_direction() → up=LONG, down=SHORT, flat=HOLD
   - Si override inactif : flow classique
4. Scalping reversal — SKIPPÉ si override actif
5. Check "attendre" — BYPASSÉ si override actif
6. Market quality gate
7. Economic viability gate
8. Structural proofs
9. Micro-trend gate
10. Bearish veto — SKIPPÉ si override actif
11. Tick momentum confirmation — SKIPPÉ si override actif (redondant)
12. Score minimum (réduit à 10 si override actif)
13. Cooldown, max_trades, risk
14. Open position
```

## Ce qui n'a PAS été touché

- ❌ Trailing stop, breakeven, gain erosion (inchangés)
- ❌ SL/TP, stale exit, signal contraire (inchangés)
- ❌ Profils aggressive/conservative/balanced (override=False)
- ❌ Market quality gate, economic gate, structural proofs (toujours actifs)
- ❌ Cooldown, max_trades_per_day (toujours actifs)
- ❌ Frontend

## Validations

- ✅ **1694 tests** backend passent (9 ajoutés)
- ✅ Zéro régression sur les 1685 tests existants
- ✅ `tsc --noEmit` sans erreur frontend

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ v2.0.14, 1694 tests, feature candle direction |
| `CHANGELOG.md` | ✅ Section v2.0.14 (Added + Changed + Fixed + Technical) |
| `docs/ROADMAP.md` | ✅ État actuel v2.0.14 |
| `docs/requirements_traceability.md` | ✅ FR-CDO-001, total 1694 tests |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## Commit

```
399da2a — feat(scalping): candle direction override v2.0.14
```

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.14 |
| Tests | 1694 passing |
| Phase | Candle direction override livré |

## Prochaine action recommandée

1. **Full reset + nouveau run** : faire tourner le robot en scalping pendant 1-2h
2. **Vérifier que** :
   - Des LONG apparaissent quand le prix monte (log "🟢 Bougie verte → LONG")
   - Des SHORT apparaissent quand le prix descend (log "🔴 Bougie rouge → SHORT")
   - Les bougies flat sont bloquées (log "⚪ Bougie neutre")
   - Le ratio long/short est ~50/50 en marché ranging
   - Le PnL moyen par trade s'améliore (entrées dans le sens du prix)
3. **Si trop de blocages "flat"** : réduire `MIN_MOVE_PCT` de 0.002→0.001%
4. **Si les positions perdent quand même** : la fenêtre de 30 sec peut être ajustée (20→45 sec)
5. **Audit runtime** : `GET /audit/enriched-export` pour vérifier la distribution des actions

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
cd backend && python -m pytest tests/test_pivot_v200.py::TestTickMomentumServiceV2013 -v
cd backend && python -m pytest tests/test_pivot_v200.py::TestTickMomentumIntegrationV2013 -v
```
