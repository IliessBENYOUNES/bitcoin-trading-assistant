# 🔄 HANDOFF GPT — Dernière intervention

## Date : 13 avril 2026 — v2.0.26

---

## Problème

L'analyse de **92 trades** du run nocturne v2.0.25 révèle que les **shorts scalping** perdent de l'argent (47% WR, **-$8.93** net) quand le score technique est fortement bullish (+64/+65). Le tick_override ouvre des shorts quand la bougie 30s est rouge, mais le marché monte globalement → les shorts sont fermés 36-72s plus tard par "signal contraire" en perte.

## Diagnostic

- Sur 92 trades analysés, les shorts ont un WR de 47% et un PnL net de -$8.93
- Le score technique de +64/+65 indique un marché nettement bullish (≥4 indicateurs convergent)
- Le tick_override détecte une bougie rouge (micro-dip de 30s) et ouvre un short
- Mais le marché remonte car la tendance de fond est bullish → le score déclenche un "signal contraire" → fermeture en perte
- Les LONGs dans la même période sont rentables (bénéficient de la tendance)

## Cause racine

Le tick_override (v2.0.14) ne vérifie pas l'alignement entre la direction de la bougie 30s et la tendance macro (score technique). Il ouvre aveuglément dans la direction de la bougie, même si le marché va dans l'autre sens. Un short sur un micro-dip dans un marché bullish est structurellement perdant.

## Correction appliquée

### `backend/app/schemas/journal.py`
- Ajout du paramètre `trend_alignment_score_threshold` (Optional[float], default None)

### `backend/app/services/trading_profile_service.py`
- Profil scalping : `trend_alignment_score_threshold=50`

### `backend/app/services/paper_trading_service.py`
- Gate inséré entre le momentum stability check et le scalping reversal check
- Condition : `if tm_override_active and action == "vendre" and score > ta_threshold`
- Retourne `PaperTickResult(non_trade_reason="trend_alignment_blocked")`

### `backend/app/services/journal_service.py`
- 2 nouveaux labels : `trend_alignment_blocked`, `momentum_unstable`

## Ce qui n'a PAS été touché

- Aucun autre profil modifié (aggressive, balanced, conservative ont threshold=None)
- Les shorts mean_reversion ne sont PAS affectés (filtre vérifie `tm_override_active=True`)
- Les LONGs ne sont PAS affectés (filtre vérifie `action == "vendre"`)
- Aucun gate existant modifié (SAS, micro SL, economic gate, structural proofs)
- Aucun mécanisme de sortie modifié

## Validations

- ✅ **1804 tests** backend passent (0 échec)
- ✅ `tsc --noEmit` frontend sans erreur
- ✅ 8 nouveaux tests dédiés dans `TestTrendAlignmentFilter`
- ✅ Non-régression complète sur les 1796 tests existants

## Documentation mise à jour

| Document | Changements |
|----------|-------------|
| `docs/CURRENT_STATE.md` | Version 2.0.26, dernier commit, 1804 tests, feature v2.0.26 ajoutée |
| `CHANGELOG.md` | Nouvelle entrée [2.0.26] avec Added + Changed + Technical |
| `docs/HANDOFF_GPT.md` | Ce fichier (édité, pas recréé) |

## Commit

Message : `feat(scalping): trend alignment filter — bloque shorts override en marché bullish v2.0.26`

## État actuel

- **Version** : v2.0.26
- **Tests** : 1804 passed ✅
- **Impact estimé** : +$8.93 net sur 92 trades (élimination des shorts contre-tendance)
- **Le robot devrait** : ne plus ouvrir de shorts quand le score est > 50 (bullish), ne trade que les longs en marché haussier
- **Prochaine action recommandée** : Lancer un run de 12h et comparer : ratio long/short, PnL shorts, WR global

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v
```
