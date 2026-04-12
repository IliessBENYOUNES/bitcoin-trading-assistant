# 🔄 HANDOFF GPT — v2.0.20

> **Date :** 13 avril 2026
> **Intervention :** Fix biais 100% SHORT sur slot scalping

---

## Problème

Le système de paper trading ne produisait **aucun trade LONG** sur le slot scalping depuis plusieurs heures. Tous les trades étaient des SHORTs (`mean_reversion_short` ou `tick_override_short`). Un trade aggressive a dérivé 3h en perte (-$10.32) avant d'être fermé en stale.

## Diagnostic

Analyse du flux d'entrée dans `_tick_single_slot()` :

1. Le **tick momentum override** (v2.0.14) détecte la direction réelle du prix sur 30 sec
2. Quand prix monte → `action = "acheter"` (LONG), `tm_override_active = True`
3. Le code BYPASS correctement : bearish_veto, scalping_reversal, tick_momentum_confirmation
4. **MAIS** le gate **structural proofs** (ligne ~1172) n'était PAS bypassé

## Cause racine

Le gate structural proofs vérifie 4 preuves pour valider une entrée :
- `micro_trend_score ≥ 3` pour LONG, `≤ -3` pour SHORT
- `price_position < 0.35` pour LONG, `> 0.65` pour SHORT
- `volume_ratio ≥ 1.0`
- `range_width_atr ≥ 1.5`

Le `micro_trend_score` vient des **indicateurs 15 min** (lagging). En marché bearish/ranging, il est **négatif**. Conséquence :
- **SHORT** : micro_trend négatif = 1 preuve (+ éventuellement volume) → **PASSE** (2/4 requis)
- **LONG** : micro_trend négatif = 0 preuves pour ce critère → **BLOQUÉ** (0-1/4, < 2 requis)

Le tick momentum override était conçu pour bypasser les indicateurs lagging. Mais le structural proofs gate réintroduisait ce même biais via micro_trend_score → **100% SHORT**.

## Correction appliquée

| Fichier | Ligne | Avant | Après |
|---------|-------|-------|-------|
| `paper_trading_service.py` | ~1180 | `if min_proofs > 0 and mq_data:` | `if min_proofs > 0 and mq_data and not tm_override_active:` |

1 seule ligne modifiée. Commentaire v2.0.20 ajouté avec justification.

## Ce qui n'a PAS été touché

- Profils (aucun paramètre changé)
- Tick momentum service (inchangé)
- Candle reversal (inchangé)
- Slot aggressive (les protections v2.0.19 sont déjà en place)
- Frontend (aucun changement)
- Toutes les autres gates (economic, market quality, min_score, risk engine)

## Validations

| Check | Résultat |
|-------|----------|
| Tests backend | **1732 passed** ✅ (+2 nouveaux) |
| TypeScript | `tsc --noEmit` clean ✅ |
| Test override LONG | `opened_long` avec micro_trend=-5 ✅ |
| Non-régression structural proofs | `min_structural_proofs=2` toujours actif sans override ✅ |

## Documentation mise à jour

| Document | Changement |
|----------|------------|
| `docs/CURRENT_STATE.md` | Version 2.0.20, tests 1732, description fix v2.0.20 |
| `CHANGELOG.md` | Nouvelle entrée [2.0.20] Fixed + Changed + Technical |
| `docs/ROADMAP.md` | (pas de changement de phase) |
| `docs/requirements_traceability.md` | (pas de nouvelles exigences) |
| `docs/HANDOFF_GPT.md` | Ce fichier |

## Commit

```
fix(scalping): bypass structural proofs when tick momentum override active — fixes 100% SHORT bias v2.0.20
```

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.20 |
| Tests | 1732 passing |
| Frontend | tsc clean |
| Prochaine action | Observer le runtime : vérifier que des LONGs apparaissent sur le slot scalping |

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v
cd frontend && npx tsc --noEmit
```

## Explication technique détaillée

### Pourquoi le bypass est sûr

Quand `tm_override_active=True`, la direction vient de la **direction réelle du prix** sur les 30 dernières secondes (6+ ticks). C'est une preuve structurelle EN SOI — plus fiable que le micro_trend_score 15 min qui est en retard.

Les protections restantes sans structural proofs :
1. **Economic gate** : vérifie la viabilité financière (coût RT vs capture attendue)
2. **Market quality gate** : quality_score ≥ 50, volume_ratio ≥ 0.8
3. **Min score** : |score| ≥ 10 (réduit en override, filtre les marchés morts)
4. **Cooldown** : 1 min minimum entre trades
5. **Risk engine** : SL/TP, kill switch, daily loss limit
6. **Max trades/jour** : 30 max

### Pourquoi le trade aggressive de 3h

Le slot aggressive n'a **pas** de tick momentum override (by design — c'est un swing intraday). Il suit les indicateurs 1h. En marché bearish sur le 1h, il ne produit que des SHORTs. Le trade #597 a dérivé 3h car l'ancien profil aggressive n'avait aucun trailing stop ni stale négatif raccourci. **C'est déjà corrigé** par v2.0.19 (`stale_negative=60 min`, `trailing 0.15%+30%`, `gain_erosion 50%`).
