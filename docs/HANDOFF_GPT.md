# 📋 Handoff GPT — Fix Multi-Slot Perdu Après Full Reset (10 avril 2026)

> Transfert de contexte pour GPT parallèle.

---

## 1. Titre et date

**Fix : Multi-slot perdu après full reset — le slot aggressive ne se relance pas**  
Date : 10 avril 2026

---

## 2. Problème

Après un full reset + relance du run, un seul trade scalping s'ouvre. Le slot aggressive, qui auparavant tournait en parallèle et portait de gros gains, ne se relance plus.

---

## 3. Diagnostic

Trace du flux complet :
1. Frontend appelle `resetPaperAccount({ initial_capital: capital })` — **sans `max_open_positions`**
2. `FullResetRequest.max_open_positions` avait un default de **1** (schema Pydantic)
3. L'endpoint `POST /paper/account/reset` fait `account.max_open_positions = config.max_open_positions` = **1**
4. `get_enabled_slots(account)` avec `max_open_positions=1` retourne `[active_profile]` (mono-slot)
5. Pour `active_profile="scalping"`, retourne `["scalping"]` au lieu de `["scalping", "aggressive"]`

---

## 4. Cause racine

Deux champs schema avec default=1 :
- `FullResetRequest.max_open_positions` (ligne 42 de `schemas/paper_trading.py`)
- `PaperAccountCreate.max_open_positions` (ligne 29 de `schemas/paper_trading.py`)

Le frontend ne passe jamais `max_open_positions` lors du reset ou de l'activation. Le default 1 était appliqué systématiquement.

Problème secondaire : `autonomous/start` ne configurait `max_open_positions=3` que si `is_active=False`. Si le compte était déjà activé manuellement, le multi-slot n'était pas restauré.

---

## 5. Correction appliquée

### Fichier 1 : `backend/app/schemas/paper_trading.py`

**AVANT :**
```python
# PaperAccountCreate
max_open_positions: int = Field(default=1, ge=1, le=10, ...)
# FullResetRequest
max_open_positions: int = Field(default=1, ge=1, le=10)
```

**APRÈS :**
```python
# PaperAccountCreate
max_open_positions: int = Field(default=3, ge=1, le=10, ...)
# FullResetRequest
max_open_positions: int = Field(default=3, ge=1, le=10)
```

### Fichier 2 : `backend/app/api/routes/paper_trading.py` (autonomous/start)

**AVANT :**
```python
if not account.is_active:
    account.is_active = True
    account.max_open_positions = 3
    db.commit()
```

**APRÈS :**
```python
account.is_active = True
account.max_open_positions = max(account.max_open_positions or 1, 3)
db.commit()
```

---

## 6. Ce qui n'a PAS été touché

- ✅ `get_enabled_slots()` : logique inchangée, fonctionnait correctement avec `max_open_positions>1`
- ✅ `reset_account()` service : inchangé
- ✅ `PaperAccount` model : default DB reste 1 (endpoint override)
- ✅ Frontend : aucun changement (defaults backend suffisent)
- ✅ Profils (trading_profile_service) : inchangés
- ✅ `_tick_single_slot()` : inchangé

---

## 7. Validations

| Check | Résultat |
|-------|----------|
| Tests ciblés (5 nouveaux) | ✅ 5/5 passed |
| Suite complète backend | ✅ **1512 passed** (was 1507) |
| `tsc --noEmit` frontend | ✅ 0 erreurs |

### Tests ajoutés (TestMultiSlotAfterReset)

1. `test_reset_endpoint_default_max_open_positions_is_3` — reset crée compte avec max_open_positions=3
2. `test_create_account_default_max_open_positions_is_3` — activate crée avec max_open_positions=3
3. `test_get_enabled_slots_scalping_multi` — scalping+3 → ["scalping", "aggressive"]
4. `test_get_enabled_slots_scalping_mono` — scalping+1 → ["scalping"] (mono-slot explicite)
5. `test_full_reset_then_scalping_gets_multi_slot` — scénario complet reset→scalping→multi-slot

---

## 8. Documentation mise à jour

| Document | Changement |
|----------|------------|
| `docs/CURRENT_STATE.md` | Dernier commit, tests 1507→1512, nouveau fix, problème #14 résolu |
| `CHANGELOG.md` | Nouvelle entrée Fixed pour multi-slot, tests 1460→1512 |
| `docs/ROADMAP.md` | Non modifié (pas de changement de phase) |
| `docs/requirements_traceability.md` | Non modifié (fix de bug) |
| `docs/HANDOFF_GPT.md` | Ce fichier |

---

## 9. Commit

**Message :** `fix(multi-slot): max_open_positions default 1→3 pour que le slot aggressive survive au full reset`

---

## 10. État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.0 |
| Tests backend | 1512 passing |
| Frontend | tsc clean |
| Phase | v2.0.0 livré |

**Impact attendu :**

| Métrique | Avant | Après |
|----------|-------|-------|
| max_open_positions après reset | 1 (mono-slot) | 3 (multi-slot) |
| Slots avec profil scalping | `["scalping"]` | `["scalping", "aggressive"]` |
| Slot aggressive après reset | ❌ Ne tourne pas | ✅ Tourne en parallèle |
| autonomous/start déjà running | Pas de reconfiguration | ✅ Reconfigure toujours |

---

## 11. Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v

# Tests ciblés
cd backend && python -m pytest tests/test_paper_trading.py::TestMultiSlotAfterReset -v
```
