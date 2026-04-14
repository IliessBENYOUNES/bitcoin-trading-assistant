# Moteur Expérimental Multi-Strategy — Documentation

> **Branche** : `experiment/v2-fees-and-1m`
> **Ports** : Backend 8001 / Frontend 5174
> **DB** : `bitcoin_experiment` (PostgreSQL séparé)
> **Dernière mise à jour** : 2026-04-14

---

## 1. Architecture

Le moteur expérimental est un wrapper autour du moteur standard (`PaperTradingService`).
Il ajoute une couche d'orchestration multi-stratégie par-dessus.

```
UI (bouton "Lancer le Robot" + profil Multi-Strategy)
 │
 ├─ POST /paper/engine-mode?mode=experimental
 ├─ POST /paper/profile  (scalping comme base)
 └─ POST /paper/tick
      │
      ▼
ExperimentalPaperTradingService
 ├─ Phase 1 : Gestion des positions ouvertes (SL/TP/trailing/micro SL)
 ├─ Phase 2 : Analyse de marché (fallback 5m → 30m → 4h)
 │    ├─ DecisionService.analyze() → score + série
 │    └─ MarketContextEngine.analyze(series) → régime, zone, volatilité
 ├─ Phase 3 : Orchestration (MultiStrategyEngine)
 │    ├─ Routing table : contexte → stratégies éligibles
 │    ├─ Chaque stratégie évalue le signal
 │    ├─ Filtres globaux (anti-collision, max positions, cooldown)
 │    └─ Risk layer (kill switch, exposition, anti-rafale)
 └─ Phase 4 : Ouverture des positions approuvées
```

### Fichiers clés

| Fichier | Rôle |
|---------|------|
| `services/experimental_engine.py` | Service principal, wrapper du moteur standard |
| `services/market_context_engine.py` | Détection du régime de marché (range/trend/breakout) |
| `services/multi_strategy_engine.py` | Orchestrateur : routing + filtres globaux |
| `services/multi_strategy_risk.py` | Risk layer : kill switch, exposition, anti-rafale |
| `services/strategies/aggressive.py` | Stratégie aggressive swing (trend-following) |
| `services/strategies/scalping.py` | Scalping classique |
| `services/strategies/breakout.py` | Cassure de range |
| `services/strategies/mean_reversion.py` | Retour à la moyenne aux bords du range |
| `services/strategies/micro_scalping.py` | Micro-scalping tick-based |
| `services/trading_cost_service.py` | Modèle de frais réalistes (Binance) |

---

## 2. Modèle de frais

Basé sur le barème Binance utilisateur standard (vérifié le 2026-04-13).

| Composante | Valeur | Source |
|---|---|---|
| Maker fee | 0.100% | Binance standard |
| Taker fee | 0.100% | Binance standard |
| Spread bid-ask | 0.050% | Estimé conservateur |
| Slippage | 0.030% | Estimé conservateur |
| **Coût aller (entrée)** | **0.155%** | taker + spread/2 + slippage |
| **Coût retour (sortie)** | **0.155%** | maker + spread/2 + slippage |
| **Round-trip total** | **0.310%** | entrée + sortie |

### Impact sur les positions

| Taille effective | Frais RT ($) | Gain min pour breakeven |
|---|---|---|
| $500 (micro_scalping) | $1.55 | 0.31% du mouvement |
| $800 (scalping, mean_rev) | $2.48 | 0.31% du mouvement |
| $1,000 (aggressive, breakout) | $3.10 | 0.31% du mouvement |
| $1,500 (aggressive × 1.5x) | $4.65 | 0.31% du mouvement |

> Les frais sont proportionnels à la taille effective. Réduire la taille ou le levier réduit les frais en valeur absolue, mais le % reste le même. L'enjeu est que le gain brut en $ dépasse les frais en $.

---

## 3. Routing table (contexte → stratégies)

