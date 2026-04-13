# 🔄 HANDOFF GPT — Dernière intervention

## Date : 13 avril 2026 — v2.0.27

---

## Problème

Le filtre trend alignment v2.0.26 ne bloquait que les **SHORTs** en marché bullish (score > +50), mais **ne bloquait pas les LONGs** en marché bearish (score < -50). Asymétrie : une bougie verte 30s en tendance baissière est tout autant un faux signal qu'une bougie rouge en tendance haussière. Les longs contre-tendance perdent de la même manière.

## Diagnostic

- Le filtre v2.0.26 vérifie `action == "vendre" and score > ta_threshold` — unilatéral
- Aucune condition symétrique pour `action == "acheter" and score < -ta_threshold`
- En marché bearish, le tick_override détecte une bougie verte (micro-rebond 30s) et ouvre un LONG
- Mais la tendance de fond est baissière → le prix redescend → fermeture en perte

## Cause racine

Le filtre trend alignment v2.0.26 a été conçu uniquement pour le cas observé dans les données (shorts perdants en marché bullish) sans considérer le cas symétrique (longs perdants en marché bearish). C'est un problème de conception unilatérale.

## Correction appliquée

### `backend/app/services/paper_trading_service.py`
- Restructuration du bloc trend alignment : le `if` externe vérifie maintenant `tm_override_active and profile_params` (sans direction)
- Deux branches internes indépendantes :
  - `action == "vendre" and score > ta_threshold` → bloque SHORT (existant)
  - `action == "acheter" and score < -ta_threshold` → bloque LONG (**nouveau**)
- Même seuil `trend_alignment_score_threshold=50` utilisé en valeur absolue

### `backend/tests/test_pivot_v200.py`
- Test `test_long_not_affected_by_filter` renommé en `test_long_not_blocked_when_score_bullish`
- 5 nouveaux tests ajoutés :
  - `test_long_blocked_when_score_strongly_bearish` (score=-65 → bloqué)
  - `test_long_allowed_when_score_mildly_bearish` (score=-30 → autorisé)
  - `test_long_boundary_exact_negative_threshold` (score=-50 → autorisé, strict <)
  - `test_long_just_below_negative_threshold_blocks` (score=-51 → bloqué)
  - `test_long_not_blocked_when_score_bullish` (score=+65 → autorisé, aligné)

## Ce qui n'a PAS été touché

- Aucun autre profil modifié (threshold=None pour conservative, balanced, aggressive)
- Les shorts mean_reversion et longs mean_reversion ne sont PAS affectés
- Le schéma `trend_alignment_score_threshold` est réutilisé (pas de nouveau paramètre)
- Aucun mécanisme de sortie modifié
- Aucun gate existant modifié

## Validations

- ✅ **1808 tests** backend passent (0 échec)
- ✅ `tsc --noEmit` frontend sans erreur
- ✅ 12 tests trend alignment total (7 existants + 5 nouveaux)
- ✅ Non-régression complète

## Documentation mise à jour

| Document | Changements |
|----------|-------------|
| `docs/CURRENT_STATE.md` | Version 2.0.27, dernier commit, 1808 tests, feature v2.0.27 ajoutée |
| `CHANGELOG.md` | Nouvelle entrée [2.0.27] avec Fixed + Changed + Technical |
| `docs/HANDOFF_GPT.md` | Ce fichier (édité, pas recréé) |

## Commit

Message : `fix(scalping): trend alignment symétrique — bloque aussi les longs override en marché bearish v2.0.27`

## État actuel

- **Version** : v2.0.27
- **Tests** : 1808 passed ✅
- **Le filtre est maintenant bidirectionnel** : SHORT bloqué quand score > +50, LONG bloqué quand score < -50
- **Prochaine action recommandée** : Lancer un nouveau run et vérifier que les trades contre-tendance (shorts en bullish ET longs en bearish) sont bien bloqués

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v
```
