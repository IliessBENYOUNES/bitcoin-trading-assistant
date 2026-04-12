# HANDOFF GPT — Candle Direction Learning Patterns v2.0.17

**Date :** 12 avril 2026  
**Version :** v2.0.17 (feature)  

---

## Problème

Le modèle d'apprentissage ne prenait pas en compte la **cohérence de couleur de bougie** entre l'entrée et la sortie d'un trade. L'utilisateur observait que les trades gagnants étaient ceux où la pastille restait de la même couleur (momentum conservé), tandis que les perdants avaient un changement de couleur (momentum retourné). Ce pattern n'était pas exploité par le learning.

De plus, dans le journal UI, la pastille de sortie n'apparaissait pas pour les anciens trades (champ null), et les deux pastilles étaient visuellement indistinguables.

## Diagnostic

1. `analyze_patterns()` analysait par exit_type, score, direction, durée, utilité économique — mais **pas par cohérence candle direction**
2. `suggest_adjustments()` ne générait aucune suggestion basée sur les patterns entrée/sortie de bougie
3. L'UI n'avait pas de fallback pour les anciens trades sans `exit_candle_direction`
4. Les pastilles E et S étaient identiques visuellement (même taille, pas de label)

## Cause racine

Feature manquante — le v2.0.16 avait posé les données (entry/exit candle dans LearningSignal) mais le moteur d'apprentissage ne les exploitait pas encore.

## Correction appliquée

### Backend — Learning Service

| Ajout | Détail |
|-------|--------|
| Pattern 7 : Candle consistency | 4 catégories : `same_aligned`, `same_counter`, `reversed_favor`, `reversed_against` |
| Méta-pattern | Comparaison globale "même couleur" vs "changement" avec delta WR/PnL |
| Pattern 8 : Durée × candle | Croisement scalps rapides (<2min) × cohérence couleur |
| Suggestion 15 | Si reversed_against WR < 35% → réduire `stale_negative_exit_minutes` |
| Suggestion 16 | Si entrée contre-tendance nettement pire → relever `min_micro_trend_long` |

### Frontend — Pastilles enrichies

| Changement | Détail |
|-----------|--------|
| Fallback sortie | Pastille S calculée client-side via `exit_price vs entry_price` si champ null |
| Mini-labels | "E" / "S" en blanc dans chaque pastille (20px) |
| Séparateur | `→` entre les deux pastilles |
| Tooltip enrichi | Type de sortie (✅ TP, ❌ SL, ⚠️ Signal...) + PnL sur la pastille S |

## Ce qui n'a PAS été touché

- Logique d'ouverture/fermeture de position inchangée
- `record_sample()` inchangé (v2.0.16 le faisait déjà)
- Aucun changement de modèle DB (pas de migration)
- Aucun changement d'endpoint API

## Validations

- ✅ **1718 tests** backend passent (0 régression, +9 nouveaux)
- ✅ `tsc --noEmit` sans erreur frontend
- ✅ Import `LearningService` OK

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ Version 2.0.17, tests 1718, dernier commit |
| `CHANGELOG.md` | ✅ Nouvelle section v2.0.17 complète |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.17 |
| Tests | 1718 passing |
| Frontend | tsc clean |

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
```
