# HANDOFF GPT — Gain Erosion Stop v2.0.12

**Date :** 12 avril 2026  
**Version :** v2.0.12  
**Commit :** `18186b3`

---

## Problème

Les petits gains (entre $0.25 et $1.00) fondaient sans protection. Le trailing stop ne s'active qu'à 0.04% (~$1). En dessous de ce seuil, le seul mécanisme de protection était le breakeven stop (qui attend PnL ≤ 0%) ou le stale négatif (2 min d'attente, fermeture souvent en perte). Résultat : un trade qui atteignait +$0.60 retombait à -$1.20 sans qu'aucun mécanisme ne le ferme à temps.

## Diagnostic

| Scénario | Peak | Trailing activé ? | Breakeven activé ? | Issue |
|----------|------|-------------------|---------------------|-------|
| Gain +$0.60 (0.025%) | 0.025% | Non (< 0.04%) | Non (PnL > 0) | Aucune protection → fond jusqu'au stale négatif → perte |
| Gain +$1.50 (0.06%) | 0.06% | Oui (≥ 0.04%) | N/A | Trailing protège → OK |
| Gain +$0.10 (0.004%) | 0.004% | Non | Non | Bruit, pas de gain significatif → OK |

Le trou se situe entre 0.01% (~$0.25) et 0.04% (~$1) : le gain existe mais n'est pas protégé.

## Cause racine

Absence de mécanisme de sortie entre le trailing stop (activation ≥ 0.04%) et le breakeven stop (attend PnL ≤ 0%). Les gains dans la zone 0.01%-0.04% fondent sans déclencheur de sortie.

## Correction appliquée

### Gain Erosion Stop

Nouveau mécanisme inséré entre le trailing stop et le breakeven stop :

```python
ge_ratio = getattr(profile_params, "gain_erosion_ratio", None)
if ge_ratio is not None and peak_pct >= 0.01 and peak_pct < ts_activation:
    ge_retention = 1.0 - ge_ratio  # 0.70 pour ratio=0.30
    ge_min_pct = peak_pct * ge_retention
    if unrealized_pct_now <= ge_min_pct:
        # Sort : le gain s'est érodé de plus de 30% du pic
        closed = self._close_position(open_pos, current_price, ge_reason, "closed_gain_erosion")
```

**Logique :** Si le gain a atteint un pic ≥ 0.01% mais < 0.04% (zone sous le trailing), et que le gain actuel est tombé sous 70% du pic (érosion > 30%), sortie immédiate.

**Exemples :**
- Peak +$0.60 (0.025%) → exit si gain < $0.42 → **sauve $0.42 au lieu de -$1.20**
- Peak +$0.30 (0.012%) → exit si gain < $0.21 → **sauve $0.21 au lieu de -$1.20**

### Fichiers modifiés

| Fichier | Changement |
|---------|-----------|
| `schemas/journal.py` | Nouveau champ `gain_erosion_ratio: Optional[float]` dans `TradingProfileParams` |
| `services/paper_trading_service.py` | Gain erosion stop inséré entre trailing et breakeven (31 lignes) |
| `services/trading_profile_service.py` | `gain_erosion_ratio=0.30` sur profil scalping |
| `services/journal_service.py` | Label `closed_gain_erosion` dans `REASON_LABELS` |
| `tests/test_pivot_v200.py` | 18 nouveaux tests `TestGainErosionStopV2012` + adaptation breakeven existant |

## Ce qui n'a PAS été touché

- ❌ Trailing stop relatif (v2.0.9 — inchangé, prend le relais au-dessus de 0.04%)
- ❌ Breakeven stop (toujours actif pour peak < 0.01% ou gain_erosion désactivé)
- ❌ Anti-churn reversal (v2.0.11 — inchangé)
- ❌ Veto bearish (v2.0.10 — inchangé)
- ❌ Profils aggressive/conservative (gain_erosion_ratio=None → désactivé)
- ❌ Frontend
- ❌ SL/TP, stale exit, signal contraire

## Validations

- ✅ **1665 tests** backend passent (18 ajoutés)
- ✅ Zéro régression sur les 1647 tests existants
- ✅ `tsc --noEmit` sans erreur frontend

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ v2.0.12, 1665 tests, feature gain erosion stop |
| `CHANGELOG.md` | ✅ Section v2.0.12 (Added + Changed + Technical) |
| `docs/ROADMAP.md` | ✅ État actuel v2.0.12 |
| `docs/requirements_traceability.md` | ✅ FR-GES-001, total 1665 tests |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## Commit

```
18186b3 — feat(scalping): gain erosion stop v2.0.12
```

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.12 |
| Tests | 1665 passing |
| Phase | Gain erosion stop livré |

## Prochaine action recommandée

1. **Full reset + nouveau run** : faire tourner le robot en scalping pendant 1-2h
2. **Vérifier que** :
   - Les trades avec peak entre $0.25 et $1 se ferment via `closed_gain_erosion` au lieu de `stale_negative`
   - Le trailing prend toujours le relais au-dessus de $1 (0.04%)
   - Le breakeven fonctionne toujours pour les cas < $0.25
   - Le PnL moyen par trade s'améliore (moins de pertes sur petits gains)
3. **Audit runtime** : `GET /audit/enriched-export` pour vérifier la distribution des exit_reason

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
cd backend && python -m pytest tests/test_pivot_v200.py::TestGainErosionStopV2012 -v
```