| Contexte | Zone | Stratégies éligibles (par priorité) |
|---|---|---|
| **Range** | low | mean_reversion, scalping, micro_scalping |
| **Range** | mid | scalping, micro_scalping, mean_reversion |
| **Range** | high | mean_reversion, scalping, micro_scalping |
| **Trend** | toutes | aggressive, breakout, scalping |
| **Breakout** | toutes | breakout, aggressive |
| **Unknown** | toutes | scalping, micro_scalping |

Jusqu'à **3 positions simultanées** de stratégies différentes (ex: aggressive + breakout + scalping).

---

## 4. Paramètres des stratégies (après recalibration v2)

### 4.1 Aggressive

| Param | Valeur | Justification |
|---|---|---|
| Position | $1,000 | Frais $3.10 RT (avant $7.75 avec $2,500) |
| Levier | 1.0–1.5x | Max 1.5x si confiance ≥ 80 (avant 3x) |
| Micro SL | 0.50% | 0.15% était du bruit de marché |
| Trailing activation | 0.60% | 0.25% coupait les trades rentables |
| Trailing drop | 30% | Garde 70% du pic (avant 80%) |
| Take profit | 2.0% | Vise des vrais mouvements (avant 1.0%) |
| Stop loss | 1.5% | Laisse respirer (avant 1.0%) |
| Score min | 25 | Avant 15 (trop de trades médiocres) |
| Confiance min | 60 | Avant 40 |
| Min hold | 2 min | Avant 1 min |

### 4.2 Scalping

| Param | Valeur | Justification |
|---|---|---|
| Position | $800 | Frais $2.48 RT |
| Levier | 1.0x | Pas de levier (avant 1.5x) |
| Micro SL | 0.20% | 0.05% était du tick noise |
| Trailing activation | 0.30% | 0.10% trop serré |
| Take profit | 0.80% | Inchangé |
| Stop loss | 0.40% | Doublé (0.20% = bruit) |
| Score min | 20 | Avant 10 |
| Volume filter | désactivé | volume_sma_20 absent sur 30m fallback |

### 4.3 Breakout

| Param | Valeur |
|---|---|
| Position | $1,000 |
| Levier | 1.5x |
| Micro SL | 0.30% |
| Trailing activation | 0.40% |
| Volume filter | désactivé |

### 4.4 Micro-scalping

| Param | Valeur |
|---|---|
| Position | $500 |
| Levier | 1.0x |
| Micro SL | 0.10% |
| Max hold | 10 min |

### 4.5 Mean reversion

| Param | Valeur |
|---|---|
| Position | $800 |
| Levier | 1.0x |
| Micro SL | 0.20% |
| SL/TP | Dynamique basé sur la largeur du range |

---

## 5. Protections (Risk Layer)

| Protection | Valeur | Rôle |
|---|---|---|
| Max positions simultanées | 3 | Diversification |
| Max même direction | 2 | Pas de surexposition |
| Anti-collision long/short | actif | Pas de hedge implicite |
| 1 position par stratégie | actif | Pas de doublon |
| Cooldown entre ticks | 5s | Anti-rafale (entre ticks) |
| Exposition max | 80% du capital | Garde 20% en réserve |
| Kill switch | -5% drawdown | Arrêt d'urgence |

---

## 6. Analyse du Run #1 (2026-04-13 → 2026-04-14)

### Contexte
- **Période** : ~00h12 → ~01h30 (environ 1h20)
- **Marché** : BTC en légère hausse (+1.7% buy & hold)
- **Régime détecté** : Trend bullish, zone high, volatilité élevée
- **Engine mode** : experimental (après ~00h40, standard avant)

### Résultats

| Métrique | Valeur |
|---|---|
| Total trades | 23 |
| Gagnants | 2 (8.7%) |
| Perdants | 21 (91.3%) |
| PnL net | **-$504.62 (-5.05%)** |
| PnL brut estimé | ~+$30 |
| Frais totaux estimés | ~$535 |
| Buy & Hold | +1.70% |
| Profit Factor | 0.02 |
| Meilleur trade | +$5.74 |
| Pire trade | -$52.26 |
| Durée moyenne | 2.4 min |

