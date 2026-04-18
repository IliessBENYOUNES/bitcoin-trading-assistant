# 🔄 HANDOFF GPT — Dernière intervention

## Date : 18 avril 2026 — v2.0.30

---

## Problème

Les deux moteurs (MAIN et EXPERIMENTAL) perdent de l'argent sur une période où BTC a fait **+6.6%** :
- MAIN : **-$51 brut** (831 trades) — mais **-$6 158 simulé avec frais** (98.8% des trades < 0.31% = bruit pur)
- EXPERIMENTAL : **-$468 net** (46 trades) — frais cumulés **$442** soit **17× la perte brute** de $26

Le problème central : trop de churn, signaux technique mal calibrés, entrées aux pires moments horaires, breakeven qui ferme systématiquement au niveau des frais.

## Diagnostic

Analyse statistique profonde de 831+46 trades avec corrélations Pearson, distributions, heatmaps :

1. **Corrélation |score| vs pnl_pct = -0.134 (p=0.0001)** — statistiquement significative. Scores >60 (n=705) : WR 48% (aléatoire). Scores 20-40 (n=26) : WR 65% (vrai edge). → le score élevé arrive trop tard (signal déjà digéré par le marché).
2. **Fenêtre toxique 13-16h UTC** — cumule -$104 sur 4 jours (2× le résultat brut). Heure 14h UTC seule = -$55 (US open + macro releases).
3. **Micro SL scalping destructeur** — 184 coupures à -$1.98 avg = -$364 cumulés. Coupe avant que les trades puissent se développer vers le TP.
4. **Breakeven systématiquement net négatif** — 18 trades EXP fermés en breakeven avec peak moyen 0.13% (< frais 0.31%), 100% net-negative, -$111 cumulés.
5. **Chop ranges non filtrés** — aucun filtre sur la largeur du range (range_width_atr). Les marchés compressés (< 1.5× ATR) sont mathématiquement incapables de capturer 0.62% nécessaires pour couvrir 2× frais.

## Cause racine

Le moteur n'intégrait pas les apprentissages tirés de l'échantillon statistique propre. Les gates existants (economic, structural, SAS) filtrent correctement sur l'amplitude attendue mais pas sur :
- Le **timing horaire** (14h UTC = destructeur systémique)
- La **saturation du score** (>50 = signal consommé)
- La **structure du marché** (chop range = impossible à scalper)
- L'**amplitude réelle du peak** avant breakeven (< 2× frais = perte garantie)

De plus, le micro SL scalping à 0.20% était trop serré par rapport aux frais 0.31% : coupe avant même d'atteindre le seuil de rentabilité.

## Corrections appliquées

### Fichiers modifiés

| Fichier | Changement |
|---------|------------|
| `backend/app/schemas/journal.py` | +4 nouveaux champs `TradingProfileParams` : `max_score`, `blocked_hours_utc`, `min_range_atr`, `breakeven_min_peak_fee_multiple` |
| `backend/app/services/paper_trading_service.py` | +3 nouveaux gates dans `_tick_single_slot()` : max_score, blocked_hours_utc, min_range_atr + intégration `breakeven_min_peak_fee_multiple` dans la logique breakeven existante |
| `backend/app/services/trading_profile_service.py` | Activation des 4 gates sur profils `scalping` et `aggressive` + désactivation micro_sl scalping + relève volume_ratio aggressive |
| `backend/tests/test_micro_stop_loss.py` | `test_scalping_has_micro_sl` adapté à la désactivation volontaire |

### Nouveaux paramètres — Scalping

| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| `micro_stop_loss_pct` | 0.20 | **None** | audit : 184 coupures, -$364 cum ; SL classique 0.50% reste |
| `max_score` | — | **50** | corrélation r=-0.134 ; scores >60 = WR 48% aléatoire |
| `blocked_hours_utc` | — | **[13,14,15,16]** | audit : -$104 cum sur 3h (US open + macro) |
| `min_range_atr` | — | **1.5** | rejette chop ranges où 0.62% est inatteignable |
| `breakeven_min_peak_fee_multiple` | — | **2.0** | peak doit atteindre 0.62% (2× frais) avant breakeven |

