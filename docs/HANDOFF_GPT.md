# 🔄 HANDOFF GPT — Intervention v2.0.1

> **Date :** 10 avril 2026
> **Intervention :** Rendre le slot aggressive plus vivant sans le dénaturer

---

## Problème

Le slot aggressive ne tradait presque pas en runtime réel. Diagnostic runtime :
- Multi-slot actif ✅, slots `["scalping", "aggressive"]` ✅
- Score observé ≈ 24, action = "attendre", confidence = "low"
- **Pas un bug technique** — un problème de **calibrage / seuils**.

## Diagnostic

Le flux dans `_tick_single_slot()` :
1. `DecisionService.analyze(timeframe="4h")` avec `buy_threshold=None` (→ global 25)
2. Score ≈ 24 → `24 > 25` = False → action = `"attendre"`
3. Retour immédiat "hold" → `min_score=10` n'est **jamais atteint**

**Cause racine** : Le timeframe 4h est trop lent et le score ne traverse jamais le seuil global 25. Le `min_score=10` est un seuil mort car évalué APRÈS la décision du moteur.

## Correction appliquée

**Fichier :** `backend/app/services/trading_profile_service.py`
**Bloc :** `PROFILE_PRESETS["aggressive"]`

| Paramètre | Avant | Après | Justification |
|---|---|---|---|
| `analysis_timeframe` | `None` (= "4h") | `"1h"` | 4× plus de data fraîche, scores dynamiques |
| `buy_threshold` | `None` (= 25 global) | `20` | Score ~24 passe maintenant |
| `sell_threshold` | `None` (= 20 global) | `15` | Shorts accessibles plus tôt |

**Tous les autres paramètres sont INCHANGÉS** :
- TP 1.0%, SL 1.0%, durée max 48h, max_leverage 3.0
- Pas de trailing stop, pas de gate économique, pas de structural proofs
- min_score=10, cooldown 15min, max 15 trades/jour
- stale_exit 180min, market_quality 25, volume_ratio 0.5

## Ce qui n'a PAS été touché

- ❌ Scalping (aucun paramètre modifié)
- ❌ DecisionService (aucune modification du moteur)
- ❌ SignalService (aucune modification des scores)
- ❌ PaperTradingService._tick_single_slot (logique intacte)
- ❌ Frontend (aucune modification)
- ❌ Autres profils (conservative, balanced)

## Validations

- ✅ **1525 tests backend** passent (était 1512, +13 nouveaux)
- ✅ `tsc --noEmit` sans erreur (frontend clean)
- ✅ 13 tests spécifiques `TestAggressiveSlotCalibration` passent

## Documentation mise à jour

| Document | Changement |
|---|---|
| `docs/CURRENT_STATE.md` | Version 2.0.1, test count 1525, description v2.0.1, aggressive in "solide" |
| `CHANGELOG.md` | Nouvelle entrée [2.0.1] avec Changed, Added, Technical |
| `docs/HANDOFF_GPT.md` | Ce fichier (écrasé) |
| `docs/ROADMAP.md` | Pas de changement de phase nécessaire |
| `docs/requirements_traceability.md` | Pas de nouvelles exigences FR |

## Commit

**Message :** `feat(aggressive): timeframe 4h→1h + seuils buy/sell abaissés pour rendre le slot plus vivant`

## État actuel

| Élément | Valeur |
|---|---|
| Version | v2.0.1 |
| Tests | 1525 passing ✅ |
| tsc | clean ✅ |
| Prochaine action | Lancer un run runtime pour observer le slot aggressive en action |

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests backend
cd backend && python -m pytest tests/ -v

# Tests ciblés aggressive
cd backend && python -m pytest tests/test_paper_trading.py::TestAggressiveSlotCalibration -v

# TypeScript check
cd frontend && npx tsc --noEmit

# Mode headless (robot autonome)
curl -X POST http://localhost:8000/paper/autonomous/start -H "Content-Type: application/json" -d '{"interval_seconds": 10, "profile": "scalping"}'
```

## Protocole de validation runtime

1. Démarrer le backend + mode autonome headless
2. Observer les logs aggressive : `analysis_timeframe="1h"`, `buy_threshold=20`
3. Vérifier que le slot aggressive produit des actions `"acheter"` / `"vendre"` (pas seulement `"attendre"`)
4. Comparer : aggressive doit avoir ~3-8 trades/jour (vs 0-1 avant), avec des durées de 30min-4h (vs scalping 1-15min)
5. Vérifier que les TP/SL sont bien à ±1% (vs scalping ±0.2-0.8%)
6. Après 24h, exporter les trades et vérifier que le PnL net est positif
