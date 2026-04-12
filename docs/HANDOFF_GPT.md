# HANDOFF GPT — Déblocage scalping v2.0.6 + Timer position + Certification profil UI

**Date :** 12 avril 2026  
**Version :** v2.0.6  
**Commit :** (en cours)

---

## Problème

Le scalping était 100% bloqué — aucune position ne s'ouvrait sur le slot scalping. Le slot aggressive fonctionnait normalement. L'utilisateur a aussi demandé une confirmation visuelle du profil actif et un timer de position.

## Diagnostic — Audit runtime exhaustif

Requête SQL sur `tick_activity_log` — 135 ticks scalping analysés :

| Métrique | Valeur |
|----------|--------|
| Ticks scalping | 135 |
| `micro_trend_insufficient` | **135 (100%)** |
| `micro_trend_score` | **-2** (tous) |
| `decision_score` | **65** (seuil = 30) |
| `decision_action` | **acheter** (tous) |
| `market_quality_score` | **59** (seuil = 50) |
| Autres gates atteints | **0** |

**Verdict : le gate `micro_trend_insufficient` est le seul et unique coupable.** Il avait été assoupli de 2→1 en v2.0.4, mais le marché stagne à mt=-2 dans cette phase, rendant mt≥1 encore trop restrictif.

## Cause racine

Le gate micro-tendance dédié (`min_micro_trend_long=1`) bloque **séquentiellement** tous les ticks scalping avant qu'aucun autre gate ne soit atteint. Avec un micro_trend_score constant de -2 dans les phases latérales/baissières, le gate à mt≥1 est un verrou total.

## Corrections appliquées

### MISSION 2 — Déblocage scalping

**Fichier : `backend/app/services/trading_profile_service.py`**
- `min_micro_trend_long` : 1 → **0** (désactivé)
- Le code vérifie `if min_mt_long > 0` → avec 0, le gate est inactif
- La protection micro-trend reste via `structural_proofs` (mt≥3 = 1 preuve sur 4 requises, min_structural_proofs=2)

### MISSION 3 — Timer de position UI

**Fichier : `frontend/src/components/PaperTradingPanel.tsx`**
- Nouveau composant `PositionTimer` — chronomètre live basé sur `entry_ts`
- Format : `hh:mm:ss` ou `mm:ss` si < 1h
- Rafraîchi chaque seconde via `setInterval`
- Intégré dans les 2 zones de position (multi-slot et single-slot)

### Certification profil UI (livré dans l'intervention précédente, complété ici)

**Fichier : `backend/app/schemas/paper_trading.py`**
- `active_profile` ajouté à `PaperAccountResponse` → remonté dans chaque poll

**Fichier : `frontend/src/types/api.ts`**
- `active_profile` ajouté à `PaperAccountItem`

**Fichier : `frontend/src/components/PaperTradingPanel.tsx`**
- Bandeau `🔒 Profil certifié par le serveur` avec couleur du profil
- Sync automatique `activeProfile` via `status.account.active_profile` à chaque poll
- Alerte orange clignotante si désynchronisation détectée

## Ce qui n'a PAS été touché

- ❌ Aggressive (sanctuarisé)
- ❌ Scoring global
- ❌ Stale exit
- ❌ Trailing stop
- ❌ Economic gate (toujours actif)
- ❌ Structural proofs (toujours 2 requis)
- ❌ buy_threshold (reste à 30 — pas nécessaire, le score est 65)

## Validations

- ✅ **1598 tests** backend passent
- ✅ `tsc --noEmit` clean
- ✅ Audit runtime prouve que seul le micro_trend gate bloquait

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ Version 2.0.6, features, phase |
| `CHANGELOG.md` | ✅ Nouvelle entrée [2.0.6] |
| `docs/ROADMAP.md` | — (pas de changement de phase) |
| `docs/requirements_traceability.md` | — (pas de nouvelles exigences formelles) |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.6 |
| Tests backend | 1598 passing ✅ |
| TypeScript | tsc --noEmit clean ✅ |
| Gate micro-trend | DÉSACTIVÉ (0) |
| Certification profil | ✅ Bandeau UI |
| Timer position | ✅ Live hh:mm:ss |

## Protocole exact pour relancer un run propre

```bash
# 1. Full reset du compte
curl -X POST http://localhost:8000/paper/account/reset -H "Content-Type: application/json" -d "{\"initial_capital\": 10000}"

# 2. Poser le profil scalping
curl -X POST http://localhost:8000/paper/profile -H "Content-Type: application/json" -d "{\"profile\": \"scalping\"}"

# 3. Vérifier le profil
curl http://localhost:8000/paper/profile

# 4. Lancer le robot autonome en scalping
# (Via l'UI : sélectionner scalping → cliquer "Lancer le Robot")
# Ou headless :
curl -X POST http://localhost:8000/paper/autonomous/start -H "Content-Type: application/json" -d "{\"interval_seconds\": 5, \"profile\": \"scalping\"}"

# 5. Vérifier que le bandeau UI affiche "🔒 Profil certifié : ⚡ Scalping"
```

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests complets
cd backend && python -m pytest tests/ -v

# Tests pivot spécifiques
cd backend && python -m pytest tests/test_pivot_v200.py::TestScalpingV206MicroTrendDisable -v
```