### Nouveaux paramètres — Aggressive

| Paramètre | Avant | Après | Justification |
|-----------|-------|-------|---------------|
| `min_volume_ratio` | 0.5 | **0.8** | volume < SMA20 = signal fiable de futur chop |
| `max_score` | — | **55** | scores >55 sur swings 1h = signal trop tardif |
| `blocked_hours_utc` | — | **[13,14,15,16]** | même fenêtre destructive |
| `min_range_atr` | — | **1.5** | scalping 1h nécessite amplitude |
| `breakeven_min_peak_fee_multiple` | — | **2.0** | audit EXP aggressive : 18 trades breakeven tous net négatifs |

## Ce qui n'a PAS été touché

- Le frontend (aucun changement — la config vit dans les presets backend)
- Les profils `conservative` et `balanced` (inchangés)
- Les mécanismes de sortie existants (trailing, stale, SL/TP, gain_erosion, candle_reversal)
- Le micro SL aggressive (maintenu à 0.30%)
- Le SAS d'entrée (inchangé)
- Les gates économique, structural, trend alignment, tick momentum
- Le pipeline de décision / scoring composite
- Le moteur expérimental (worktree séparé `bitcoin-trading-v2-experiment`, non touché)
- Les fichiers `binance_service.py`, `coingecko_service.py`, `cryptocompare_service.py`, `news_service.py`, `price_service.py` (modifications visibles dans git status = uniquement CRLF, aucun changement de contenu)

## Validations

- ✅ **1773 tests backend passent** (baseline préservée)
- ✅ **35 tests failed** identiques à avant les changements (régressions v2.0.29 préexistantes sur anciens seuils — déjà documentées dans le commit 261b83f)
- ✅ `tsc --noEmit` frontend sans erreur (exit 0)
- ✅ Diff baseline/après : **0 régression nouvelle** introduite par v2.0.30
- ✅ Aucun import manquant, aucun schéma Pydantic cassé (defaults None garantissent la rétrocompatibilité)

## Documentation mise à jour

| Document | Changements |
|----------|-------------|
| `CHANGELOG.md` | Entrée [2.0.30] complète (Added : audit stats + 4 gates ; Changed : micro_sl off, volume_ratio 0.8 ; Technical : 1773/35) |
| `docs/CURRENT_STATE.md` | En-tête version 2.0.30 / date 2026-04-18 / tests 1773 passing, ligne phase courante mise à jour |
| `docs/ROADMAP.md` | État actuel v2.0.30 + timeline v2.0.29/v2.0.30 ajoutée |
| `docs/requirements_traceability.md` | Version v2.0.30, date 18/04, **5 nouveaux FRs** (FR-BHU-001, FR-MSC-002, FR-RAT-001, FR-BPM-001, FR-MSL-003) |
| `docs/ENGINE_AUDIT.md` | Section "v2.0.30 — Gates statistiques" ajoutée dans historique corrections (avant v2.0.29) |
| `docs/HANDOFF_GPT.md` | Ce fichier (édité, pas recréé) |

## État actuel

- **Version** : v2.0.30
- **Tests backend** : 1773 passed / 35 failed (régressions préexistantes v2.0.29)
- **Frontend** : tsc clean ✅
- **Audit statistique** : 13 insights non triviaux documentés (disponibles dans la session)
- **Prochaine action (Session 4)** : Validation runtime sur 7 jours depuis le laptop perso
  - Pull du code v2.0.30
  - Reset comptes paper trading
  - Laisser tourner 7 jours en mode auto
  - Métriques cibles : PnL net > 0, 10-20 trades/j scalping, WR net > 50%, durée moy > 5 min, aucun trade 13-16h UTC, aucun trade |score| > 50

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && .\venv\Scripts\python.exe -m pytest tests/ -q --no-header --tb=no

# Lancer le robot (mode headless)
curl -X POST http://localhost:8000/paper/autonomous/start -H "Content-Type: application/json" -d '{"interval_seconds": 5, "profile": "auto"}'

# Export journal post-validation (7j)
curl http://localhost:8000/paper/journal/export > journal_v2.0.30_day7.json
```
