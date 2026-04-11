# HANDOFF GPT — 11 avril 2026

## Intervention : Audit runtime nocturne + Corrélation BTC + Learning enrichi

---

## Problème

Le run nocturne (57 trades fermés) a révélé un moteur qui survit (+4.06 USD) mais qui travaille beaucoup pour presque rien. Les sorties `closed_stale` dominent (91.2%), le trailing stop est le seul créateur de valeur, et le moteur ne sait pas corréler ses trades avec le mouvement réel du BTC.

---

## Diagnostic

### Données runtime extraites de PostgreSQL :
- **57 trades** : 21 gagnants / 36 perdants, WR=36.84%, PnL=+4.05 USD
- **Exit distribution** : closed_stale=52 (91.2%!), closed_trailing_stop=4 (100% WR, +22.84 USD), closed_sl=1 (-5.12 USD)
- **Slots** : scalping=54 (WR=37%, +14.31 USD), aggressive=3 (WR=33.3%, -10.25 USD)
- **Direction** : 100% long, 0 shorts
- **Scores** : 63-66 pour 55/57 trades (saturation totale)

### Verdicts :
1. **Le trailing stop est le SEUL créateur de valeur** : 4 trades, 100% WR, +22.84 USD
2. **Le stale exit est le problème #1** : 52/57 trades, 67% négatifs, contribution -336.5% du PnL total
3. **Le score ne discrimine pas** : 96% des trades dans une bande de 4 points (63-66)
4. **Le moteur ne capturait pas le contexte BTC** : aucune corrélation entre trades et mouvement réel du prix

---

## Cause racine

Le learning layer n'avait aucune information sur ce que faisait le BTC pendant et après chaque trade. Impossible de savoir si une sortie stale était prématurée ou justifiée. Impossible de mesurer l'efficacité de capture du mouvement BTC.

---

## Correction appliquée

### 1. RuntimeCorrelationService (NOUVEAU)
- **Fichier** : `backend/app/services/runtime_correlation_service.py`
- Corrèle chaque trade fermé avec les bougies BTC (1h, fallback 4h)
- Calcule : trend_at_entry, btc_move_during, btc_move_after_exit, missed_favorable_move, capture_efficiency
- Détecte les mouvements manqués entre trades (gaps sans position)

### 2. Learning enrichi (MODIFIÉ)
- **Fichier** : `backend/app/models/learning.py` — 5 nouvelles colonnes
- **Fichier** : `backend/app/services/learning_service.py` — méthode `_compute_btc_context()` ajoutée
- **Fichier** : `backend/app/schemas/learning.py` — 5 champs ajoutés à LearningSignalItem

### 3. Endpoint (MODIFIÉ)
- **Fichier** : `backend/app/api/routes/audit.py` — `GET /audit/runtime-correlation` ajouté

### 4. Migration
- **Fichier** : `backend/migrate_v202.py` — exécuté sur PostgreSQL prod

---

## Ce qui n'a PAS été touché

- ❌ Paramètres des profils scalping/aggressive (aucun changement de comportement)
- ❌ Logic de décision (seuils, scoring, règles)
- ❌ Logic de sortie (stale, trailing, momentum fade)
- ❌ Frontend (aucune modification)
- ❌ Scheduler / jobs

---

## Validations

- ✅ 17/17 tests `test_runtime_correlation.py` passent
- ✅ 1542/1542 tests totaux passent (0 régression)
- ✅ `tsc --noEmit` sans erreur
- ✅ Migration PostgreSQL exécutée

---

## Documentation mise à jour

| Document | Changements |
|----------|-------------|
| `docs/CURRENT_STATE.md` | Version v2.0.2, 1542 tests, features v2.0.2, nouveau fichier test |
| `CHANGELOG.md` | Nouvelle entrée [2.0.2] complète (Added, Technical) |
| `docs/ROADMAP.md` | v2.0.2 ajouté dans la timeline, état actuel mis à jour |
| `docs/requirements_traceability.md` | FR-COR-001/002/003 ajoutés, test count 1542 |

---

## Commit

```
feat(audit): runtime correlation BTC + learning enrichi contexte BTC (17 tests)
```

---

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.2 |
| Tests | 1542 passing |
| Frontend | tsc clean |
| Phase | Audit runtime + corrélation BTC livrés |

---

## Recommandation stratégique (basée sur les données runtime)

### Priorité #1 : Ajuster le stale exit (CRITIQUE)

**Le stale exit est le mode de sortie dans 91.2% des trades, et 67% sont négatifs.** C'est LE problème principal.

**Constat :**
- Le trailing stop (4 trades, 100% WR, +22.84 USD) crée TOUTE la valeur
- Le stale exit (52 trades) est la "poubelle" où finissent les trades qui n'atteignent ni TP ni SL ni trailing

**Actions recommandées (par priorité) :**

| # | Action | Impact attendu | Risque |
|---|--------|----------------|--------|
| **A** | **Réduire le stale exit time** de 15min à 8-10min pour positions à PnL < 0 | Réduit la durée d'exposition des perdants | Faible |
| **B** | **Augmenter la sélectivité d'entrée** (buy_threshold, min_score) | Moins de trades mais meilleure qualité | Modéré |
| **C** | **Élargir le trailing stop** (activation + trail) pour capturer plus de trades | Plus de closed_trailing_stop, moins de closed_stale | Faible |
| **D** | **Ajouter un filtre BTC trend** : ne pas entrer en scalping long si BTC micro-trend ≤ 0 | Filtre les entrées contre-tendance | Modéré |

---

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v

# TypeScript
cd frontend && npx tsc --noEmit

# Endpoint corrélation
curl http://localhost:8000/audit/runtime-correlation
```
