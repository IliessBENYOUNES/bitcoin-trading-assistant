# HANDOFF GPT — Audit scalping + Export enrichi + Learning runtime v2.0.4

**Date :** 11 avril 2026  
**Version :** v2.0.4  
**Commit :** `feat(scalping+learning): assouplissement micro-trend 2→1, export enrichi, learning runtime`

---

## Problème

Le scalping était complètement bloqué depuis le déploiement v2.0.3. Aucun trade scalping n'a été ouvert. Seul le slot aggressive produisait des trades. L'utilisateur demandait un audit chirurgical avec chiffres exacts.

## Diagnostic

Audit des 966 ticks scalping en base (TickActivityLog) :

| Métrique | Valeur |
|----------|--------|
| Total ticks scalping | **966** |
| Bloqués par `micro_trend_insufficient` | **966 (100%)** |
| `micro_trend_score` dominant | **-2** (100% des ticks) |
| `decision_action` | **acheter** (100% — le moteur VEUT acheter) |
| `decision_score` | **65** (100% — bien au-dessus du seuil 30) |

## Cause racine

Le gate `min_micro_trend_long=2` (ajouté en v2.0.3) exige un `micro_trend_score ≥ 2` pour ouvrir un long scalping. Or le BTC était en micro-tendance baissière persistante (mt_score=-2). Ce gate VETO bloquait 100% des ticks scalping. Aucun autre gate (buy_threshold, economic, structural) n'était même atteint.

## Correction appliquée

### BLOC A — Assouplissement scalping

**Fichier :** `backend/app/services/trading_profile_service.py`  
**Avant :** `min_micro_trend_long=2`  
**Après :** `min_micro_trend_long=1`

Justification :
- mt≥1 = début de reprise → suffisant pour tenter un long
- mt≤0 = flat ou baissier → toujours bloqué
- Le buy_threshold (30) n'est PAS responsable (score=65)
- Impact attendu : le scalping se déverrouille dès que BTC passe en début de reprise (mt=1), sans accepter le bruit directionnel (mt≤0)

### BLOC B — Export enrichi + Learning runtime

1. **EnrichedExportService** — Export tick-par-tick avec contexte complet :
   - Prix BTC + variation inter-tick
   - Décision moteur + raison de non-trade
   - Ventilation des refus par gate (GateBlockDistribution)
   - Détection des tendances BTC ratées (MissedTrendAnalysis)
   - Endpoint `GET /audit/enriched-export`

2. **LearningService.learn_from_runtime()** — Apprentissage basé sur les refus :
   - Analyse les TickActivityLog (pas les trades fermés)
   - Suggestion 15 : gate micro-trend sur-bloquant (>50% des refus)
   - Suggestion 16 : gate unique dominant (>70% des refus)
   - Endpoint `POST /learning/learn-runtime`

## Ce qui n'a PAS été touché

- ❌ Aggressive (sanctuarisé)
- ❌ buy_threshold (pas le problème, score=65 >> 30)
- ❌ min_score (pas le problème)
- ❌ Trailing stop, stale exit, momentum fade
- ❌ Economic gate, structural proofs
- ❌ Frontend (aucun changement)

## Validations

- ✅ **1587 tests** backend passent (1554 + 33 nouveaux)
- ✅ `tsc --noEmit` clean
- ✅ Endpoints testés et accessibles

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ Version, tests, features v2.0.4 |
| `CHANGELOG.md` | ✅ Nouvelle entrée [2.0.4] |
| `docs/ROADMAP.md` | — (pas de changement de phase) |
| `docs/requirements_traceability.md` | — (pas de nouvelles exigences formelles) |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.4 |
| Tests backend | 1587 passing ✅ |
| TypeScript | tsc --noEmit clean ✅ |
| Scalping gate micro-trend | mt≥1 (était mt≥2) |
| Export enrichi | GET /audit/enriched-export |
| Learning runtime | POST /learning/learn-runtime |

## Prochaine action recommandée

1. **Laisser tourner** le robot — quand BTC passera en micro-tendance ≥1, le scalping se déverrouillera
2. **Vérifier** via `GET /audit/enriched-export?profile_type=scalping` que les gates suivants fonctionnent correctement une fois micro-trend dépassé
3. **Si aucun trade après plusieurs heures avec mt≥1** : utiliser `POST /learning/learn-runtime` pour identifier le gate suivant

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v

# Export enrichi scalping
curl http://localhost:8000/audit/enriched-export?profile_type=scalping

# Learning runtime
curl -X POST http://localhost:8000/learning/learn-runtime?profile_type=scalping
```
