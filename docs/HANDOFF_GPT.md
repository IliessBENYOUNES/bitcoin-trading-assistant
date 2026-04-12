# 🔄 Handoff GPT — Dernière intervention

> **Date :** 13 avril 2026
> **Version :** v2.0.21
> **Titre :** Momentum Stability Check + Journal Filters

---

## Problème

L'utilisateur a observé un pattern clair dans le journal des trades : **les trades gagnants conservent la même couleur de pastille** (bougie entrée = bougie sortie), tandis que les trades perdants changent de couleur immédiatement après l'entrée. Cela signifie que le robot entre en fin de bougie, juste avant un retournement.

Deux besoins :
1. **Filtres journal** — Pour analyser visuellement les trades par direction, résultat, cohérence de bougie, slot, type de sortie
2. **Prédiction retournement** — Ne pas entrer si la bougie est sur le point de changer de couleur

---

## Diagnostic

Le tick momentum override (v2.0.14) détecte la direction sur 30 secondes. Mais il ne vérifie pas si le mouvement est en train de **s'essouffler**. Exemple : sur 30s le prix monte (→ LONG), mais les 10 dernières secondes montrent un recul → la bougie va devenir rouge → si on entre LONG maintenant, on perd.

---

## Cause racine

Absence de vérification de la **stabilité** du momentum avant l'entrée. Le `detect_direction()` regarde la tendance globale (30s) mais ignore la micro-tendance récente (10s).

---

## Correction appliquée

### Backend : `tick_momentum_service.py`
- **Nouvelle méthode** `check_momentum_stability(slot, direction, long_window=30, short_window=10)` :
  - Compare la direction sur la fenêtre longue (30s) vs courte (10s)
  - Si la fenêtre courte va CONTRE la direction, bloque l'entrée
  - Si le ratio de ticks récents est > 65% contre la direction, bloque
  - Si données insuffisantes, laisse passer (pas de blocage au démarrage)

### Backend : `paper_trading_service.py`
- **Après le tick momentum override** (qui détecte la direction), appel à `check_momentum_stability()`
- Si instable → retourne `hold` avec `non_trade_reason="momentum_unstable"`

### Frontend : `PaperTradingPanel.tsx`
- **5 filtres** dans le journal : direction, résultat, cohérence bougie, slot, type de sortie
- **Stats dynamiques** sous les filtres : total, wins, losses, WR, PnL
- Bouton reset pour effacer tous les filtres
- Le journal affiche `filteredTrades` au lieu de `trades`

---

## Ce qui n'a PAS été touché

- ✅ Profils trading (aucun paramètre changé)
- ✅ Trailing stop / gain erosion / breakeven / stale exit
- ✅ Candle reversal exit (v2.0.18)
- ✅ Mode autonome backend
- ✅ Slot aggressive (sanctuarisé)
- ✅ JournalPanel (séparé du PaperTradingPanel)

---

## Validations

- ✅ **1739 tests** backend passent (dont 7 nouveaux)
- ✅ `tsc --noEmit` sans erreur
- ✅ Backend relancé et mode autonome actif
- ✅ Endpoint `/health` OK

---

## Documentation mise à jour

| Document | Changement |
|----------|-----------|
| `docs/CURRENT_STATE.md` | Version 2.0.21, tests 1739, features |
| `CHANGELOG.md` | Entrée v2.0.21 complète |
| `docs/HANDOFF_GPT.md` | Ce fichier |
| `docs/ROADMAP.md` | Pas modifié (pas de changement de phase) |
| `docs/requirements_traceability.md` | Pas modifié (pas de nouvelle exigence formelle) |

---

## Commit

```
feat(scalping): momentum stability check + journal filters v2.0.21
```

---

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.21 |
| Tests | 1739 ✅ |
| TSC | 0 erreur ✅ |
| Backend | Running (port 8000) |
| Autonome | Running (scalping, 10s) |

---

## Prochaine action recommandée

1. **Observer** les trades avec le nouveau filtre de stabilité pour valider que les entrées en fin de bougie sont bien bloquées
2. **Filtrer** dans le journal pour comparer : même couleur (gagnants) vs changée (perdants) et confirmer le pattern
3. Si le filtre `momentum_unstable` bloque trop souvent, **ajuster** les paramètres (fenêtre courte, ratio seuil)

---

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Mode autonome
curl -X POST http://localhost:8000/paper/autonomous/start -H "Content-Type: application/json" -d '{"interval_seconds": 10, "profile": "scalping"}'

# Tests
cd backend && python -m pytest tests/ -v
```
