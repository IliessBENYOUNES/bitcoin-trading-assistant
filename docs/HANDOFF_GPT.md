# HANDOFF GPT — Incident grave : bascule silencieuse du profil actif v2.0.5

**Date :** 12 avril 2026  
**Version :** v2.0.5  
**Commit :** `(pending)` — fix(profile): préservation du profil actif lors du reset — anti-bascule conservative

---

## Problème

Le profil actif du paper trading basculait silencieusement de "scalping" vers "conservative" sans aucune action explicite de l'utilisateur. L'export runtime montrait `active_profile = "conservative"` avec un slot conservative ouvert, alors que l'utilisateur avait lancé le run en mode scalping.

## Diagnostic

Audit exhaustif de **tous les chemins** qui lisent ou écrivent `active_profile` dans le code. 5 chemins identifiés comme responsables :

| # | Chemin | Fichier | Gravité |
|---|--------|---------|---------|
| 1 | `reset_account()` crée PaperAccount sans active_profile | `paper_trading_service.py:150` | 🔴 CRITIQUE |
| 2 | `get_or_create_account()` crée PaperAccount sans active_profile | `paper_trading_service.py:80` | 🔴 CRITIQUE |
| 3 | Fallback `or "conservative"` masque le None | `paper_trading_service.py:199, :1832` | 🟡 MASQUE |
| 4 | Default SQLAlchemy `default="conservative"` | `paper_account.py:43` | 🟠 RACINE |
| 5 | Frontend self-healing appelle `createPaperAccount` sans profil | `usePaperTrading.ts:178` | 🟡 INDIRECT |

## Cause racine

**Catégorie : C — Valeur par défaut destructrice + D — Reset qui écrase le profil.**

Le modèle SQLAlchemy `PaperAccount` a `active_profile` avec `default="conservative"` (ligne 43 de `paper_account.py`). C'est le comportement attendu pour une création initiale, mais c'est destructeur quand le compte est recréé par un `reset_account()` : l'ancien profil est détruit avec le compte, et le nouveau est créé avec le default "conservative" — le profil demandé par l'utilisateur est perdu.

**Scénario reproduit :**
1. L'utilisateur sélectionne "scalping" et lance le robot
2. `setPaperProfile("scalping")` → `active_profile="scalping"` ✅
3. Un full reset est déclenché (bouton frontend ou via processus)
4. `reset_account()` → DELETE old PaperAccount → INSERT new PaperAccount(active_profile="conservative") ❌
5. Aucun code ne restaure le profil après → le robot tourne en conservative

## Correction appliquée

### Backend

**Fichier 1 : `backend/app/services/paper_trading_service.py`**
- `reset_account()` : Ajout du paramètre `preserve_profile`. Le profil de l'ancien compte est capturé AVANT la purge et restauré dans le nouveau compte.
- `get_or_create_account()` : Ajout du paramètre `active_profile`. Si le compte est créé pour la première fois, le profil demandé est utilisé au lieu du default. Si le compte existe déjà, le profil n'est PAS écrasé.

**Fichier 2 : `backend/app/api/routes/paper_trading.py`**
- `start_autonomous()` : Ajout de `account.active_profile = request.profile` — force le profil demandé dans TOUS les cas (compte existant ou nouveau).

**Fichier 3 : `backend/app/services/autonomous_manager.py`**
- `_set_profile()` : Passe le profil à `get_or_create_account(active_profile=profile)`.

### Frontend

**Fichier 4 : `frontend/src/components/PaperTradingPanel.tsx`**
- `handleFullReset()` : Après le reset, appel explicite `setPaperProfile(selectedProfile)` pour restaurer le profil.
- `handleStartAuto()` : Appel `setPaperProfile(selectedProfile)` avant de démarrer l'auto-tick.

## Ce qui n'a PAS été touché

- ❌ Aggressive (sanctuarisé)
- ❌ Logique de trading / tick / SL/TP
- ❌ Gate économique, structural proofs
- ❌ Decision engine, scoring
- ❌ Default SQLAlchemy dans le modèle (gardé pour la rétrocompatibilité, le fix est au niveau service)
- ❌ Schema PaperAccountCreate (pas de champ active_profile ajouté — le profil se gère via `POST /paper/profile`)

## Validations

- ✅ **1598 tests** backend passent (1587 + 11 nouveaux)
- ✅ `tsc --noEmit` clean
- ✅ 11 tests de non-régression spécifiques à l'incident

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ Version 2.0.5, tests 1598, feature fix |
| `CHANGELOG.md` | ✅ Nouvelle entrée [2.0.5] avec Fixed + Added + Technical |
| `docs/ROADMAP.md` | — (pas de changement de phase) |
| `docs/requirements_traceability.md` | — (pas de nouvelles exigences formelles) |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.5 |
| Tests backend | 1598 passing ✅ |
| TypeScript | tsc --noEmit clean ✅ |
| Profil préservé lors du reset | ✅ Prouvé par 11 tests |
| Chemins corrigés | 5/5 |

## Prochaine action recommandée

1. **Commit + push** le fix
2. **Relancer un run scalping** propre
3. **Vérifier** via `GET /paper/profile` que le profil reste "scalping" après chaque action
4. **Si le profil bascule encore** : utiliser les tests de diagnostic

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests complets
cd backend && python -m pytest tests/ -v

# Tests spécifiques anti-bascule
cd backend && python -m pytest tests/test_paper_trading.py::TestProfilePreservation -v

# Vérifier le profil actif
curl http://localhost:8000/paper/profile

# Lancer un run scalping autonome
curl -X POST http://localhost:8000/paper/autonomous/start -H "Content-Type: application/json" -d '{"interval_seconds": 10, "profile": "scalping"}'
```
