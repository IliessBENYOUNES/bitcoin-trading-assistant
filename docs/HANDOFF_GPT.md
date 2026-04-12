# 🔄 HANDOFF GPT — Dernière intervention

> **Date :** 13 avril 2026
> **Version :** v2.0.22
> **Intervention :** SAS d'Entrée Sécurisé (Entry Airlock)

---

## Problème

Les trades scalping s'ouvraient et perdaient immédiatement de l'argent à cause de changements de bougie destructeurs. Cas le plus grave : trade #620 (SHORT @ 70825.67), stop loss atteint en 36 secondes → -$15.27. Ce seul trade a effacé tous les gains de la session (+$7.27 PnL total passé à -$7.27).

**Données clés du run :**
- 22 trades, 12 gagnants, 10 perdants (win rate 54.55%)
- Mais les pertes étaient disproportionnées (worst: -$15.27 vs best: +$25.58)
- Les trades SL hit avaient tous un PnL immédiatement négatif dès l'ouverture
- Le prix allait systématiquement contre la direction avant même que les protections ne puissent agir

## Diagnostic

Analyse des trades export JSON fourni par l'utilisateur :
1. Les trades destructeurs entraient alors que le prix allait immédiatement en sens inverse
2. Le momentum stability check (v2.0.21) filtrait les fins de bougie mais pas les entrées à contre-courant
3. Aucune vérification post-gates ne validait que le prix allait réellement dans la bonne direction après décision d'ouverture

## Cause racine

Le système passait tous les gates (market quality, economic, structural proofs, momentum stability) et ouvrait immédiatement. Mais entre la décision et le prochain tick (~5s), le prix pouvait se retourner drastiquement (changement de bougie). Le système n'avait aucun mécanisme pour "observer avant d'entrer".

## Correction appliquée

### Nouveau service : `EntrySasService` (in-memory)
- **Fichier :** `backend/app/services/entry_sas_service.py`
- Pattern identique à `TickMomentumService` (class-level dict par slot)
- Stocke des `SasPendingEntry` avec tous les paramètres nécessaires à l'ouverture
- `evaluate()` calcule le PnL virtuel et décide : approved / rejected / waiting

### Schéma : 4 nouveaux paramètres
- **Fichier :** `backend/app/schemas/journal.py` (TradingProfileParams)
- `entry_sas_enabled` (bool) : active le SAS
- `entry_sas_duration_seconds` (float, 15.0) : timeout max
- `entry_sas_min_positive_seconds` (float, 10.0) : durée min de PnL positif
- `entry_sas_range_caution` (bool, True) : prudence aux extrémités de range

### Profil scalping configuré
- **Fichier :** `backend/app/services/trading_profile_service.py`
- SAS activé uniquement sur scalping (les autres profils gardent `entry_sas_enabled=False`)

### Intégration dans le flux de tick
- **Fichier :** `backend/app/services/paper_trading_service.py`
- 2 points d'insertion :
  1. **Avant évaluation** (~l.937) : si SAS pending → évaluer (approved/rejected/waiting)
  2. **Après tous les gates** (~l.1660) : si SAS enabled → créer SAS pending au lieu d'ouvrir

### Logique du SAS
1. **Création** : quand tous les gates passent, stocker entrée virtuelle au prix courant
2. **Évaluation** (ticks suivants) :
   - PnL virtuel = (current - virtual_entry) / virtual_entry × 100 (long) ou inverse (short)
   - Si positif continu ≥ min_positive_seconds → **approved**
   - Si négatif après ½ temps (jamais positif) → **rejected (anticipé)**
   - Si timeout atteint + positif maintenant → **approved (timeout+positif)**
   - Si timeout atteint + négatif → **rejected (timeout)**
3. **Range caution** : LONG en haut de range (>70%) ou SHORT en bas de range (<30%) + PnL négatif après 2 ticks → **rejected immédiat**

## Ce qui n'a PAS été touché

- Les profils conservative, balanced, aggressive → `entry_sas_enabled=False` par défaut
- Le flux d'ouverture directe (sans SAS) → conservé pour les profils non-SAS
- Les mécanismes de sortie (trailing, gain erosion, breakeven, stale, candle reversal)
- Le TickMomentumService → aucune modification
- Le frontend → aucune modification (le SAS apparaît comme "hold" avec detail explicite)

## Validations

- ✅ **1778 tests** backend passent (1739 + 39 nouveaux)
- ✅ `tsc --noEmit` sans erreur
- ✅ 39 tests dédiés couvrant : création, évaluation (approved/rejected/waiting), range caution, PnL calcul, tracking, profils, scénarios réels
- ✅ 3 scénarios réels simulés : trade #620 (rejeté), trade #600 (approuvé), trade #605 (rejeté range caution)

## Documentation mise à jour

| Document | Changements |
|----------|-------------|
| `docs/CURRENT_STATE.md` | Version v2.0.22, 1778 tests, nouvelle feature SAS |
| `CHANGELOG.md` | Nouvelle section [2.0.22] complète |
| `docs/ROADMAP.md` | (pas de changement de phase) |
| `docs/requirements_traceability.md` | (pas de nouveau FR) |
| `docs/HANDOFF_GPT.md` | Ce fichier |

## Commit

```
feat(scalping): SAS d'entrée sécurisé — observation avant ouverture v2.0.22
```

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.22 |
| Tests | 1778 passing |
| Frontend | tsc OK |
| SAS activé | scalping (15s max, 10s positif, range caution ON) |
| Prochaine action | Tester en runtime (paper trading live) pour mesurer l'impact |

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v

# TypeScript check
cd frontend && npx tsc --noEmit
```
