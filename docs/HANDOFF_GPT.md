# 📋 Handoff GPT — Fix Stale Exit vs Trailing Stop (10 avril 2026)

> Transfert de contexte pour GPT parallèle.

---

## 1. Titre et date

**Fix : Stale exit override le trailing stop sur les trades profitables**  
Date : 10 avril 2026

---

## 2. Problème

Le stale exit fermait des trades profitables (+0.46%) en les classant "stagnants" avant que le trailing stop puisse agir. Runtime : trade #364 fermé à +$11.39 en `closed_stale` après 15 min.

---

## 3. Diagnostic

Audit runtime de 603 ticks (~50 minutes) : 4 trades ouverts, 3 fermés `closed_stale`. Le trade #364 à +0.46% aurait dû être géré par le trailing stop (activation 0.20%), pas fermé comme stagnant.

---

## 4. Cause racine

Ligne 448 de `paper_trading_service.py` :
```python
stale_pnl_threshold = profile_params.profit_take_pct  # 0.8%
```

Pour les profils tight (scalping, loss_cut ≤ 0.5%), le seuil de stagnation était `profit_take_pct` = 0.8%.  
Un trade à +0.46% : `abs(0.46) < 0.8` → classé "stagnant" → fermé.  
Mais le trailing stop (activation 0.20%) était actif depuis longtemps (0.46 > 0.20) et n'a jamais pu agir.

---

## 5. Correction appliquée

**Fichier :** `backend/app/services/paper_trading_service.py`, bloc stale exit (~ligne 441-448)

**AVANT :**
```python
stale_pnl_threshold = 0.1
if profile_params and profile_params.loss_cut_pct <= 0.5:
    stale_pnl_threshold = profile_params.profit_take_pct
```

**APRÈS :**
```python
stale_pnl_threshold = 0.1
if profile_params and profile_params.loss_cut_pct <= 0.5:
    ts_act = getattr(profile_params, "trailing_stop_activation_pct", None)
    stale_pnl_threshold = ts_act if ts_act else profile_params.profit_take_pct
```

---

## 6. Ce qui n'a PAS été touché

- ✅ Profil **aggressive** : non impacté (loss_cut_pct > 0.5, branche tight jamais exécutée)
- ✅ Stale **négatif** : inchangé (positions en perte continuent à sortir normalement)
- ✅ Tous les autres gates (economic, structural, quality, volume, score) : inchangés
- ✅ Trailing stop logic : inchangé
- ✅ SL/TP logic : inchangé
- ✅ Frontend : aucun changement

---

## 7. Validations

| Check | Résultat |
|-------|----------|
| Tests ciblés (6 nouveaux) | ✅ 6/6 passed |
| Suite complète backend | ✅ **1507 passed** (was 1501) |
| `tsc --noEmit` frontend | ✅ 0 erreurs |

### Tests ajoutés (TestStaleVsTrailingThreshold)

1. `test_stale_threshold_uses_trailing_activation_for_tight_profiles` — scalping utilise ts_act
2. `test_profitable_position_above_trailing_activation_not_stale` — +0.46% n'est PAS stale
3. `test_flat_position_below_trailing_activation_is_stale` — +0.05% EST stale
4. `test_aggressive_not_affected_by_tight_logic` — aggressive garde seuil 0.1%
5. `test_stale_threshold_fallback_when_no_trailing` — fallback sur profit_take_pct
6. `test_stale_threshold_code_path_matches_service` — vérifie tous les profils

---

## 8. Documentation mise à jour

| Document | Changement |
|----------|------------|
| `docs/CURRENT_STATE.md` | Dernier commit, tests 1501→1507, ajout ligne v2.0.0-fix stale exit |
| `CHANGELOG.md` | Nouvelle entrée Fixed pour stale exit, tests 1460→1507 |
| `docs/ROADMAP.md` | Non modifié (pas de changement de phase) |
| `docs/requirements_traceability.md` | Non modifié (pas de nouvelles exigences, fix de bug) |
| `docs/HANDOFF_GPT.md` | Ce fichier |

---

## 9. Commit

**Message :** `fix(scalping): stale exit utilise trailing_stop_activation_pct au lieu de profit_take_pct`

---

## 10. État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.0 |
| Tests backend | 1507 passing |
| Frontend | tsc clean |
| Phase | v2.0.0 livré |

**Impact attendu sur les trades gagnants scalping :**

| Métrique | Avant | Après |
|----------|-------|-------|
| Seuil stale (scalping) | 0.80% (profit_take_pct) | 0.20% (trailing_stop_activation_pct) |
| Trade à +0.46% | ❌ fermé stale | ✅ trailing stop gère |
| Trade à +0.05% | ✅ fermé stale | ✅ fermé stale (inchangé) |
| Durée trades gagnants | ~15 min (coupés stale) | ~15-25 min (trailing gère) |
| PnL par gagnant | +$11 (0.46%) | +$12-20 (0.50-0.80% estimé) |
| Profil aggressive | Inchangé | Inchangé |

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
cd backend && python -m pytest tests/test_paper_trading.py::TestStaleVsTrailingThreshold -v
```
