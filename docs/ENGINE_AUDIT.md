# Audit Comparatif & Suivi d'Amelioration des Moteurs de Trading

> **Document vivant** — Mis a jour a chaque iteration d'amelioration.
> Derniere mise a jour : 17 avril 2026

---

## Table des matieres

1. [Vue d'ensemble des 2 moteurs](#1-vue-densemble-des-2-moteurs)
2. [Conception technique comparee](#2-conception-technique-comparee)
3. [Audit du 17 avril 2026 — Analyse des journaux](#3-audit-du-17-avril-2026--analyse-des-journaux)
4. [Diagnostic des problemes](#4-diagnostic-des-problemes)
5. [Plan de refonte](#5-plan-de-refonte)
6. [Historique des corrections](#6-historique-des-corrections)

---

## 1. Vue d'ensemble des 2 moteurs

### 1.1 Moteur MAIN (branche `master`)

| Element | Valeur |
|---------|--------|
| Branche | `master` |
| Dossier | `C:\Users\ilies\git\bitcoin-trading-assistant` |
| Backend | `localhost:8000` |
| Frontend | `localhost:5173` |
| DB | `bitcoin_assistant` (PostgreSQL) |
| Profil actif | `auto` (multi-slot : scalping + aggressive + balanced) |
| Gestion des frais | **AUCUNE** — PnL brut seulement |
| Statut | **Irealiste** — les resultats sont fausses car les frais ne sont pas deduits |

**Le moteur MAIN est la version de production historique.** Il a accumule 28 versions d'ajustements (v2.0.0 a v2.0.28) mais ne deduit jamais les frais de trading du PnL. Tous ses resultats sont donc structurellement trop optimistes.

### 1.2 Moteur EXPERIMENTAL (branche `experiment/v2-fees-and-1m`)

| Element | Valeur |
|---------|--------|
| Branche | `experiment/v2-fees-and-1m` |
| Dossier | `C:\Users\ilies\git\bitcoin-trading-v2-experiment` (git worktree) |
| Backend | `localhost:8001` |
| Frontend | `localhost:5174` |
| DB | `bitcoin_experiment` (PostgreSQL) |
| Profil actif | `scalping` (mono-profil) |
| Gestion des frais | **OUI** — frais Binance realistes (0.31% round-trip) |
| Statut | **Realiste mais mal calibre** — les frais detruisent toute la performance |

**Le moteur EXPERIMENTAL est un fork du main** avec 3 modifications cles :
1. Frais de trading deduits dans `_close_position()` (gross_pnl - fees = net_pnl)
2. Breakeven stop ajuste pour inclure les frais (seuil releve)
3. Profils ajustes (trailing activation releve, momentum fade desactive, timeframe 5m)

---

## 2. Conception technique comparee

### 2.1 Architecture commune

Les deux moteurs partagent la meme architecture :

```
paper_trading_service.py (2659 lignes)
  tick()                       → Point d'entree, itere sur les slots
  _tick_single_slot()          → Logique d'un slot (monitoring + ouverture)
  _open_position()             → Cree un trade en DB
  _close_position()            → Ferme un trade, calcule le PnL ← DIFFERENCE PRINCIPALE
  _check_sl_tp()               → Verifie stop loss / take profit
  _check_market_quality()      → Filtre qualite de marche
  _scalping_reversal_check()   → Reversal scalping

trading_profile_service.py     → 4 profils (conservative, balanced, aggressive, scalping)
trading_cost_service.py        → Modele de couts (presets optimistic/realistic/stressed)
decision_service.py            → Moteur de decision (score composite + confiance)
signal_service.py              → Signaux techniques (RSI, MACD, SMA, Bollinger)
tick_momentum_service.py       → Detection de direction par momentum de tick
```

### 2.2 Differences entre les 2 moteurs

#### A. Calcul du PnL (`_close_position`)

**MAIN :**
```python
pnl = trade.position_size_usd * leverage * pnl_pct / 100
# C'est tout. Pas de frais. pnl = gross_pnl.
```

**EXPERIMENTAL :**
```python
gross_pnl = trade.position_size_usd * leverage * pnl_pct / 100
cost_model = get_cost_model("realistic")
effective_size = trade.position_size_usd * leverage
trading_fees = cost_model.round_trip_cost_usd(effective_size)
pnl = gross_pnl - trading_fees  # NET
trade.gross_pnl = gross_pnl
trade.trading_fees = trading_fees
```

#### B. Breakeven stop

**MAIN :**
```python
# Ferme quand PnL retombe a 0%
if peak_pct >= breakeven_activation and unrealized_pct_now <= 0:
```

**EXPERIMENTAL :**
```python
# Ferme quand PnL retombe au niveau des frais (0.31%)
_be_fee_pct = cost_model.round_trip_cost_pct()  # ~0.28-0.31%
if peak_pct >= breakeven_activation and unrealized_pct_now <= _be_fee_pct:
```

#### C. Profils scalping

| Parametre | MAIN | EXPERIMENTAL | Impact |
|-----------|------|-------------|--------|
| `analysis_timeframe` | 15m | **5m** | Indicateurs plus reactifs |
| `momentum_fade_enabled` | True (restricted) | **False** | Plus de sorties prematurees |
| `trailing_stop_activation_pct` | 0.04% | **0.10%** | Evite de verrouiller des poussieres |
| `gain_erosion_ratio` (aggressive) | 0.70 | **None** (desactive) | Evite sorties a +$0.40 brut = -$7 net |

### 2.3 Modele de couts (`trading_cost_service.py`)

Le modele de couts existe dans les DEUX moteurs mais n'est UTILISE que par l'experimental.

**Preset "realistic" (utilise par l'experimental) :**

| Composant | Valeur | Calcul |
|-----------|--------|--------|
| Maker fee | 0.10% | Binance standard |
| Taker fee | 0.10% | Binance standard |
| Spread | 0.05% | BTC/USDT conditions normales |
| Slippage | 0.03% | Mix market/limit orders |
| **Cout par cote** | **0.155%** | taker + spread/2 + slippage |
| **Round-trip** | **0.310%** | entree + sortie |

**Impact en dollars selon la taille :**

| Position | Levier | Taille effective | Frais round-trip |
|----------|--------|-----------------|-----------------|
| $2,500 | x1 | $2,500 | **$7.75** |
| $2,500 | x1.5 | $3,750 | **$11.63** |
| $2,500 | x2 | $5,000 | **$15.50** |
| $2,500 | x3 | $7,500 | **$23.25** |

### 2.4 Mecanismes de sortie (communs)

Ordre de priorite dans `_tick_single_slot` :

1. **SL/TP classique** — Stop loss / Take profit atteints
2. **Micro stop loss** — PnL latent < -X% (scalping: 0.05%, aggressive: 0.15%)
3. **Trailing stop** — Gain recule de X% depuis le pic
4. **Gain erosion** — Gain erode de X% du pic (sous activation trailing)
5. **Breakeven stop** — Position etait gagnante, retombe a 0 (ou aux frais dans EXP)
6. **Candle reversal** — Momentum inverse detecte
7. **Stale exit** — Position stagnante (scalping: 5min, aggressive: 180min)
8. **Signal contraire** — Score de decision inverse

---

## 3. Audit du 17 avril 2026 — Analyse des journaux

### 3.1 Chiffres bruts

| Metrique | MAIN | EXPERIMENTAL |
|----------|------|-------------|
| Capital initial | $10,000 | $10,000 |
| Capital final | $9,949.33 | $9,531.78 |
| **PnL net** | **-$50.72 (-0.51%)** | **-$468.22 (-4.68%)** |
| Peak capital | $10,028.50 | $10,000 (jamais en profit) |
| Max drawdown | 1.37% | 4.68% |
| Buy & Hold BTC | +6.61% | +5.37% |
| Total trades | 831 | 46 |
| Win rate | 50.48% | 4.35% |
| Avg PnL/trade | -$0.06 | -$10.18 |
| Best trade | +$43.74 | +$5.65 |
| Worst trade | -$30.36 | -$68.66 |
| Profit factor | 0.92 | 0.01 |
| Sharpe ratio | -0.52 | -0.25 |
| Duree moyenne | 4.5 min | 21 min |
| Periode | 13-17 avril (4 jours) | 14-17 avril (3 jours) |
| **BTC pendant la periode** | **$73,281 -> $78,122 (+6.6%)** | **$74,174 -> $78,168 (+5.4%)** |

### 3.2 Simulation : le MAIN avec frais

Le main ne deduit pas les frais. Voici ce que donnerait le main en conditions reelles :

| Metrique | MAIN brut | MAIN simule avec frais |
|----------|-----------|----------------------|
| PnL | -$50.72 | **-$6,158.66** |
| Frais totaux | $0 | **$6,109.98** |
| Trades rentables | 419 (50.48%) | **22 (2.6%)** |
| Trades gagants tues par frais | — | **397** |
| Trades avec \|PnL%\| < 0.31% | — | **821/831 (98.8%)** |

**Conclusion : Le moteur MAIN est une illusion.** 98.8% de ses trades sont dans le bruit des frais. En conditions reelles, il perdrait **$6,159** au lieu de $51.

### 3.3 Repartition par profil (MAIN)

| Profil | Trades | PnL brut | Frais simules | PnL net simule | WR | Duree moy |
|--------|--------|----------|--------------|---------------|-----|-----------|
| **scalping** | 797 (96%) | -$101.44 | $5,738 | **-$5,839** | 48% | 82s |
| **aggressive** | 30 (3.6%) | +$31.58 | $333 | **-$302** | 60% | 4.1min |
| **balanced** | 4 (0.5%) | +$21.18 | $39 | **-$18** | 50% | 10.6h |

Le scalping genere 96% des trades mais TOUTE la perte. Le balanced est le seul profil presque viable.

### 3.4 Repartition par duree (MAIN)

| Duree | Trades | Avg PnL | Total PnL | WR | Verdict |
|-------|--------|---------|-----------|-----|---------|
| <30s | 26 | -$1.18 | -$30.59 | 31% | Destructeur |
| 30s-1min | 143 | -$0.41 | -$58.26 | 49% | Destructeur |
| 1-2min | 550 | -$0.01 | -$5.99 | 50% | Bruit pur |
| 2-5min | 91 | -$0.19 | -$17.22 | 44% | Negatif |
| **5-10min** | **15** | **+$1.64** | **+$24.54** | **53%** | **Positif** |
| **10-30min** | **2** | **+$8.83** | **+$17.66** | **100%** | **Excellent** |
| **>30min** | **4** | **+$5.30** | **+$21.18** | **50%** | **Positif** |

**Les trades de moins de 5 minutes perdent de l'argent. Les trades de plus de 5 minutes en gagnent.** C'est le signal le plus clair de l'audit.

### 3.5 Analyse des frais (EXPERIMENTAL)

| Metrique | Valeur |
|----------|--------|
| PnL brut total | -$25.87 |
| Frais totaux | **$442.32** |
| PnL net total | -$468.22 |
| **Ratio frais / \|brut\|** | **17.1x** |
| Frais moyen/trade | $9.62 |
| Frais min | $1.28 (position $413) |
| Frais max | $23.25 (position $7,500 a x3) |

Les frais representent **17 fois** la perte brute. Le moteur n'est pas mauvais en termes de direction — sa perte brute est de seulement $26. Mais chaque trade coute $9.62 en frais, ce qui detruit toute performance.

### 3.6 Analyse par type de sortie (EXPERIMENTAL)

| Type de sortie | Trades | Gross PnL | Frais | Net PnL | Analyse |
|----------------|--------|-----------|-------|---------|---------|
| breakeven | 18 | +$55.98 | $167.82 | **-$111.85** | Trades GAGNANTS en brut mais tues par frais |
| micro_sl | 14 | -$98.05 | $137.38 | **-$235.45** | Pertes amplifiees par les frais |
| trailing_stop | 6 | +$36.08 | $81.37 | **-$45.29** | Seul type avec du brut positif significatif |
| signal | 5 | -$3.24 | $32.57 | **-$35.81** | Sorties neutres + frais |
| sl | 3 | -$16.64 | $23.18 | **-$39.82** | Vraies pertes + frais |

**Probleme central du breakeven :** 18 trades ont ete fermes en "breakeven" (PnL brut > 0) mais sont TOUS en perte nette car le seuil de breakeven n'est pas assez haut pour couvrir les frais. Le breakeven EXP ferme quand `pnl <= frais (0.31%)`, mais les frais sont de 0.31%, donc il ferme a exactement $0 net = perte de $7.75.

### 3.7 Trades NET positifs (EXPERIMENTAL)

Sur 46 trades, seuls **2** sont net positifs :

| Trade | Gross | Frais | Net | Duree | Levier | Mouvement |
|-------|-------|-------|-----|-------|--------|-----------|
| #99 | +$17.27 | $11.63 | **+$5.65** | 45min | x1.5 | +0.46% |
| #74 | +$9.11 | $7.75 | **+$1.36** | 4.8min | x1 | +0.36% |

**Point commun des 2 gagnants :** mouvement > 0.36%, duree > 4 min. C'est le seuil minimum pour etre rentable.

### 3.8 Repartition par score (MAIN)

| Score | Trades | Avg PnL | Total PnL | WR |
|-------|--------|---------|-----------|-----|
| 0-30 | 8 | +$1.43 | +$11.40 | 50% |
| 30-50 | 23 | +$2.53 | +$58.14 | 65% |
| 50-70 | 633 | -$0.18 | -$112.39 | 48% |
| 70-100 | 167 | -$0.03 | -$5.83 | 51% |

Les scores 30-50 sont les plus rentables. Les scores eleves (50+) ne predisent RIEN — le win rate est quasi-aleatoire (48-51%).

---

## 4. Diagnostic des problemes

### 4.1 Probleme fondamental : le micro-scalping est economiquement non-viable

Le moteur MAIN genere **797 trades scalping** sur 4 jours (200/jour), avec une duree moyenne de **82 secondes**. Les mouvements captures sont de 0.01-0.05% — soit **6 a 30 fois moins** que le cout des frais (0.31%).

**C'est mathematiquement impossible d'etre rentable.** Meme avec un win rate de 90%, la taille des gains ($0.25-$1.25) ne peut pas compenser les frais ($7.75 par trade).

Formule : pour breakeven avec WR=90%, il faut avg_win >= frais / 0.9 = $8.61, soit un mouvement de 0.34%. Le moteur capture en moyenne 0.04%.

### 4.2 Probleme n.2 : le levier amplifie les frais

Le levier multiplie la taille effective, donc les frais :
- x1 : frais = $7.75 (0.31% de $2,500)
- x3 : frais = $23.25 (0.31% de $7,500)

Mais les gains ne sont pas amplifies proportionnellement car les sorties (micro SL, trailing) coupent trop tot. Le trade EXP #83 illustre : gross +$6.11 a x3, mais frais $23.25 = net **-$17.14**.

### 4.3 Probleme n.3 : trop de mecanismes de sortie prematuree

Le moteur a **8 mecanismes de sortie** qui se font concurrence :

1. Micro SL (0.05%) coupe apres 1-2 ticks defavorables
2. Gain erosion coupe des gains de $0.12-$0.50
3. Candle reversal sort sur un tick de couleur differente
4. Breakeven ferme des positions a +$3-7 brut (perte nette)
5. Stale exit (5 min) ne laisse pas les trades se developper
6. Signal contraire sort sur des retournements temporaires

Chaque mecanisme "protege" individuellement, mais collectivement ils empechent tout trade de se developper assez pour couvrir les frais.

### 4.4 Probleme n.4 : le tick momentum override cree du churn

Le prix BTC bouge de $5-20 entre chaque tick (5 secondes). Le `tick_momentum_override` entre LONG sur un tick vert et SHORT sur un tick rouge — c'est du trading de random walk. Sur 797 trades scalping, c'est essentiellement du bruit aleatoire avec un biais negatif (frais).

### 4.5 Probleme n.5 : les scores ne predisent rien a court terme

Les scores techniques (RSI, MACD, Bollinger sur 15m) sont calcules sur des fenetres de 3.5h (RSI14 * 15m). Utiliser ces signaux pour des trades de 82 secondes n'a aucun sens — le signal est decouple du timeframe d'execution.

---

## 5. Plan de refonte

### 5.1 Principes directeurs

1. **Pas de trade si le mouvement attendu < 2x les frais** (seuil: 0.62%)
2. **Duree minimum de trade : 5 minutes** (les trades < 5 min sont du bruit)
3. **Levier x1 par defaut** (le levier amplifie les frais sur les petits mouvements)
4. **Un seul moteur avec frais integres** (convergence main vers experimental)
5. **Moins de trades, meilleurs trades** (10-20/jour max au lieu de 200)

### 5.2 Modifications a implementer

#### A. Integrer les frais dans le moteur MAIN

Modifier `_close_position()` dans le main pour deduire les frais, exactement comme l'experimental :
- Fichier : `backend/app/services/paper_trading_service.py`
- Ajouter : `gross_pnl`, `trading_fees`, calcul net
- Les deux moteurs deviennent equivalents sur ce point

#### B. Refondre le profil scalping

Le scalping actuel (82s, 0.04% de capture) est non-viable. Transformation en **"swing court"** :

| Parametre | Avant | Apres | Raison |
|-----------|-------|-------|--------|
| `analysis_timeframe` | 15m | 15m | Inchange |
| `cooldown_minutes` | 0.5 | **5** | Reduire la frequence |
| `stale_exit_minutes` | 5 | **30** | Laisser le trade se developper |
| `stale_negative_exit_minutes` | 2 | **10** | Plus de patience sur les reculs |
| `micro_stop_loss_pct` | 0.05% | **0.20%** | Aligner sur le SL classique |
| `trailing_stop_activation_pct` | 0.04% | **0.40%** | Activer seulement quand le gain couvre les frais |
| `trailing_stop_drop_ratio` | 0.15 | **0.25** | Garder 75% du gain |
| `gain_erosion_ratio` | 0.40 | **None** (desactive) | Empeche les sorties prematurees |
| `profit_take_pct` | 0.8% | **1.5%** | TP atteignable ET rentable |
| `loss_cut_pct` | 0.20% | **0.50%** | SL plus large pour respirer |
| `candle_reversal_exit_enabled` | True | **False** | Supprime le churn |
| `tick_momentum_override_direction` | True | **False** | Le score decide la direction, pas le tick |
| `min_hold_seconds` | 30 | **300** (5min) | Duree minimum obligatoire |
| `min_score` | 30 | **40** | Plus selectif |
| `economic_gate_enabled` | True | True | Garde le gate economique |
| `expected_capture_pct` | 0.50% | **0.80%** | Alignee sur le nouveau TP |
| `min_ev_multiple` | 1.5 | **2.0** | Plus exigeant |

#### C. Refondre le profil aggressive

| Parametre | Avant | Apres | Raison |
|-----------|-------|-------|--------|
| `cooldown_minutes` | 5 | **15** | Reduire la frequence |
| `micro_stop_loss_pct` | 0.15% | **0.30%** | Plus de respiration |
| `trailing_stop_activation_pct` | 0.25% | **0.50%** | Au-dessus des frais |
| `gain_erosion_ratio` | 0.70 | **None** (desactive) | Sorties prematurees |
| `min_score` | 10 | **20** | Plus selectif |
| `economic_gate_enabled` | False | **True** | Obligatoire avec frais |
| `expected_capture_pct` | — | **0.80%** | |
| `min_ev_multiple` | — | **2.0** | |

#### D. Filtre pre-trade economique universel

Ajouter dans `_tick_single_slot()`, avant l'ouverture de toute position :

```python
# Simulation pre-trade : rejeter si pas rentable apres frais
cost_model = get_cost_model("realistic")
effective_size = position_size * leverage
rt_cost = cost_model.round_trip_cost_usd(effective_size)
expected_capture = effective_size * profile_params.profit_take_pct / 100
if expected_capture < rt_cost * 2:
    reject("TP ${expected_capture} < 2x frais ${rt_cost * 2}")
```

#### E. Convergence des 2 moteurs

A terme, le main et l'experimental doivent converger vers une logique unique. La premiere etape est d'integrer les frais dans le main. La deuxieme est d'aligner les profils.

### 5.3 Resultats attendus

Avec les nouvelles regles :
- **Frequence estimee** : 10-20 trades/jour (au lieu de 200)
- **Duree moyenne estimee** : 15-60 min (au lieu de 82s)
- **Mouvement moyen capture** : 0.3-1.0% (au lieu de 0.04%)
- **Frais par trade** : $7.75 (x1) — representant 5-25% du gain au lieu de 600%
- **Win rate necessaire pour breakeven** : ~55% (au lieu de 99%+ actuellement)

---

## 6. Historique des corrections

### v2.0.30 — 18 avril 2026 — Gates statistiques

**Contexte :** Audit statistique approfondi des 2 journaux (831 + 46 trades) avec corrélations Pearson,
distributions, heatmaps score×duree, et identification de 13 insights non triviaux.

**Modifications livrées :**
- [x] `blocked_hours_utc=[13,14,15,16]` sur scalping + aggressive (audit : -$104 cum sur ces 3h)
- [x] `max_score=50` (scalping) / `55` (aggressive) — corrélation r=-0.134 p=0.0001 significative
- [x] `min_range_atr=1.5` — rejette chop ranges (amplitude insuffisante pour couvrir 2× frais)
- [x] `breakeven_min_peak_fee_multiple=2.0` — empêche fermetures breakeven à net nul (18 trades EXP, -$111)
- [x] `micro_stop_loss_pct=None` sur scalping — désactive 184 coupures destructrices (-$364 cum)
- [x] `min_volume_ratio=0.8` aggressive (aligné scalping) — volume faible = chop à venir
- [x] Tests : 1773 passed / 35 failed (baseline préservée, aucune régression nouvelle)

**Metriques de succes attendues (à valider en Session 4 sur 7j laptop perso) :**
- PnL net positif sur 7j de trading
- 10-20 trades/jour scalping (au lieu de 200)
- Moins de 20 trades/jour aggressive
- WR net > 50% (au lieu de 4% sur EXP / 48% sur MAIN)
- Durée moyenne > 5 min (au lieu de 82s)
- Aucun trade ouvert entre 13-16h UTC
- Aucun trade ouvert avec |score| > 50 (scalping) / 55 (aggressive)

### v2.0.29-fees — 17 avril 2026 (PLANIFIE)

**Objectif :** Rendre le moteur MAIN realiste et viable economiquement.

**Modifications prevues :**
- [ ] Integration des frais dans `_close_position()` (main)
- [ ] Refonte profil scalping (swing court)
- [ ] Refonte profil aggressive (gate economique)
- [ ] Filtre pre-trade economique universel
- [ ] Desactivation candle reversal + tick override direction
- [ ] Tests (1808+ doivent passer)
- [ ] Reset des comptes paper trading pour clean start

**Metriques de succes :**
- PnL net positif sur 48h de trading
- Moins de 30 trades par jour
- Win rate > 50% NET (apres frais)
- Avg duration > 5 min
- Aucun trade avec mouvement < 0.31%

---

*Document cree le 17 avril 2026. Sera mis a jour apres chaque iteration de correction.*
