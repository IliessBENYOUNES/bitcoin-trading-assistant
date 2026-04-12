# HANDOFF GPT — Candle Direction Indicator + REST Price Fallback v2.0.15

**Date :** 12 avril 2026  
**Version :** v2.0.15  
**Commit :** `5589421`

---

## Problème

Deux demandes utilisateur :

1. **Indicateur de couleur de bougie manquant** — Aucun moyen visuel de vérifier dans le frontend que les positions scalping entrent dans le sens du prix.

2. **Prix BTC stale (~5 min de retard)** — Le Dashboard affichait un prix en retard quand le WebSocket Binance est inaccessible.

## Correction appliquée

### Feature 1 — Candle Direction Indicator

| Fichier | Changement |
|---------|-----------|
| `models/paper_account.py` | Nouvelle colonne `entry_candle_direction VARCHAR(10)` nullable |
| `schemas/paper_trading.py` | Champ ajouté dans `PaperTradeResponse` + `PaperTradeExportItem` |
| `services/paper_trading_service.py` | Param + détermination via tick momentum (scalping) ou micro_trend (autres) |
| `migrate_v2015.py` | Script de migration DB |
| `tests/test_paper_trading.py` | 7 nouveaux tests |
| `types/api.ts` | Champ dans types TS |
| `PaperTradingPanel.tsx` | Composant `CandleDirectionDot` : dot 🟢/🔴 + tooltip cohérence |

### Feature 2 — REST Price Fallback

| Fichier | Changement |
|---------|-----------|
| `useLivePrice.ts` | Fallback REST /market/price si WS down après 5s, polling 10s |
| `PriceTicker.tsx` | Prop `source`, badge "REST" orange |
| `Dashboard.tsx` | Propagation `source`, footer "Mode REST (prix ~10s)" |

## Validations

- ✅ **1701 tests** backend passent (7 ajoutés)
- ✅ `tsc --noEmit` sans erreur frontend
- ✅ Migration DB exécutée

## Documentation mise à jour

| Document | Mis à jour |
|----------|-----------|
| `docs/CURRENT_STATE.md` | ✅ v2.0.15, 1701 tests |
| `CHANGELOG.md` | ✅ Section v2.0.15 |
| `docs/ROADMAP.md` | ✅ État actuel v2.0.15 |
| `docs/requirements_traceability.md` | ✅ FR-CDI-001, FR-RPF-001 |
| `docs/HANDOFF_GPT.md` | ✅ Ce fichier |

## État actuel

| Élément | Valeur |
|---------|--------|
| Version | v2.0.15 |
| Tests | 1701 passing |

## Commandes de relance

```bash
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
cd backend && python -m pytest tests/ -v
```
