# HANDOFF GPT — Downtrend protection v2.0.10

**Date :** 12 avril 2026  
**Version :** v2.0.10  
**Commit :** *en cours*

---

## Problème

7/33 trades entrent **LONG pendant que le BTC descend**, résultant en **-$10.44 de pertes** (tous fermés par stale_negative_exit en 2 min). Le score technique de 65 est en retard (basé sur des indicateurs 15min lagging : RSI ~55, SMA bullish, EMA9>EMA21) et reste bullish pendant le pullback. Le trailing stop ne peut rien y faire — c'est un problème d'**entrée**, pas de **sortie**.

## Diagnostic

| Tick | Score | Action | micro_trend | Résultat |
|------|-------|--------|-------------|----------|
| 1-7 | 65 | acheter | -2 | LONG → stale_negative → -$1.49 chacun |

Le score 65 > buy_threshold 30 → entrée systématique. Le `micro_trend_score = -2` (bearish) était ignoré pour les entrées LONG (le gate était désactivé à 0). Le reversal check ne détectait pas non plus la tendance baissière car il ne recevait pas les données de micro-trend.

## Cause racine

1. **Score technique en retard** : les indicateurs 15min (RSI, SMA, EMA) sont lagging et restent bullish pendant un pullback court
2. **micro_trend ignoré** : le gate `min_micro_trend_long=0` était désactivé, donc `micro_trend_score=-2` ne bloquait pas les LONG
3. **Reversal aveugle** : le reversal check ne recevait pas `mq_data`, donc ne voyait pas la micro-tendance baissière
4. **mq_data calculé trop tard** : le market quality était évalué APRÈS le reversal check, donc les données n'étaient pas disponibles

## Correction appliquée

### 1. Veto bearish (NOUVEAU)
```python
# AVANT : rien ne bloquait un LONG quand micro_trend < 0
# APRÈS : veto si micro_trend < 0 ET direction = long ET pas un reversal
if mq_data and not scalping_reversal:
    mt = mq_data.get("micro_trend_score", 0) or 0
    if direction_check == "long" and mt < 0:
        return "bearish_veto"  # LONG bloqué
```

### 2. Reversal enrichi (Source 4 micro-trend)
```python
# AVANT : _scalping_reversal_check(decision_result)
# APRÈS : _scalping_reversal_check(decision_result, mq_data=mq_data)
# + Source 4 : micro_trend ≤ -2 → signal overbought → SHORT
# + Source 4 : micro_trend ≥ 3 → signal oversold → LONG
```

### 3. Réordonnancement mq_data AVANT reversal
```
# AVANT : reversal → action_wait → market_quality → gates → entrée
# APRÈS : market_quality → reversal (enrichi) → action_wait → gates → veto bearish → entrée
```

### Fichiers modifiés

| Fichier | Changement |
|---------|-----------|
| `services/paper_trading_service.py` | Réordonnancement mq_data, veto bearish, reversal Source 4, signature `_scalping_reversal_check(decision, mq_data=None)` |
| `services/journal_service.py` | Nouveau label `bearish_veto` dans `REASON_LABELS` |
| `tests/test_pivot_v200.py` | 11 nouveaux tests `TestDowntrendProtectionV2010` |

## Ce qui n'a PAS été touché

- ❌ Trailing stop (v2.0.9 — déjà corrigé)
- ❌ Breakeven stop, stale exit, SL/TP, momentum fade
- ❌ Profils aggressive/conservative/balanced
- ❌ Frontend
- ❌ Paramètres du profil scalping (buy_threshold, min_score, etc.)

## Validations

- ✅ **1635 tests** backend passent (11 ajoutés)
- ✅ `tsc --noEmit` clean
- ✅ Zéro régression sur les 1622 tests existants

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ v2.0.10, 1635 tests, feature downtrend protection |
| `CHANGELOG.md` | ✅ Section v2.0.10 (Fixed + Added + Technical) |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.10 |
| Tests | 1635 passing |
| tsc | Clean |
| Phase | Downtrend protection livré |

## Prochaine action recommandée

1. **Déployer et observer** : faire tourner le robot en scalping pendant 1-2h, vérifier que :
   - Les LONG sont bloqués quand `micro_trend < 0` (raison = `bearish_veto`)
   - Les SHORT reversal se déclenchent quand `micro_trend ≤ -2`
   - Les LONG passent quand `micro_trend ≥ 0`
2. **Audit runtime** : utiliser `GET /audit/enriched-export` pour vérifier la répartition des raisons de non-trade
3. **Calibration possible** : si le veto est trop restrictif (bloque trop de trades), on pourrait ajuster le seuil à `micro_trend < -1` au lieu de `< 0`

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
cd backend && python -m pytest tests/test_pivot_v200.py::TestDowntrendProtectionV2010 -v
```
