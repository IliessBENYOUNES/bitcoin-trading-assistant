# 🔄 HANDOFF GPT — Dernière intervention

## Date : 13 avril 2026 — v2.0.28

---

## Problème

L'analyse du run v2.0.27 (58 trades, -$20.41, profit factor 0.64) révèle 3 problèmes structurels :

1. **Slot aggressive sans protections** : pas de SAS, pas de micro SL, pas de smart cooldown. Le trade #1108 a perdu 100% d'un pic de 0.705% ($0 PnL au lieu de +$17), le trade #1102 a perdu -$6.60.
2. **Cooldown scalping trop long** : le cooldown de 1 min (v2.0.25 anti-churn) est disproportionné maintenant que le micro SL est à 0.05% — les boucles churn sont cassées, le cooldown bloque inutilement.
3. **Gain erosion trop sensible** : se déclenche sur des peaks < $0.50 (bruit de tick), avec des sorties à +$0.12-$0.18 qui ne couvrent pas les frais.

## Diagnostic

- **58 trades analysés** dont ~50 scalping et ~8 aggressive
- Aggressive : gain erosion ferme sur des peaks de 0.02-0.08% → PnL de $0 à $0.40 (poussière)
- Aggressive : trailing activé trop tôt (0.15%) ou laissé filer (drop ratio 30% → perte de 100% du pic)
- Scalping : gain erosion sort sur des peaks de 0.01% ($0.25) — du bruit
- Scalping : cooldown de 1 min empêche de profiter d'opportunités rapides

## Cause racine

Le profil aggressive manquait de toutes les protections développées pour le scalping (SAS v2.0.22, micro SL v2.0.23, smart cooldown v2.0.24). Le profil scalping avait un cooldown calibré pour un micro SL de 0.01%, devenu obsolète avec le recalibrage à 0.05%.

## Corrections appliquées

### Fichiers modifiés

| Fichier | Changement |
|---------|------------|
| `backend/app/services/trading_profile_service.py` | Profil aggressive : +SAS, +micro SL 0.15%, +smart cooldown, trailing 0.25%/20%, gain erosion 0.70, cooldown 5 min. Profil scalping : cooldown 0.5 min, min 0.25, max 2.0, gain erosion 0.40 |
| `backend/app/services/paper_trading_service.py` | Gain erosion min peak 0.01%→0.02% |
| `backend/tests/test_smart_cooldown.py` | 4 assertions mises à jour |
| `backend/tests/test_pivot_v200.py` | 7 assertions mises à jour |
| `backend/tests/test_scalping_audit.py` | 1 assertion mise à jour |
| `backend/tests/test_diagnostic.py` | 1 assertion mise à jour |
| `backend/tests/test_runtime_truth.py` | 1 assertion mise à jour |
| `backend/tests/test_entry_sas.py` | 1 test renommé/corrigé (aggressive SAS activé) |
| `backend/tests/test_micro_stop_loss.py` | 1 test renommé/corrigé (aggressive micro SL activé) |

### Paramètres modifiés — Scalping

| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| `cooldown_minutes` | 1.0 | **0.5** | micro SL 0.05% casse les boucles churn |
| `min_cooldown_minutes` | 0.5 | **0.25** | SAS protège en amont |
| `max_cooldown_minutes` | 3.0 | **2.0** | micro SL + SAS suffisent |
| `gain_erosion_ratio` | 0.30 | **0.40** | plus de marge pour développer les gains |

### Paramètres modifiés — Aggressive

| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| `cooldown_minutes` | 15 | **5** | 3× plus d'opportunités intraday |
| `trailing_stop_activation_pct` | 0.15 | **0.25** | laisse les swings se développer |
| `trailing_stop_drop_ratio` | 0.30 | **0.20** | protège 80% au lieu de 70% |
| `gain_erosion_ratio` | 0.50 | **0.70** | les swings oscillent, besoin de respiration |
| `entry_sas_enabled` | ❌ | **✅** | filtre mauvaises entrées (10s/5s) |
| `micro_stop_loss_pct` | None | **0.15** | coupe à -$3.75 au lieu de -$25 |
| `smart_cooldown_enabled` | ❌ | **✅** | cooldown adaptatif (1-5 min) |

### Paramètre global modifié

| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| Gain erosion min peak | 0.01% | **0.02%** | peaks < $0.50 = bruit |

## Ce qui n'a PAS été touché

- Le frontend (aucun changement)
- Les profils conservative et balanced
- Les mécanismes de sortie existants (trailing, breakeven, stale, SL/TP)
- Le SAS d'entrée scalping (15s/10s inchangé)
- Le micro SL scalping (0.05% inchangé)
- Les gates économiques, structural proofs, trend alignment
- Le tick momentum / candle direction override

## Validations

- ✅ **1808 tests** backend passent (0 échec, 12 warnings cosmétiques)
- ✅ `tsc --noEmit` frontend sans erreur
- ✅ Non-régression complète (0 test supprimé)

## Documentation mise à jour

| Document | Changements |
|----------|-------------|
| `docs/CURRENT_STATE.md` | Version 2.0.28, features v2.0.28, tests 1808, section 5 Vision Reality Gap ✅ Complet, section 6 phases v1.8-v2.0 mises à jour, section 7 PaperRun ✅, table tests complète (40 fichiers) |
| `CHANGELOG.md` | Entrée [2.0.28] complète (Added + Changed + Technical) |
| `docs/ROADMAP.md` | État actuel v2.0.28, 1808 tests, timeline v2.0.1-v2.0.28 ajoutée |
| `docs/requirements_traceability.md` | Version v2.0.28, date 13/04, 12 FRs ajoutés (v2.0.10-v2.0.28), NFR tests 1808, table test coverage complète (40 fichiers) |
| `docs/HANDOFF_GPT.md` | Ce fichier (édité, pas recréé) |

## État actuel

- **Version** : v2.0.28
- **Tests** : 1808 passed ✅
- **Frontend** : tsc clean ✅
- **Prochaine action** : Lancer un run en mode auto (scalping + aggressive) pendant 1-2h pour valider les nouvelles protections aggressive et le cooldown réduit scalping

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v

# Lancer le robot (mode headless)
curl -X POST http://localhost:8000/paper/autonomous/start -H "Content-Type: application/json" -d '{"interval_seconds": 5, "profile": "scalping"}'
```
