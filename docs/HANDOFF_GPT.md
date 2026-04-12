# HANDOFF GPT — Shorts bidirectionnels v2.0.8

**Date :** 12 avril 2026  
**Version :** v2.0.8  
**Commit :** (pending)

---

## Problème

Le robot n'ouvrait **AUCUN short** en 24h. Même en marché range (BTC oscillant), seuls des longs étaient ouverts. L'utilisateur voulait voir des shorts alterner avec des longs pour capter les micro-mouvements dans les deux sens.

## Diagnostic — Double blocage

Deux mécanismes empêchaient les shorts :

### Blocage 1 : Reversal check trop restrictif (seuil = 2)
Le `_scalping_reversal_check()` exigeait **2 signaux overbought convergents** :
- RSI overbought (RSI ≥ 70, strength ≥ 0.7)
- StochRSI overbought (K ≥ 80, D ≥ 75, strength ≥ 0.6)

En marché range avec RSI à 55 et StochRSI à 60, **aucun** de ces signaux ne se déclenchait jamais.

### Blocage 2 : short_min_score illogique pour reversals
Le filtre `short_min_score` (= 30) exigeait `abs(score) ≥ 30` pour ouvrir un short. Mais le reversal est **contrarian** : quand le score est +25 (bullish), le reversal dit "trop bullish = surachat = short". Le filtre bloquait car abs(25) = 25 < 30.

C'est fondamentalement illogique : un score **positif** n'est pas une faiblesse pour un short contrarian, c'est une **confirmation** du surachat.

## Cause racine

1. Le seuil de 2 signaux (v1.9.4) avait été mis pour éviter "trop de shorts en bull run". Mais les sorties étaient mauvaises à l'époque. Maintenant avec trailing stop, breakeven stop, et stale 2 min, un mauvais short sort en 30sec-2min avec ~$0-1 de perte max.

2. Le `short_min_score` avait été conçu pour des shorts **directionnels** (où un score bearish confirme la direction). Pour un trade contrarian, le filtre est contre-productif.

## Corrections appliquées

**Fichier : `backend/app/services/paper_trading_service.py`**

### 1. Refonte `_scalping_reversal_check()` (L1524-1609)
- **Seuil abaissé de 2 à 1** signal
- **Nouveau signal "majorité bearish"** : si ≥2 règles bearish satisfaites ET bearish > bullish → +1 overbought
- Symétrique : majorité bullish → +1 oversold (pour les reversals long)
- Tech score extrême ≥ 95 conservé comme signal additionnel

### 2. Suppression `short_min_score` pour reversals (L820-838)
- **Avant** : le code vérifiait `abs(score) < short_min_score` et bloquait le reversal
- **Après** : le reversal est appliqué directement, sans vérification de score
- `short_min_score` reste actif pour les shorts NON-reversal

## Ce qui n'a PAS été touché

- ❌ Trailing stop / breakeven stop (inchangés)
- ❌ Profil aggressive (sanctuarisé)
- ❌ SL/TP, gates économiques, market quality
- ❌ Frontend

## Validations

- ✅ **1617 tests** backend passent (9 ajoutés net)
- ✅ `tsc --noEmit` clean

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ 1617 tests, feature shorts bidirectionnels |
| `CHANGELOG.md` | ✅ Section Fixed + Added + Technical enrichie |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.8 |
| Tests backend | 1617 passing ✅ |
| TypeScript | tsc --noEmit clean ✅ |

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
cd backend && python -m pytest tests/test_pivot_v200.py::TestShortBidirectionalV208 -v
```
