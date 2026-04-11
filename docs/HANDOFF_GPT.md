# HANDOFF GPT — Fix auto-activation paper trading v2.0.3

**Date :** 11 avril 2026  
**Version :** v2.0.3

---

## Problème

Après un full reset ou au premier lancement, le paper trading reste "INACTIF" même quand le robot est lancé. Le message "Paper trading désactivé. Activez-le via POST /paper/account." s'affiche en boucle dans les auto-ticks. L'utilisateur final ne peut pas trader sans faire une requête POST manuelle via Postman.

## Diagnostic

Le bouton "Lancer le Robot" appelle bien `createPaperAccount()` pour activer le compte, puis `startAuto()` pour démarrer les ticks automatiques. Mais si l'activation échoue silencieusement (erreur réseau, timing, etc.) ou si le bouton "Auto custom" est utilisé (qui ne fait AUCUNE activation), le robot tourne en boucle sur un compte inactif.

## Cause racine

1. **`POST /paper/tick` ne fait pas d'auto-activation** : si le compte est inactif, le tick retourne juste "inactive" sans rien faire
2. **`handleStartAuto` (bouton "Auto custom") ne fait aucune activation** : il appelle `startAuto()` directement sans vérifier/activer le compte
3. **Pas de self-healing frontend** : si un tick retourne "inactive", le frontend affiche le message sans tenter de corriger
4. **Message technique inadapté** : "Activez-le via POST /paper/account." est un message développeur, pas un message utilisateur final

## Correction appliquée

### 4 changements (backend + frontend) :

| Fichier | Changement |
|---------|-----------|
| `backend/app/api/routes/paper_trading.py` | `POST /paper/tick` auto-active le compte si inactif + configure multi-slot ≥3 |
| `backend/app/services/paper_trading_service.py` | Message UX : "Cliquez sur Lancer le Robot" au lieu de "POST /paper/account" |
| `frontend/src/hooks/usePaperTrading.ts` | `doAutoTick` + `manualTick` : si "inactive" → `createPaperAccount()` + retry |
| `frontend/src/components/PaperTradingPanel.tsx` | `handleStartAuto` active le compte avant de démarrer l'auto-tick |
| `backend/tests/test_paper_trading.py` | 1 test endpoint mis à jour (inactive → no_price après auto-activation) |

## Ce qui n'a PAS été touché

- ❌ Slot aggressive (sanctuarisé)
- ❌ Scoring global / DecisionService
- ❌ Stale exit logic
- ❌ Momentum fade
- ❌ Economic viability gate
- ❌ Scheduler paper_trading_job (garde le check is_active — le scheduler ne doit PAS auto-activer)
- ❌ Service tick() (le check is_active reste dans le service, l'auto-activation est dans la route HTTP)
- ❌ Full Reset (crée toujours le compte avec is_active=False — c'est correct)

## Validations

- ✅ 1554 tests backend passent (0 ajouté, 0 supprimé, 1 mis à jour)
- ✅ Aucune régression
- ✅ `tsc --noEmit` sans erreur
- ✅ L'auto-activation est triple-couche : backend endpoint + frontend doAutoTick + frontend handleStartAuto

## Documentation mise à jour

| Document | Changement |
|----------|-----------|
| `docs/CURRENT_STATE.md` | Version v2.0.3, tests 1554, auto-activation documentée |
| `CHANGELOG.md` | Section Fixed ajoutée dans v2.0.3 + Technical mis à jour |
| `docs/HANDOFF_GPT.md` | Ce fichier |

## État actuel

- **Version :** v2.0.3
- **Tests :** 1554 passing
- **Prochaine action :** Lancer le robot depuis le frontend, vérifier que le paper trading s'active automatiquement et que les ticks fonctionnent

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Tests
cd backend && python -m pytest tests/ -v

# Frontend
cd frontend && npm run dev
```
