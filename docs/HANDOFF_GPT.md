# HANDOFF GPT — État du run live v2.0.3

**Date :** 11 avril 2026  
**Version :** v2.0.3  
**Commit :** `de99aca` — fix(paper): auto-activation du compte dans POST /paper/tick + self-healing frontend

---

## Contexte

L'utilisateur a lancé le robot en mode **Scalping** depuis le frontend (bouton "Lancer le Robot"). Le robot tourne avec tick auto toutes les **5 secondes**. Le multi-slot est actif : **scalping** (15m) + **aggressive** (1h) en parallèle, jusqu'à 3 positions simultanées.

## Fix appliqué juste avant ce run

Le paper trading était bloqué sur "INACTIF" après un full reset. Le message "Activez-le via POST /paper/account" apparaissait — inadapté pour un utilisateur final. 

**Corrections (commit `de99aca`) :**
1. `POST /paper/tick` auto-active le compte si inactif + configure multi-slot ≥3
2. Frontend `doAutoTick` + `manualTick` : si "inactive" → `createPaperAccount()` + retry (self-healing)
3. Frontend `handleStartAuto` : active le compte avant de démarrer l'auto-tick
4. Message UX : "Cliquez sur Lancer le Robot" au lieu de "POST /paper/account"

## Diagnostic du run en cours (après ~10 min)

**Aucun trade ouvert.** Les deux slots retournent `hold` à chaque tick :

| Slot | Résultat | Raison | Détail |
|------|----------|--------|--------|
| ⚡ Scalping | `hold` | `micro_trend_insufficient` | `micro_trend_score = -2` < 2 requis. La micro-tendance BTC est baissière — le gate v2.0.3 bloque les longs sans tendance. |
| 🔥 Aggressive | `hold` | score trop faible | Score = 17, confiance = LOW. Seuil buy = 20 → pas atteint. |

**BTC :** ~$73 550 (en légère baisse)

## Analyse

Le comportement est **normal et attendu** après les corrections v2.0.3 :
- **Avant v2.0.3** : 57 trades/nuit, 91% closed_stale (morts) — le robot entrait sur du bruit
- **Après v2.0.3** : les gates filtrent les entrées sans tendance. Les seuils sont :
  - Scalping : `buy_threshold=30`, `min_score=30`, `min_micro_trend_long=2`
  - Aggressive : `buy_threshold=20`, analyse sur 1h

Le BTC est actuellement en micro-tendance baissière (`micro_trend_score = -2`), avec un score composite faible (17). Aucun des deux slots ne voit d'opportunité.

**Ce n'est PAS un bug.** C'est la correction qui fonctionne : le robot attend une vraie opportunité au lieu d'entrer sur du bruit.

## Ce qui va déclencher un trade

- **Scalping long** : quand `micro_trend_score ≥ 2` ET `composite_score ≥ 30` ET `structural_proofs ≥ 2`
- **Scalping short** : quand `score ≤ -30` ET mean-reversion confirmée (2 oscillateurs convergents)
- **Aggressive** : quand `score ≥ 20` (ou `≤ -15` pour short) sur timeframe 1h

## Prochaines actions recommandées

1. **Laisser tourner** le robot — les conditions de marché changent, un trade finira par passer
2. **Si aucun trade après plusieurs heures** : considérer un léger assouplissement du `min_micro_trend_long` (2→1) ou du `buy_threshold` (30→28) pour le scalping
3. **Pour un run nocturne** : passer en mode **Headless** (bouton vert) pour que le robot tourne côté serveur même navigateur fermé

## État technique

| Élément | Valeur |
|---------|--------|
| Version | v2.0.3 |
| Tests backend | 1554 passing ✅ |
| TypeScript | tsc --noEmit clean ✅ |
| Backend | `uvicorn app.main:app --reload --port 8000` |
| Frontend | `npm run dev` (Vite) |
| Profil actif | scalping (multi-slot: scalping + aggressive) |
| Compte | actif, capital $10 000, 0 trades |

## Commandes de relance

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v

# Diagnostic rapide tick
cd backend && python -c "import urllib.request, json; req = urllib.request.Request('http://localhost:8000/paper/tick', method='POST', headers={'Content-Type': 'application/json'}, data=b''); r = urllib.request.urlopen(req); t = json.loads(r.read()); print(t['action_taken'], '-', t['detail'][:200])"
```
