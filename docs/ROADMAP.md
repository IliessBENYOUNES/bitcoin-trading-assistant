# Roadmap Projet — De BTC Insight à INFINI

**Document de référence — Version 1.0**
**Date de rédaction : 1er avril 2026**
**Auteur : Équipe projet BTC Insight / INFINI**

---

## Table des matières

1. [Introduction stratégique](#1-introduction-stratégique)
2. [État des lieux du projet](#2-état-des-lieux-du-projet)
3. [Cartographie fonctionnelle](#3-cartographie-fonctionnelle)
4. [Niveaux de maturité produit](#4-niveaux-de-maturité-produit)
5. [Roadmap détaillée par phases](#5-roadmap-détaillée-par-phases)
6. [Priorisation argumentée](#6-priorisation-argumentée)
7. [UX, accessibilité et pédagogie](#7-ux-accessibilité-et-pédagogie)
8. [Risques et garde-fous](#8-risques-et-garde-fous)
9. [Conclusion opérationnelle](#9-conclusion-opérationnelle)

---

## Avancement global

```
┌─────────────────────────────────────────────────────────────────────┐
│  ÉTAPE 1 — BTC Insight (v0.2 → v0.9) ✅ COMPLET                    │
│  Assistant visuel, modulaire, pédagogique                           │
│  ├── Données marché temps réel          ✅ Livré (v0.2-v0.6)       │
│  ├── Indicateurs techniques             ✅ Livré (v0.3)            │
│  ├── Signaux & scoring                  ✅ Livré (v0.7)            │
│  ├── Alertes visuelles                  ✅ Livré (v0.8)            │
│  └── News & sentiment                   ✅ Livré (v0.9)            │
│                                                                      │
│  ÉTAPE 2 — INFINI v1 (v1.0 → v1.7) ✅ COMPLET                        │
│  Assistant intelligent, décisionnel                                  │
│  ├── Moteur de décision / règles        ✅ Livré (v1.0)             │
│  ├── Backtesting engine                 ✅ Livré (v1.1)             │
│  ├── Vérification historique            ✅ Livré (v1.1.1)           │
│  ├── Sentiment historique + ML          ✅ Livré (v1.2.1-1.2.4)    │
│  ├── Risk management engine             ✅ Livré (v1.3)             │
│  ├── Paper trading                      ✅ Livré (v1.4)             │
│  ├── Journal + Profils + Levier + Style ✅ Livré (v1.5)             │
│  ├── Diagnostic + Scalping + Sorties    ✅ Livré (v1.6)             │
│  └── Multi-slot + Mean reversion        ✅ Livré (v1.7)             │
│                                                                      │
│  ÉTAPE 2b — Reality Gap Closure (v1.8-v1.9) ✅ COMPLET                │
│  Validation opérationnelle avant exécution réelle                    │
│  ├── TradingCostModel (frais/spread/slip) ✅ Livré (v1.8.1)         │
│  ├── PaperRun (campagnes de validation)   ✅ Livré (v1.9.0)         │
│  ├── TruthAudit (audit métriques)         ✅ Livré (v1.8.3)         │
│  ├── V2Gate (gate formelle v2.0)          ✅ Livré (v1.8.4)         │
│  ├── SmartCooldown + Learning Layer       ✅ Livré (v1.9.0)         │
│  ├── Anti-micro-PnL + Valeur économique   ✅ Livré (v1.9.1)         │
│  ├── Short Optimization + Valeur/trade    ✅ Livré (v1.9.3)         │
│  └── Correction surcorrection short       ✅ Livré (v1.9.4)         │
│                                                                      │
│  ÉTAPE 3 — INFINI v2 (v2.0+) ⛔ BLOQUÉ PAR 2b                     │
│  Assistant autonome (sous contrôle humain)                           │
│  ├── Exécution automatisée              ⬜ Futur                    │
│  ├── Mode fantôme (observer sans agir)  ⬜ Futur                    │
│  ├── Apprentissage de stratégies        ⬜ Futur                    │
│  └── Kill switch & audit trail          ⬜ Futur                    │
│                                                                      │
│  ÉTAPE 4 — INFINI v3 (v3.0+) 🧠 PROJET ML CONVERGENT              │
│  Modèle intelligent unifié : Technique + Sentiment + Apprentissage   │
│  ├── Dataset unifié historique           ⬜ Futur (v3.0)            │
│  ├── Feature engineering multi-sources   ⬜ Futur (v3.0)            │
│  ├── Modèle ML prédictif (prix)         ⬜ Futur (v3.1)            │
│  ├── Modèle NLP sentiment (news)        ⬜ Futur (v3.1)            │
│  ├── Modèle convergent (fusion)         ⬜ Futur (v3.2)            │
│  ├── Online learning (amélioration)     ⬜ Futur (v3.3)            │
│  └── Évaluation & monitoring ML         ⬜ Futur (v3.3)            │
└─────────────────────────────────────────────────────────────────────┘
```

### État actuel : v1.7.2 livré — Reality gap closure (v1.8) en cours

> ⚠️ **L'Étape 2 est fonctionnellement livrée mais la validation opérationnelle manque.**
> Le passage v2.0 est bloqué tant que le reality gap (coûts, campagnes, audit, gate) n'est pas comblé.

| Composant | Status |
|-----------|--------|
| Backend dual-jobs scheduler | ✅ Complet |
| 14 timeframes (1m → 1w) | ✅ Complet |
| Resample multi-timeframe | ✅ Complet |
| Frontend Dashboard | ✅ Complet |
| Indicateurs (RSI, MACD, SMA, Bollinger, ADX, Volume) | ✅ Complet |
| Chart Lightweight Charts | ✅ Complet |
| Signal Engine (interprétation + score) | ✅ Complet (v0.7) |
| SignalPanel (jauge + liste + consensus) | ✅ Complet (v0.7) |
| Alert System (CRUD + check + notifications) | ✅ Complet (v0.8) |
| AlertPanel (formulaire + liste + polling) | ✅ Complet (v0.8) |
| News Service (RSS + sentiment + impact) | ✅ Complet (v0.9) |
| NewsPanel (jauge + articles + filtres) | ✅ Complet (v0.9) |
| **Decision Engine (règles + scénarios + recommandation)** | **✅ Complet (v1.0)** |
| **DecisionPanel (jauge + scénarios + recommandation)** | **✅ Complet (v1.0)** |
| **Backtesting (replay + métriques + equity curve)** | **✅ Complet (v1.1)** |
| **BacktestPanel (config + métriques + journal trades)** | **✅ Complet (v1.1)** |
| **Vérification historique (time-travel + walk-forward)** | **✅ Complet (v1.1.1)** |
| **VerificationPanel (charger historique + vérifier + walk-forward)** | **✅ Complet (v1.1.1)** |
| **Intégrité données (complétude, gaps, grade qualité)** | **✅ Complet (v1.2.2)** |
| **Mode comparaison walk-forward (technique vs technique+sentiment)** | **✅ Complet (v1.2.2)** |
| **Persistance news RSS en DB (modèle + service + endpoints + 33 tests)** | **✅ Complet (v1.2.3a)** |
| **Risk Management Engine (SL/TP, daily loss, kill switch, position sizing)** | **✅ Complet (v1.3)** |
| **RiskPanel (dashboard risque, kill switch, config, perte journalière)** | **✅ Complet (v1.3)** |
| **Paper Trading System (tick engine, SL/TP, métriques, journal, scheduler)** | **✅ Complet (v1.4)** |
| **PaperTradingPanel (statut, tick manuel, positions, métriques)** | **✅ Complet (v1.4)** |
| **Journal d'évaluation multi-jours (synthèse, journalier, activité, raisons)** | **✅ Complet (v1.5)** |
| **Profils de trading (Conservative/Balanced/Aggressive/Scalping + Auto)** | **✅ Complet (v1.5 + v1.5.1)** |
| **Levier auto intelligent (score × confiance × volatilité, veto risk)** | **✅ Complet (v1.5)** |
| **Style de trading (distribution durées, scalping/intraday/swing)** | **✅ Complet (v1.5)** |
| **JournalPanel (5 sous-vues, profils, KPIs, barres de distribution)** | **✅ Complet (v1.5)** |
| **Diagnostic fréquence (causes non-trade, comparaison profils, opportunities)** | **✅ Complet (v1.6)** |
| **DiagnosticPanel (raisons, durée positions, levier, recommandations)** | **✅ Complet (v1.6)** |
| **Multi-slot positions parallèles (trend + scalping simultanés)** | **✅ Complet (v1.7)** |
| **Mean reversion bidirectionnel (SHORT surachat, LONG survente)** | **✅ Complet (v1.7)** |
| **Per-slot cooldown + daily trade counter indépendants** | **✅ Complet (v1.7.1)** |
| 1005 tests backend | ✅ Tous passing |

### ✅ LIVRÉ : v0.7 — Moteur de Signaux (Niveau 2)

> Le système interprète les indicateurs et génère des signaux structurés.

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 7.1 `signal_service.py` | 🔴 Haute | 4h | Interpréter RSI/MACD/SMA/Bollinger → signaux structurés | ✅ |
| 7.2 Schéma `SignalResponse` | 🔴 Haute | 1h | SignalItem, CompositeScore, consensus | ✅ |
| 7.3 `GET /market/signals` | 🔴 Haute | 2h | Endpoint API retournant signaux + score | ✅ |
| 7.4 Score composite | 🔴 Haute | 3h | Agrégation -100/+100, confiance, convergence | ✅ |
| 7.5 `test_signals.py` | 🔴 Haute | 4h | Tests unitaires pour chaque interpréteur (52 tests) | ✅ |
| 7.6 `SignalPanel.tsx` | 🟡 Moyenne | 4h | Jauge, liste signaux, badge consensus | ✅ |
| 7.7 Hook `useSignals.ts` | 🟡 Moyenne | 1h | Fetch + types TypeScript | ✅ |

### ✅ LIVRÉ : v0.8 — Alertes & Notifications

> Le système passe de "interpréter" à "alerter proactivement".

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 8.1 Modèle Alert en DB | 🔴 Haute | 2h | SQLAlchemy: seuils prix, RSI, MACD, signaux | ✅ |
| 8.2 API CRUD `/alerts` | 🔴 Haute | 3h | GET/POST/PUT/DELETE + check + notifications | ✅ |
| 8.3 Service AlertChecker | 🔴 Haute | 4h | Évaluation conditions vs données marché | ✅ |
| 8.4 UI AlertPanel | 🟡 Moyenne | 4h | Formulaire + liste alertes actives + notifications | ✅ |
| 8.5 Polling notifications | 🟡 Moyenne | 2h | Polling automatique toutes les 60s | ✅ |
| 8.6 48 tests backend | 🔴 Haute | 3h | CRUD, évaluation, récurrence, endpoints | ✅ |

### ✅ LIVRÉ : v0.9 — News & Sentiment

> Le système passe de "alerter" à "comprendre le contexte".

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 9.1 Collecteur RSS | 🔴 Haute | 4h | CoinTelegraph, CoinDesk, Bitcoin Magazine | ✅ |
| 9.2 Classification sentiment | 🔴 Haute | 4h | Keyword-based (bullish/bearish/neutral) | ✅ |
| 9.3 Score d'impact | 🟡 Moyenne | 2h | HIGH/MEDIUM/LOW basé sur mots-clés | ✅ |
| 9.4 Score global sentiment | 🟡 Moyenne | 2h | Agrégation pondérée -100/+100 | ✅ |
| 9.5 API /news endpoints | 🔴 Haute | 2h | GET /news + GET /news/sentiment | ✅ |
| 9.6 43 tests backend | 🔴 Haute | 3h | Sentiment, impact, RSS, résilience, endpoints | ✅ |
| 9.7 NewsPanel UI | 🟡 Moyenne | 4h | Jauge sentiment, articles, filtres, liens | ✅ |
| 9.8 Cache + résilience | 🟡 Moyenne | 1h | TTL 5min, timeout 10s, fallback | ✅ |

### ✅ LIVRÉ : v1.0 — Moteur de Décision (INFINI v1)

> Le système passe de "informer" à "recommander" avec des scénarios et des explications.

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 10.1 Moteur de règles | 🔴 Haute | 8h | 8 règles combinées (RSI, MACD, SMA, sentiment) | ✅ |
| 10.2 Scénarios multi-outcome | 🔴 Haute | 6h | Hausse/Stable/Baisse, probabilités normalisées | ✅ |
| 10.3 Recommandations explicables | 🔴 Haute | 4h | Acheter/Vendre/Attendre + raisons en français | ✅ |
| 10.4 API `/market/decision` | 🔴 Haute | 3h | Endpoint structuré avec mode dégradé | ✅ |
| 10.5 UI DecisionPanel | 🟡 Moyenne | 6h | Jauge combinée, barres scénarios, card recommandation | ✅ |
| 10.6 75 tests backend | 🔴 Haute | 4h | Règles, scénarios, recommandation, intégration, endpoint | ✅ |

### ✅ LIVRÉ : v1.1 — Backtesting / Simulation

> Le système peut rejouer les décisions sur l'historique et mesurer la performance.

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 11.1 Engine backtest | 🔴 Haute | 8h | Replay candle par candle avec signaux/décisions | ✅ |
| 11.2 Simulation positions | 🔴 Haute | 4h | Achat/vente simulés selon action du moteur | ✅ |
| 11.3 Métriques performance | 🔴 Haute | 4h | Win rate, Sharpe, drawdown, profit factor | ✅ |
| 11.4 Buy & Hold benchmark | 🟡 Moyenne | 2h | Comparaison avec stratégie passive | ✅ |
| 11.5 Warning suroptimisation | 🟡 Moyenne | 2h | Alerte si <10 trades ou Sharpe >3.0 | ✅ |
| 11.6 UI BacktestPanel | 🟡 Moyenne | 6h | Config + métriques + journal trades | ✅ |
| 11.7 31 tests backend | 🔴 Haute | 3h | Replay, métriques, benchmark, overfitting, endpoint | ✅ |

### ✅ LIVRÉ : v1.1.1 — Vérification Historique (Time-Travel Backtest)

> Le système peut se positionner à n'importe quelle date depuis 2017 et comparer ses prédictions avec la réalité.

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 11.8 Chargement historique profond | 🔴 Haute | 4h | Binance 2017→maintenant, pagination, upsert idempotent | ✅ |
| 11.9 Service de vérification | 🔴 Haute | 6h | verify_at_date + walk-forward + comparaison prédiction/réalité | ✅ |
| 11.10 Endpoints API | 🔴 Haute | 3h | /history/load, /history/range, /verify, /walk-forward | ✅ |
| 11.11 VerificationPanel UI | 🟡 Moyenne | 6h | Charger historique, date picker, résultats ✅/❌, walk-forward | ✅ |
| 11.12 33 tests backend | 🔴 Haute | 3h | Range, verify, walk-forward, correctness, endpoints, mock loader | ✅ |

**Livrable v1.1.1 :**
> ✅ L'utilisateur charge l'historique BTC depuis 2017, choisit une date (ex: 1er janvier 2020), voit la recommandation du modèle (ACHETER score +42), puis compare avec la réalité (+15.3% à 30j → ✅ CORRECT). Le walk-forward teste automatiquement sur des dizaines de dates pour donner un taux de précision global.

> ⚠️ **Limitation** : Le sentiment (news) n'est pas disponible en historique — le modèle fonctionne en mode 100% technique. La phase v1.2 (Sentiment Historique) comblera cette lacune.

### Phase v1.2 — Sentiment Historique + Modèle d'Apprentissage 🧠

> **Objectif** : Donner au modèle une mémoire complète — technique ET contextuelle — pour que le backtest historique et le moteur de décision aient accès au sentiment réel de chaque époque.
>
> ⚠️ **Changement de priorité** : Le multi-assets (ETH, SOL...) a été déplacé en v1.6. On perfectionne d'abord tout sur BTC — si le modèle fonctionne bien sur BTC, on l'étend ensuite aux autres actifs.

**Pourquoi c'est important** : Le moteur de décision actuel utilise 70% technique + 30% sentiment. Mais en backtest historique, le sentiment n'est pas disponible → le modèle fonctionne à 100% technique. Pour valider la qualité réelle du modèle complet, il faut reconstituer le sentiment historique.

**Ce que ça changerait** :
- Le walk-forward testerait le modèle COMPLET (technique + sentiment), pas juste la partie technique
- Le robot futur prendrait des décisions basées sur l'historique complet
- Le modèle pourrait apprendre quels types de news impactent vraiment le prix

#### Catalogue complet des sources de données historiques

##### 1. Sources gratuites

| Source | Type | Couverture historique | Rate Limit | Données fournies | Qualité sentiment |
|--------|------|----------------------|------------|------------------|-------------------|
| **Alternative.me Fear & Greed** | Index agrégé | **Depuis fév. 2018** (~2900 jours) | Illimité | 1 score 0-100/jour (peur→avidité) | ⭐⭐⭐ Bon résumé quotidien |
| **GDELT Project** | News mondiales brutes | **Depuis 1979** | Illimité | Articles complets, 100+ langues, géolocalisation | ⭐ Brut — nécessite NLP maison |
| **CoinDesk/CoinTelegraph RSS** | News crypto temps réel | **Aucun historique** (temps réel uniquement) | Illimité | Titres + résumés | ⭐⭐ C'est ce qu'on utilise déjà |
| **Reddit API** (free tier) | Sentiment social | **~2 ans** via Pushshift | 60 req/min | Posts + commentaires r/Bitcoin, r/CryptoCurrency | ⭐⭐ Bruyant mais volumétrique |
| **CryptoCompare** (free tier) | News crypto agrégées | **Depuis 2015** | 100k req/mois | Titres, catégories, source, pas de sentiment pré-calculé | ⭐⭐ Bon historique gratuit |

##### 2. Sources payantes — Tableau comparatif détaillé avec tarifs

| Source | Plan | Prix mensuel | Prix annuel | Historique | Ce qu'on obtient | ROI pour notre projet |
|--------|------|-------------|-------------|------------|------------------|----------------------|
| **CryptoPanic** | Free | **0 €** | 0 € | ~2014→now | 200 req/h, titres + source + URL, filtres basiques | ⭐⭐ Suffisant pour lister les news |
| **CryptoPanic** | **Pro** | **$49/mois** (~45 €) | ~540 €/an | ~2014→now | Filtres avancés, votes communauté (bullish/bearish), sentiment pré-calculé, webhooks, 2000 req/h | ⭐⭐⭐⭐ **Meilleur rapport qualité/prix** |
| **CryptoPanic** | Enterprise | Sur devis (~$200+) | — | ~2014→now | Volume illimité, support dédié, bulk export | Overkill pour nous |
| | | | | | | |
| **Santiment** | Free | **0 €** | 0 € | Depuis 2016 | 1000 API credits/mois, données limitées, ~20 métriques | ⭐⭐ Tester le concept |
| **Santiment** | **Pro** | **$49/mois** (~45 €) | ~540 €/an | Depuis 2016 | 200k credits/mois, sentiment social (Twitter/Reddit/Telegram), on-chain, dev activity, 200+ métriques | ⭐⭐⭐⭐ **Excellent pour le social** |
| **Santiment** | **Pro+** | **$250/mois** (~230 €) | ~2760 €/an | Depuis 2016 | Illimité, données en temps réel, alertes custom, 800+ métriques, accès API complet | ⭐⭐⭐ Si on scale |
| **Santiment** | Enterprise | **$1000+/mois** | — | Depuis 2016 | White-label, support dédié, SLA | Overkill |
| | | | | | | |
| **NewsAPI.org** | Free | **0 €** | 0 € | **1 mois seulement** | 100 req/jour, 80k sources, pas d'historique profond | ❌ Inutile pour l'historique |
| **NewsAPI.org** | Developer | **$149/mois** (~137 €) | ~1640 €/an | **1 an** | 1000 req/jour, pas de restrictions commerciales | ⭐⭐ Cher pour ce que c'est |
| **NewsAPI.org** | **Business** | **$449/mois** (~415 €) | ~4980 €/an | **5 ans** | Illimité, historique profond, SLA | ⭐⭐ Pas spécialisé crypto |
| | | | | | | |
| **LunarCrush** | Free | **0 €** | 0 € | ~2019→now | Limité, social metrics basiques | ⭐⭐ Pour tester |
| **LunarCrush** | **Pro** | **$15/mois** (~14 €) | ~168 €/an | ~2019→now | Galaxy Score, AltRank, social volume, influenceurs, 24h historique détaillé | ⭐⭐⭐ **Le moins cher** |
| **LunarCrush** | Pro+ | **$49/mois** (~45 €) | ~540 €/an | ~2019→now | Historique complet, alertes, exports, API illimitée | ⭐⭐⭐ Si besoin de profondeur |
| | | | | | | |
| **The Tie** | Terminal | **$1000+/mois** (~920 €) | ~12000 €/an | Depuis 2017 | Sentiment NLP pro, 850+ tokens, Twitter/Reddit/news, données minute par minute | ⭐⭐⭐⭐⭐ Pro mais hors budget |
| | | | | | | |
| **CryptoCompare** | Free | **0 €** | 0 € | Depuis 2015 | 100k req/mois, news + prix + social, historique partiel | ⭐⭐⭐ Bon gratuit |
| **CryptoCompare** | **Starter** | **$79/mois** (~73 €) | ~876 €/an | Depuis 2015 | 500k req/mois, news complètes, order book, historical OHLCV | ⭐⭐⭐ Polyvalent |
| **CryptoCompare** | Pro | **$150/mois** (~138 €) | ~1656 €/an | Depuis 2015 | 2.5M req/mois, données temps réel, tick data | ⭐⭐⭐ Si besoin temps réel |
| | | | | | | |
| **Messari** | Free | **0 €** | 0 € | ~2017→now | Profils tokens, métriques basiques, quelques news | ⭐ Limité |
| **Messari** | **Pro** | **$29.99/mois** (~28 €) | ~336 €/an | ~2017→now | Recherche complète, screeners, watchlists, Intel (news pro), charts avancés | ⭐⭐⭐ Bon contenu éditorial |
| **Messari** | Enterprise | Sur devis | — | ~2017→now | API données, indices, rapports sur mesure | Overkill |
| | | | | | | |
| **IntoTheBlock** | Free | **0 €** | 0 € | Depuis 2018 | Métriques on-chain basiques | ⭐ Limité |
| **IntoTheBlock** | **Standard** | **$10/mois** (~9 €) | ~108 €/an | Depuis 2018 | On-chain analytics, whale alerts, sentiment social, DeFi analytics | ⭐⭐⭐ **Très abordable** |
| **IntoTheBlock** | Pro | **$50/mois** (~46 €) | ~552 €/an | Depuis 2018 | Tout Standard + signaux avancés, API complète, exports | ⭐⭐⭐ Si besoin on-chain |
| | | | | | | |
| **Token Metrics** | Basic | **$49/mois** (~45 €) | ~540 €/an | ~2018→now | Ratings AI par token, signaux daily, portfolios modèles | ⭐⭐ Focus investissement |
| **Token Metrics** | Premium | **$149/mois** (~137 €) | ~1656 €/an | ~2018→now | Ratings + prédictions prix AI, backtesting intégré, alertes trader | ⭐⭐⭐ Concurrent direct |
| **Token Metrics** | VIP | **$399/mois** (~368 €) | ~4380 €/an | ~2018→now | Tout + indices quant, signaux intraday, support prioritaire | Cher |

##### 3. Résumé des coûts par scénario

| Scénario | Sources combinées | Coût mensuel | Coût annuel | Couverture |
|----------|-------------------|-------------|-------------|------------|
| **🆓 Gratuit** | Fear & Greed + GDELT + CryptoCompare free + Reddit | **0 €** | **0 €** | 2018→now (sentiment basique) |
| **💰 Budget serré** | Gratuit + LunarCrush Pro + IntoTheBlock Standard | **~25 €/mois** | **~276 €/an** | 2018→now (social + on-chain) |
| **💰💰 Recommandé** | Gratuit + CryptoPanic Pro + Santiment Pro | **~100 €/mois** | **~1080 €/an** | 2014→now (news + social + sentiment) |
| **💰💰💰 Complet** | Recommandé + CryptoCompare Starter + Messari Pro | **~207 €/mois** | **~2292 €/an** | 2014→now (tout sauf The Tie) |
| **🏦 Institutionnel** | Tout + The Tie Terminal | **~1200+ €/mois** | **~14000+ €/an** | 2014→now (données pro minute par minute) |

#### Réponse complète : "On peut remonter jusqu'à la naissance du BTC ?"

##### Analyse par période — Prix ET Sentiment

| Période | Données prix disponibles | Données news/sentiment disponibles | Sources utilisables | Verdict |
|---------|------------------------|------------------------------------|---------------------|---------|
| **2009–2010** | ❌ Quasi rien (BTC < $1, échanges informels) | ❌ Aucune source structurée. Forums BitcoinTalk uniquement | Aucune API | 🚫 **Inexploitable** — BTC n'avait pas de marché |
| **2011–2013** | ⚠️ Partielles : Mt.Gox (fermé), CoinGecko daily depuis 2013 | ❌ Pas de news crypto structurées. Reddit r/Bitcoin existait (2011) mais données perdues | GDELT (général), Reddit archives (Pushshift) | 🚫 **Trop fragmenté** — Pas assez de données pour un modèle |
| **2014–2015** | ✅ CoinGecko daily complet | ⚠️ CryptoPanic existe (~2014) mais peu de news. GDELT a des articles sur Mt.Gox hack | CryptoPanic free, GDELT, CryptoCompare (2015) | ⚠️ **Partiel** — Quelques centaines de news/an, sentiment très bruité |
| **2016–2017** | ✅ CoinGecko + premiers exchanges majeurs | ⚠️ CryptoPanic mieux fourni, Santiment démarre (2016), ICO mania = beaucoup de bruit | CryptoPanic, Santiment, CryptoCompare | ⚠️ **Utilisable avec précautions** — Sentiment dominé par les ICOs, pas représentatif du marché actuel |
| **2018 (jan)** | ✅ Binance complet (toutes granularités) | ✅ Fear & Greed démarre (fév. 2018), Santiment complet, CryptoPanic mature | Toutes les sources | ✅ **Début de la zone fiable** |
| **2018–2020** | ✅ Binance complet | ✅ Fear & Greed ✅ CryptoPanic ✅ Santiment ⚠️ LunarCrush (2019) | Toutes sauf LunarCrush avant 2019 | ✅ **Zone idéale** — Inclut bear market 2018, halving 2020 |
| **2021–2023** | ✅ Binance complet | ✅ TOUTES les sources disponibles | Toutes | ✅ **Zone parfaite** — Bull run, crash Terra/Luna, FTX, bear market |
| **2024–2026** | ✅ Binance complet | ✅ TOUTES les sources + ETF Bitcoin spot approuvés | Toutes | ✅ **Zone la plus riche** — Marché mature, données abondantes |

##### Les trous dans la raquette — Analyse honnête

Même avec les meilleures API payantes, voici ce qu'on **ne pourra PAS** récupérer :

| Trou | Détail | Impact | Contournement possible |
|------|--------|--------|----------------------|
| **2009–2013 : néant** | Aucune API n'a de données de sentiment crypto avant 2014. Le marché n'existait pas en tant que tel. | ❌ Nul — Ces années sont inexploitables pour le ML | Accepter : le modèle commence en 2014 au mieux, 2018 idéalement |
| **Texte complet des articles** | CryptoPanic et la plupart des agrégateurs ne fournissent que les **titres** + métadonnées, pas le texte complet des articles | ⚠️ Modéré — Le titre contient ~70% du signal pour le NLP | Utiliser GDELT pour le texte complet (quand disponible) ou scraper les archives des sites |
| **Sentiment intraday avant 2018** | Avant 2018, on n'a qu'un sentiment **quotidien** au mieux. Pas de granularité horaire/minute | ⚠️ Modéré — Suffisant pour les timeframes 4h et 1d, pas pour le scalping | Le trading intraday sur données anciennes n'est pas fiable de toute façon |
| **Sentiment social pré-2016** | Twitter crypto, Reddit crypto avant 2016 = très peu de volume. Pas de données structurées | ⚠️ Faible — Le social n'était pas un driver majeur du prix avant 2017 | Ignorer le social avant 2016, se concentrer sur les news |
| **News supprimées / éditées** | Certains articles ont été retirés, modifiés, ou les sites ont fermé (ex: ICO blogs 2017) | ⚠️ Faible — Affecte surtout la période ICO 2017 | GDELT et Internet Archive (Wayback Machine) conservent des copies |
| **Manipulation médiatique** | Impossible de distinguer les news organiques des news sponsorisées/manipulées (surtout 2017-2018 ICO era) | ⚠️ Modéré — Le modèle ML pourrait apprendre ces patterns | Pondérer par source (CoinDesk > blog random), le ML peut filtrer |
| **Données on-chain historiques** | Les données on-chain complètes (whale movements, exchange flows) ne sont structurées que depuis ~2018 | ⚠️ Faible pour le sentiment, important pour un modèle avancé | IntoTheBlock / Santiment depuis 2018 |
| **Langues non-anglaises** | La plupart des API ne couvrent que les news en anglais. Le sentiment chinois/coréen (gros marchés crypto) est absent | ⚠️ Modéré — Les marchés asiatiques influencent beaucoup le BTC | GDELT couvre le multilingue, mais c'est du NLP avancé |

##### Conclusion réaliste

> **Réponse courte** : Non, on ne peut PAS remonter jusqu'à la naissance du BTC (2009) avec des données de sentiment fiables. Mais on peut couvrir **2018→2026 (8 ans)** avec une qualité excellente, et **2014→2017 (4 ans supplémentaires)** avec une qualité correcte mais partielle.

> **Est-ce un problème ?** Non. Les 8 ans 2018-2026 couvrent : un bear market brutal (2018), un halving (2020), un bull run historique (2021), un crash systémique (Terra/Luna + FTX 2022), un bear prolongé (2022-2023), un halving + ETF spot (2024), et un nouveau cycle (2025-2026). C'est **amplement suffisant** pour entraîner un modèle ML robuste. Le BTC pré-2018 était un marché fondamentalement différent (pas d'institutions, pas d'ETF, manipulation massive, volumes faibles).

> **Le vrai enjeu n'est pas la couverture temporelle, c'est la qualité du feature engineering** : comment combiner Fear & Greed + news titres + sentiment social + on-chain en features exploitables par le ML.

#### Stratégie recommandée (3 paliers progressifs)

**Palier 1 — Gratuit (v1.2a) : Fear & Greed + CryptoCompare News**
- Intégrer l'**index Fear & Greed** d'Alternative.me (gratuit, 1 valeur/jour depuis février 2018)
- C'est un score 0-100 qui résume le sentiment global du marché BTC
- Ajouter les **news historiques CryptoCompare** (gratuit, depuis 2015, titres + catégories)
- Suffit déjà pour enrichir le backtest historique avec un "mood" quotidien
- Charger tout l'historique en une requête (~2900 points Fear & Greed)
- Effort : **6-8h** | Coût : **0 €**

**Palier 2 — Budget modéré (v1.2b) : CryptoPanic Pro + Santiment Pro**
- **CryptoPanic Pro** ($49/mois) pour les news crypto historiques avec votes/sentiment communauté
  - ~10 ans d'historique (2014→now)
  - Votes bullish/bearish de la communauté = sentiment crowd-sourcé
  - 2000 req/h = possibilité de charger tout l'historique en quelques heures
- **Santiment Pro** ($49/mois) pour le sentiment social (Twitter/Reddit/Telegram mentions)
  - Social volume, social dominance, sentiment weighted
  - 200+ métriques on-chain et social depuis 2016
- Stocker les news en base avec leur sentiment pré-calculé
- Le moteur de décision utilise : sentiment social + technique + Fear & Greed + news sentiment
- Effort : **15-20h** | Coût : **~100 €/mois (~1080 €/an)**

**Palier 3 — Modèle ML maison (v1.2c) : Apprentissage sur l'historique complet**
- Entraîner un modèle de classification de sentiment sur les news crypto
- Le modèle apprend quels mots/phrases/patterns prédisent des mouvements de prix
- Utiliser l'historique GDELT (gratuit) + CryptoCompare + CryptoPanic comme données d'entraînement
- Le modèle s'améliore au fil du temps avec les nouvelles données (online learning)
- C'est le "package complet" : technique + sentiment + apprentissage
- Effort : **40-80h** | Coût : **0 € (GDELT) ou ~100 €/mois (données enrichies)**
- ⚠️ **C'est un projet en soi** — voir Phase v3.0 ci-dessous pour la vision complète

#### Tâches détaillées

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 12.1 Modèle SentimentHistory en DB | 🔴 Haute | 3h | Table pour stocker sentiment quotidien historique (date, score, source, raw_data JSON) |
| 12.2 Client Fear & Greed API | 🔴 Haute | 2h | Fetch + stockage index 0-100 depuis fév. 2018 (~2900 jours) |
| 12.3 Client CryptoCompare News (free) | 🔴 Haute | 3h | Fetch news historiques gratuites depuis 2015 (titres + catégories) |
| 12.4 Intégration au DecisionService | 🔴 Haute | 4h | En historique : utiliser le sentiment stocké au lieu du RSS temps réel |
| 12.5 Walk-forward avec sentiment | 🔴 Haute | 3h | Vérifier que la précision s'améliore vs 100% technique |
| 12.6 Client CryptoPanic Pro (Palier 2) | 🟡 Moyenne | 6h | News historiques avec votes communauté et sentiment crowd-sourcé |
| 12.7 Client Santiment Pro (Palier 2) | 🟡 Moyenne | 6h | Sentiment social (Twitter, Reddit, Telegram) depuis 2016 |
| 12.8 Pipeline d'enrichissement continu | 🟡 Moyenne | 4h | Job scheduler : stocker automatiquement le sentiment chaque jour |
| 12.9 Normalisation multi-sources | 🟡 Moyenne | 4h | Harmoniser Fear&Greed (0-100) + CryptoPanic (votes) + Santiment (score) → score unifié -100/+100 |
| 12.10 Tests et validation | 🔴 Haute | 4h | Comparer accuracy avec/sans sentiment historique, A/B walk-forward |

### Phase v1.3 — Risk Management ✅ LIVRÉ

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 13.1 Stop-loss / Take-profit | 🔴 Haute | 4h | 3 types : fixe, trailing, ATR — calculés par position | ✅ |
| 13.2 Limite d'exposition | 🔴 Haute | 3h | % max du portefeuille par position + ajustement auto | ✅ |
| 13.3 Limite perte journalière | 🔴 Haute | 3h | Compteur avec reset auto, kill switch si dépassé | ✅ |
| 13.4 Dashboard risque | 🟡 Moyenne | 4h | RiskPanel : jauge, kill switch, config, niveaux de risque | ✅ |
| 13.5 API Risk | 🔴 Haute | 3h | 7 endpoints : config CRUD, status, evaluate, kill-switch, record-loss | ✅ |
| 13.6 55 tests backend | 🔴 Haute | 3h | Config, évaluation, ATR, daily loss, kill switch, endpoints, edge cases | ✅ |

### Phase v1.4 — Paper Trading ✅ LIVRÉ

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 14.1 Modèle PaperAccount + PaperTrade | 🔴 Haute | 3h | Tables SQLAlchemy (compte singleton + journal trades) | ✅ |
| 14.2 Service Paper Trading | 🔴 Haute | 8h | Tick engine, SL/TP check, ouverture/fermeture, métriques, buy & hold | ✅ |
| 14.3 Routes API Paper Trading | 🔴 Haute | 3h | 8 endpoints : account, status, tick, trades, metrics, close | ✅ |
| 14.4 Scheduler Paper Trading | 🟡 Moyenne | 2h | Job APScheduler toutes les 5 minutes | ✅ |
| 14.5 Frontend PaperTradingPanel | 🟡 Moyenne | 4h | Statut, tick manuel, positions, journal, métriques | ✅ |
| 14.6 64 tests backend | 🔴 Haute | 3h | Modèles, service, SL/TP, métriques, tick, endpoints | ✅ |

### Phase v1.5 — Journal + Profils + Levier Auto + Style ✅ LIVRÉ

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 15.1 Journal d'évaluation multi-jours | 🔴 Haute | 6h | Synthèse période, vue journalière, activité, raisons non-trade | ✅ |
| 15.2 Profils de trading | 🔴 Haute | 3h | Conservative/Balanced/Aggressive avec seuils configurables | ✅ |
| 15.3 Levier auto intelligent | 🔴 Haute | 4h | score × confiance × volatilité, veto risk engine | ✅ |
| 15.4 Style de trading | 🟡 Moyenne | 3h | Distribution durées, scalping/intraday/swing | ✅ |
| 15.5 Modèle TickActivityLog | 🔴 Haute | 2h | Persistance de chaque tick (actions + non-trades) | ✅ |
| 15.6 Frontend JournalPanel | 🟡 Moyenne | 4h | 5 sous-vues, profils, KPIs, barres de distribution | ✅ |
| 15.7 64 tests backend | 🔴 Haute | 3h | Journal, profils, levier, style, endpoints, schémas | ✅ |

### Phase v1.6 — Diagnostic + Scalping + Sorties rapides ✅ LIVRÉ

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 16.1 DiagnosticService | 🔴 Haute | 6h | Causes non-trade, durée positions, comparaison profils, risk brake | ✅ |
| 16.2 Profil Scalping | 🔴 Haute | 4h | min_score=5, cooldown=3min, timeframe=15m, seuils custom | ✅ |
| 16.3 Seuils personnalisables | 🔴 Haute | 3h | buy_threshold/sell_threshold par profil | ✅ |
| 16.4 Sorties rapides | 🔴 Haute | 3h | Momentum fade + stale position exit | ✅ |
| 16.5 Opportunités manquées | 🟡 Moyenne | 3h | Analyse ex-post des mouvements ratés | ✅ |
| 16.6 Analyse levier | 🟡 Moyenne | 2h | Comparaison avec/sans levier | ✅ |
| 16.7 DiagnosticPanel UI | 🟡 Moyenne | 4h | 7 sections, recommandations, comparaison profils | ✅ |
| 16.8 55 tests backend | 🔴 Haute | 3h | Diagnostic, scalping, seuils, sorties, endpoints | ✅ |

### Phase v1.7 — Multi-slot + Mean reversion ✅ LIVRÉ

| Tâche | Priorité | Effort | Description | Status |
|-------|----------|--------|-------------|--------|
| 17.1 Positions parallèles multi-slot | 🔴 Haute | 6h | Jusqu'à 3 positions simultanées, allocation capital par slot | ✅ |
| 17.2 Scalping mean reversion bidirectionnel | 🔴 Haute | 4h | SHORT en surachat (RSI/StochRSI), LONG en survente | ✅ |
| 17.3 SL/TP direction-aware | 🔴 Haute | 2h | Defaults corrigés pour SHORT (SL au-dessus, TP en dessous) | ✅ |
| 17.4 Per-slot cooldown | 🔴 Haute | 3h | Timers indépendants par slot | ✅ |
| 17.5 Per-slot daily trade counter | 🔴 Haute | 2h | Compteur journalier par slot | ✅ |
| 17.6 UI multi-slot | 🟡 Moyenne | 3h | Badges de slot sur les positions, bouton robot 1-clic | ✅ |
| 17.7 Fix Windows emoji crash | 🟢 Basse | 0.5h | ASCII dans les logs startup | ✅ |

### Phase v1.8 — Reality Gap Closure 🔄 EN COURS

> **Objectif** : Fermer l'écart entre la sophistication fonctionnelle et la vérité opérationnelle avant tout passage vers v2.0.
>
> **Constat honnête** : Le projet a beaucoup de features et beaucoup de tests, mais les métriques sont structurellement optimistes (pas de frais, spread, ni slippage). Le scalping et le levier amplifient cet optimisme. Tant que cela n'est pas corrigé, les résultats ne peuvent pas être considérés comme fiables pour l'exécution réelle.

| Tâche | Priorité | Description | Status |
|-------|----------|-------------|--------|
| 18.1 TradingCostModel | 🔴 CRITIQUE | Modèle de coûts (frais maker/taker, spread, slippage) avec presets (optimistic/realistic/stressed). Intégration dans les métriques brut/net. | ⬜ |
| 18.2 PaperRun/Campagnes | 🔴 Haute | Concept de "run" : période bornée, profil fixe, slots définis, verdict final. Permet de comparer des profils rigoureusement. | ⬜ |
| 18.3 TruthAudit | 🔴 Haute | Audit de vérité : expectancy nette, drawdown vérifié, impact levier/trailing, contribution par slot/profil, verdict global. | ⬜ |
| 18.4 V2Gate | 🔴 Haute | Gate formelle v2.0 : checklist de readiness avec critères objectifs, status READY/PARTIAL/NOT_READY. | ⬜ |

### Phase Production Ready (future)

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| PR.1 Docker Compose | 🔴 Haute | 3h | Backend + Frontend + PostgreSQL |
| PR.2 CI/CD GitHub Actions | 🟡 Moyenne | 4h | Tests + Build + Deploy |
| PR.3 Auth JWT | 🟡 Moyenne | 6h | Login/Register |
| PR.4 HTTPS + Reverse proxy | 🔴 Haute | 2h | Nginx/Caddy |
| PR.5 Monitoring | 🟢 Basse | 4h | Prometheus + Grafana |

### Phase Multi-Assets (ETH, SOL, etc.) 🌐 (future)

> **Déplacé en dernier** : On perfectionne d'abord tout sur BTC. Si le modèle (technique + sentiment + risk + paper trading) fonctionne bien sur BTC, on l'étend aux autres actifs. BTC est le marché le plus liquide et le mieux documenté — c'est le terrain d'entraînement idéal.

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 17.1 Dropdown symbole | 🔴 Haute | 2h | BTC/USD, ETH/USD, SOL/USD... |
| 17.2 Scheduler multi-symbol | 🔴 Haute | 4h | Loop sur liste configurable |
| 17.3 Dashboard comparatif | 🟡 Moyenne | 4h | Multi-charts ou tabs |
| 17.4 Heatmap corrélation | 🟢 Basse | 6h | Matrice inter-assets |

**Prérequis** : Toutes les phases v1.0 → v1.6 validées sur BTC. Le passage en multi-assets est une extension, pas une priorité tant que le moteur n'est pas mature sur un seul actif.

### Phase v2.0+ — INFINI Mode Autonome ⚠️

> Ce mode ne sera activé qu'après validation complète par backtesting + paper trading.

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 20.1 Connecteur exchange | 🔴 Haute | 8h | Kraken/Binance via ccxt |
| 20.2 Exécution conditionnelle | 🔴 Haute | 10h | 3+ signaux convergents requis |
| 20.3 Trailing stop | 🔴 Haute | 4h | Stop-loss dynamique |
| 20.4 Audit trail complet | 🔴 Haute | 4h | Log chaque décision + raison |
| 20.5 Kill switch physique | 🔴 Haute | 2h | Bouton d'arrêt d'urgence |
| 20.6 Spécialisation stratégies | 🟢 Basse | 20h+ | Scalping, breakout, etc. |

### Phase v3.0+ — INFINI ML Convergent 🧠 (Projet Long Terme)

> ⚠️ **C'est un projet en soi.** Cette phase représente l'aboutissement de la vision INFINI : un modèle d'intelligence artificielle qui apprend en continu à partir de TOUTES les données disponibles — techniques, fondamentales, et contextuelles — pour prendre des décisions de plus en plus pertinentes au fil du temps.

> **Prérequis** : Phases v1.2 (sentiment historique) + v2.0 (exécution) doivent être complètes et validées.

#### La vision : un cerveau unique qui apprend de tout

Aujourd'hui, le moteur de décision est **rule-based** : 8 règles écrites à la main, des seuils fixes, des pondérations statiques. C'est solide pour un v1.0, mais ça a des limites fondamentales :

- Les règles ne s'adaptent pas quand le marché change de régime (bull → bear → range)
- Les seuils (RSI > 70 = surachat) sont les mêmes que tout le monde utilise → ils deviennent des self-fulfilling prophecies ou perdent en efficacité
- Le poids du sentiment (30%) est arbitraire, il devrait varier selon le contexte

**Le modèle ML convergent résout ça** en apprenant automatiquement :
- Quels indicateurs techniques comptent le plus à quel moment
- Quels types de news impactent vraiment le prix (et avec quel délai)
- Comment le sentiment social précède les mouvements de prix
- Les patterns multi-factoriels que des règles manuelles ne peuvent pas capturer
- Comment le marché change de régime et adapter les pondérations en conséquence

#### Architecture du modèle convergent

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     INFINI ML Convergent — Architecture                      │
│                                                                              │
│  DONNÉES D'ENTRÉE (features)                                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐   │
│  │ TECHNIQUE         │  │ SENTIMENT         │  │ CONTEXTUEL              │   │
│  │ • RSI (14, 7, 21) │  │ • Fear & Greed    │  │ • Jour de la semaine    │   │
│  │ • MACD + signal   │  │ • News sentiment  │  │ • Heure (session Asia/  │   │
│  │ • SMA (20,50,200) │  │ • Social volume   │  │   EU/US)                │   │
│  │ • Bollinger %B    │  │ • CryptoPanic     │  │ • Jours avant/après     │   │
│  │ • Volume          │  │   votes            │  │   halving               │   │
│  │ • ATR (volatilité)│  │ • Reddit/Twitter  │  │ • Volatilité récente    │   │
│  │ • Patterns candles│  │   mentions         │  │ • Volume relatif        │   │
│  │ • Multi-timeframe │  │ • Impact score    │  │ • Corrélation S&P500    │   │
│  │   (1h, 4h, 1d)    │  │ • News velocity   │  │ • DXY (dollar index)    │   │
│  └────────┬─────────┘  └────────┬─────────┘  └────────────┬─────────────┘   │
│           │                     │                          │                  │
│           ▼                     ▼                          ▼                  │
│  ┌─────────────────────────────────────────────────────────────────────┐      │
│  │                    FEATURE ENGINEERING                               │      │
│  │  • Normalisation (z-score, min-max)                                 │      │
│  │  • Lag features (sentiment J-1, J-2, J-3...)                       │      │
│  │  • Rolling stats (moyenne mobile du sentiment sur 7j)              │      │
│  │  • Interactions (RSI × Fear&Greed, MACD × news_velocity)          │      │
│  │  • Embeddings NLP des titres de news (si modèle NLP activé)       │      │
│  └──────────────────────────────┬──────────────────────────────────────┘      │
│                                 │                                             │
│                                 ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐      │
│  │                    MODÈLES ML (ENSEMBLE)                            │      │
│  │                                                                     │      │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐    │      │
│  │  │ Gradient     │  │ LSTM / GRU   │  │ Transformer (optionnel)│    │      │
│  │  │ Boosting     │  │ (séries      │  │ (attention sur les     │    │      │
│  │  │ (XGBoost/    │  │ temporelles) │  │ features importantes)  │    │      │
│  │  │ LightGBM)    │  │              │  │                        │    │      │
│  │  └──────┬──────┘  └──────┬───────┘  └────────────┬───────────┘    │      │
│  │         │                │                        │                │      │
│  │         └────────────────┼────────────────────────┘                │      │
│  │                          ▼                                         │      │
│  │              ┌──────────────────┐                                  │      │
│  │              │ META-LEARNER     │                                  │      │
│  │              │ (Stacking /      │                                  │      │
│  │              │  Blending)       │                                  │      │
│  │              └────────┬─────────┘                                  │      │
│  └───────────────────────┼────────────────────────────────────────────┘      │
│                          ▼                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐      │
│  │                    SORTIE (prédiction)                               │      │
│  │  • Direction : HAUSSE / BAISSE / RANGE (classification)            │      │
│  │  • Amplitude estimée : +X% / -X% (régression)                     │      │
│  │  • Confiance : 0-100% (calibré par isotonic regression)            │      │
│  │  • Horizon : 1h, 4h, 24h, 7j                                      │      │
│  │  • Explications : SHAP values (quels facteurs ont compté)         │      │
│  │  • Régime détecté : trending / ranging / volatile                  │      │
│  └─────────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  BOUCLE D'APPRENTISSAGE                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐      │
│  │  1. Prédiction faite à T₀                                          │      │
│  │  2. Résultat réel observé à T₀ + horizon                          │      │
│  │  3. Calcul de l'erreur (prédiction vs réalité)                    │      │
│  │  4. Mise à jour du modèle (online learning / fine-tuning)         │      │
│  │  5. Log dans le journal ML (audit trail complet)                  │      │
│  │  6. Dashboard de monitoring (drift detection, accuracy rolling)    │      │
│  └─────────────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Sous-phases détaillées

##### v3.0 — Dataset Unifié + Feature Engineering

> **Objectif** : Construire le dataset d'entraînement en fusionnant toutes les sources de données.

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 30.1 Schema dataset unifié | 🔴 Haute | 6h | Table ML avec colonnes : timestamp, prix, 30+ features techniques, 10+ features sentiment, label (prix futur) |
| 30.2 Pipeline ETL | 🔴 Haute | 12h | Script qui construit le dataset à partir de candles + indicateurs + sentiment historique |
| 30.3 Feature engineering | 🔴 Haute | 15h | Lag features, rolling stats, interactions, normalisation, target encoding |
| 30.4 Analyse exploratoire (EDA) | 🟡 Moyenne | 8h | Corrélations, distributions, feature importance préliminaire |
| 30.5 Train/validation/test split | 🔴 Haute | 4h | Walk-forward split (pas de random split pour les séries temporelles !) |

**Effort estimé : 40-50h | Coût data : 0€ à 100€/mois selon les sources**

##### v3.1 — Modèles ML Individuels

> **Objectif** : Entraîner et évaluer les modèles de base.

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 31.1 Baseline naïf | 🔴 Haute | 2h | Modèle "toujours prédire la direction de la dernière bougie" — pour comparer |
| 31.2 Gradient Boosting (XGBoost/LightGBM) | 🔴 Haute | 12h | Classification direction + régression amplitude. Fonctionne bien sur features tabulaires |
| 31.3 LSTM / GRU | 🟡 Moyenne | 20h | Réseau récurrent pour capturer les dépendances temporelles longues |
| 31.4 Modèle NLP sentiment | 🟡 Moyenne | 25h | Fine-tuning d'un modèle pré-entraîné (FinBERT ou CryptoBERT) sur les titres de news crypto |
| 31.5 Feature importance (SHAP) | 🔴 Haute | 6h | Comprendre quels facteurs le modèle utilise vraiment |
| 31.6 Hyperparameter tuning | 🟡 Moyenne | 8h | Optuna ou Grid Search avec walk-forward cross-validation |
| 31.7 Comparaison vs règles manuelles | 🔴 Haute | 4h | Le ML bat-il le moteur rule-based v1.0 ? |

**Effort estimé : 60-80h | Coût compute : GPU optionnel (~10-30€ pour un cloud GPU)**

##### v3.2 — Modèle Convergent (Fusion)

> **Objectif** : Combiner les modèles individuels en un modèle unique supérieur.

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 32.1 Stacking / Blending | 🔴 Haute | 10h | Meta-learner qui combine les prédictions des modèles individuels |
| 32.2 Attention multi-sources | 🟡 Moyenne | 15h | Le modèle apprend à pondérer technique vs sentiment selon le contexte |
| 32.3 Détection de régime | 🟡 Moyenne | 10h | Classifier le marché en trending/ranging/volatile et adapter les pondérations |
| 32.4 Calibration de confiance | 🔴 Haute | 6h | Isotonic regression / Platt scaling pour que "80% confiance" = 80% accuracy |
| 32.5 Backtesting ML vs rule-based | 🔴 Haute | 8h | Walk-forward complet sur 2018-2026, comparaison statistique |
| 32.6 Intégration au DecisionService | 🔴 Haute | 8h | Le modèle ML remplace ou enrichit le moteur rule-based |

**Effort estimé : 50-60h**

##### v3.3 — Online Learning + Monitoring

> **Objectif** : Le modèle s'améliore en continu et on peut surveiller sa performance.

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 33.1 Online learning pipeline | 🔴 Haute | 15h | Mise à jour incrémentale du modèle avec les nouvelles données (quotidien/hebdo) |
| 33.2 Drift detection | 🔴 Haute | 8h | Détecter quand la distribution des données change (nouveau régime de marché) |
| 33.3 Auto-retraining | 🟡 Moyenne | 10h | Re-entraînement automatique si le drift est détecté |
| 33.4 Dashboard ML | 🟡 Moyenne | 12h | Accuracy rolling, feature importance temps réel, alertes de dégradation |
| 33.5 A/B testing rule-based vs ML | 🟡 Moyenne | 6h | En paper trading : comparer les deux systèmes en parallèle |
| 33.6 Journal ML complet | 🔴 Haute | 4h | Chaque prédiction logguée avec features, confiance, résultat réel, erreur |
| 33.7 Fallback automatique | 🔴 Haute | 4h | Si le modèle ML dégrade, revenir automatiquement au rule-based |

**Effort estimé : 50-60h**

#### Stack technique recommandée pour le ML

| Composant | Technologie | Pourquoi |
|-----------|------------|----------|
| Feature engineering | **pandas** + **numpy** | Déjà dans le projet, naturel pour les séries temporelles |
| Gradient Boosting | **LightGBM** ou **XGBoost** | State-of-the-art sur données tabulaires, rapide, interprétable |
| Deep Learning | **PyTorch** | Plus flexible que TensorFlow, meilleur pour le prototypage |
| NLP sentiment | **HuggingFace Transformers** + **FinBERT** | Modèle pré-entraîné sur le langage financier, fine-tuning rapide |
| Hyperparameter tuning | **Optuna** | Bayesian optimization, intègre bien avec scikit-learn/LightGBM |
| Explicabilité | **SHAP** | Explications visuelles de chaque prédiction |
| Monitoring | **MLflow** ou custom | Tracking des expériences, versioning des modèles |
| Serving | **FastAPI** (existant) | Le modèle est servi comme un service supplémentaire dans notre API |

#### Estimation globale Phase v3.0

| Sous-phase | Effort | Coût data/compute | Prérequis |
|------------|--------|-------------------|-----------|
| v3.0 Dataset + Features | 40-50h | 0-100 €/mois | v1.2 complet |
| v3.1 Modèles individuels | 60-80h | 10-30 € (GPU cloud) | v3.0 |
| v3.2 Modèle convergent | 50-60h | 10-30 € | v3.1 |
| v3.3 Online learning + monitoring | 50-60h | 0-100 €/mois | v3.2 |
| **TOTAL** | **200-250h** | **~100-200 €/mois** | — |

> ⚠️ **C'est un projet de 3-6 mois à temps partiel.** Il ne faut pas sous-estimer l'effort. Mais chaque sous-phase apporte de la valeur indépendamment : le dataset unifié améliore déjà le backtest, le gradient boosting bat probablement les règles manuelles, le monitoring ML profite à tout le système.

---

## Annexe — Vue timeline

```
2026
├── Avril (réalisé)
│   ├── [✅] v0.6.0 — Socle marché complet (4 timeframes, dual-jobs)
│   ├── [✅] v0.7.0 — Moteur de signaux (52 tests)
│   ├── [✅] v0.8.0 — Alertes & Notifications (48 tests)
│   ├── [✅] v0.9.0 — News & Sentiment (43 tests)
│   ├── [✅] v0.9.5 — Binance Service + DataSourceRouter (45 tests)
│   ├── [✅] v0.9.6 — 14 timeframes Binance + WebSocket prix live (44 tests)
│   ├── [✅] v1.0.0 — Moteur de décision (75 tests) — 417 tests total
│   ├── [✅] v1.1.0 — Backtesting / Simulation (31 tests) — 448 tests total
│   ├── [✅] v1.1.1 — Vérification Historique Time-Travel (33 tests) — 481 tests total
│   ├── [✅] v1.2.x — Sentiment historique (Fear&Greed + CryptoCompare + News DB)
│   ├── [✅] v1.3.0 — Risk Management Engine (55 tests) — 777 tests total
│   ├── [✅] v1.4.0 — Paper Trading System (64 tests) — 841 tests total
│   ├── [✅] v1.5.0 — Journal + Profils + Levier Auto + Style (64 tests) — 930 tests
│   ├── [✅] v1.6.0 — Diagnostic + Scalping + Sorties rapides (55 tests) — 1005 tests
│   ├── [✅] v1.7.0 — Multi-slot + Mean reversion
│   ├── [✅] v1.7.1 — Per-slot cooldown + Fix Windows emoji
│   ├── [✅] v1.7.2 — Trailing stop scalping + Auto-refresh panels
│   └── [🔄] v1.8.0 — Reality Gap Closure
│       ├── [ ] v1.8.1 — TradingCostModel (frais/spread/slippage)
│       ├── [ ] v1.8.2 — PaperRun (campagnes de validation)
│       ├── [ ] v1.8.3 — TruthAudit (audit métriques)
│       └── [ ] v1.8.4 — V2Gate (gate formelle v2.0)
│
├── Mai — Juin
│   └── [ ] v2.0.0 — INFINI Mode Autonome (si gate = READY)
│
├── Q4 2026 — Q1 2027
│   └── [ ] v3.0+ — PHASE ML CONVERGENT 🧠
│
└── 2027+
    └── [ ] Exploitation, maintenance, évolutions continues
```

---

**Fin du document.**