### Ventilation par stratégie

| Stratégie | Trades | Note |
|---|---|---|
| aggressive | 21 | 100% des trades post-experimental |
| (standard engine) | 2 | Trades #1-#2 avant activation multi-strategy |
| scalping | 0 | Bloqué par volume_ratio |
| breakout | 0 | Bloqué par volume_ratio |
| mean_reversion | 0 | Bloqué par régime "trend" |
| micro_scalping | 0 | Bloqué par volatilité "high" |

### Diagnostic détaillé

**Problème #1 — Frais disproportionnés**

Chaque trade aggressive : $2,500 × 3x levier = $7,500 effectif → **$23.25 de frais RT**.
Le trailing stop coupait typiquement à +0.2-0.3% de gain prix, soit ~$15-22 brut.
Résultat : les trades "gagnants" en brut étaient perdants en net.

Exemples :
- Trade #6 : brut +$13.22, frais $23.25 → net **-$10.03**
- Trade #11 : brut +$12.27, frais $23.25 → net **-$10.98**
- Trade #17 : brut +$13.30, frais $23.25 → net **-$9.95**

**Problème #2 — Micro SL trop serré**

Le micro SL à 0.15% se déclenchait sur du simple bruit de marché :
- 8 trades fermés par micro SL en moins de 72 secondes
- Le mouvement de -0.15% sur BTC à $74k = seulement $111 — un tick normal

**Problème #3 — Zéro diversité**

Les 4 autres stratégies ne se déclenchaient jamais :
- Scalping : `volume_ratio: 0.0` sur les candles 30m (pas de `volume_sma_20`)
- Breakout : idem, bloqué par `MIN_VOLUME_RATIO = 1.3`
- Mean reversion : régime "trend" détecté → stratégie inactive
- Micro-scalping : volatilité "high" → stratégie inactive

**Problème #4 — Boucle de re-entry**

L'aggressive se faisait couper par le micro SL, puis re-entrait immédiatement (cooldown insuffisant), se faisait re-couper, etc. Trades #19→23 en 4 minutes.

### Corrections appliquées (commit eceb43c)

1. **Positions réduites** : $2,500 → $800-$1,000 selon stratégie
2. **Levier réduit** : 3x → 1.0-1.5x max
3. **Micro SL élargi** : 0.15% → 0.20-0.50% selon stratégie
4. **Trailing élargi** : laisser les trades respirer au lieu de couper au premier recul
5. **Volume filter désactivé** : les candles 30m n'ont pas `volume_sma_20`
6. **Seuils d'entrée relevés** : score min 15→25 (aggressive), 10→20 (scalping)
7. **Cooldown ajusté** : 30s → 5s entre ticks, mais min_hold augmenté

---

## 7. Commandes utiles

```bash
# Démarrer le backend expérimental
cd bitcoin-trading-v2-experiment/backend
"C:/Users/ilies/git/bitcoin-trading-assistant/backend/venv/Scripts/python.exe" \
  -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Frontend expérimental
cd bitcoin-trading-v2-experiment/frontend
npm run dev  # port 5174

# Tester les endpoints
curl http://localhost:8001/paper/engine-mode
curl -X POST "http://localhost:8001/paper/engine-mode?mode=experimental"
curl http://localhost:8001/paper/market-context?timeframe=5m
curl -X POST http://localhost:8001/paper/tick

# Tests
cd bitcoin-trading-v2-experiment/backend
python -m pytest tests/test_multi_strategy.py -v
```

---

## 8. Historique des runs

| Run | Date | Trades | Win% | PnL net | Notes |
|-----|------|--------|------|---------|-------|
| #1 | 2026-04-13/14 | 23 | 8.7% | -$504.62 | Frais dévastateurs, mono-stratégie aggressive |
| #2 | 2026-04-14 | — | — | — | Après recalibration v2 (positions + SL + levier) |
