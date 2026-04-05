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
│  ÉTAPE 2 — INFINI v1 (v1.0 → v1.7)                                 │
│  Assistant intelligent, décisionnel                                  │
│  ├── Moteur de décision / règles        ✅ Livré (v1.0)             │
│  ├── Backtesting engine                 ✅ Livré (v1.1)             │
│  ├── Vérification historique            ✅ Livré (v1.1.1)           │
│  ├── Sentiment historique + ML          🔄 En cours (v1.2.1-1.2.3a livrés)  │
│  ├── Risk management engine             ⬜ Planifié (v1.3)         │
│  ├── Paper trading                      ⬜ Planifié (v1.4)         │
│  ├── Production (Docker, CI/CD, Auth)   ⬜ Planifié (v1.5)         │
│  └── Multi-assets (ETH, SOL...)         ⬜ Planifié (v1.6)         │
│                                                                      │
│  ÉTAPE 3 — INFINI v2 (v2.0+)                                       │
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

### État actuel : v1.2.3a — Persistance News RSS en DB (Livré) ✅

| Composant | Status |
|-----------|--------|
| Backend dual-jobs scheduler | ✅ Complet |
| 14 timeframes (1m → 1w) | ✅ Complet |
| Resample multi-timeframe | ✅ Complet |
| Frontend Dashboard | ✅ Complet |
| Indicateurs (RSI, MACD, SMA, Bollinger) | ✅ Complet |
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
| 620 tests backend | ✅ Tous passing |

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

### Phase v1.3 — Risk Management

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 13.1 Stop-loss / Take-profit | 🔴 Haute | 4h | Configurables par position |
| 13.2 Limite d'exposition | 🔴 Haute | 3h | % max du portefeuille |
| 13.3 Limite perte journalière | 🔴 Haute | 3h | Kill switch si dépassé |
| 13.4 Dashboard risque | 🟡 Moyenne | 4h | Visualisation exposition |

### Phase v1.4 — Paper Trading

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 14.1 Carnet d'ordres fictif | 🔴 Haute | 6h | Market/Limit simulés |
| 14.2 Suivi positions | 🔴 Haute | 4h | PnL temps réel simulé |
| 14.3 Journal de trading | 🔴 Haute | 3h | Log toutes les décisions |
| 14.4 Mode fantôme | 🟡 Moyenne | 2h | Observer sans agir |

### Phase v1.5 — Production Ready

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 15.1 Docker Compose | 🔴 Haute | 3h | Backend + Frontend + PostgreSQL |
| 15.2 CI/CD GitHub Actions | 🟡 Moyenne | 4h | Tests + Build + Deploy |
| 15.3 Auth JWT | 🟡 Moyenne | 6h | Login/Register |
| 15.4 HTTPS + Reverse proxy | 🔴 Haute | 2h | Nginx/Caddy |
| 15.5 Monitoring | 🟢 Basse | 4h | Prometheus + Grafana |

### Phase v1.6 — Multi-Assets (ETH, SOL, etc.) 🌐

> **Déplacé en dernier** : On perfectionne d'abord tout sur BTC. Si le modèle (technique + sentiment + risk + paper trading) fonctionne bien sur BTC, on l'étend aux autres actifs. BTC est le marché le plus liquide et le mieux documenté — c'est le terrain d'entraînement idéal.

| Tâche | Priorité | Effort | Description |
|-------|----------|--------|-------------|
| 16.1 Dropdown symbole | 🔴 Haute | 2h | BTC/USD, ETH/USD, SOL/USD... |
| 16.2 Scheduler multi-symbol | 🔴 Haute | 4h | Loop sur liste configurable |
| 16.3 Dashboard comparatif | 🟡 Moyenne | 4h | Multi-charts ou tabs |
| 16.4 Heatmap corrélation | 🟢 Basse | 6h | Matrice inter-assets |

**Prérequis** : Toutes les phases v1.0 → v1.5 validées sur BTC. Le passage en multi-assets est une extension, pas une priorité tant que le moteur n'est pas mature sur un seul actif.

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

## 1. Introduction stratégique

### 1.1 Origine du projet

Le projet est né d'un besoin concret : disposer d'un outil personnel d'aide à la lecture du marché Bitcoin, capable de collecter des données de prix, de les stocker proprement, de calculer des indicateurs techniques, et de restituer le tout dans une interface lisible.

Le point de départ n'était pas un business plan. C'était un problème réel : comprendre ce que fait le marché, avec des données fiables, des indicateurs solides, et une interface qui ne ment pas.

### 1.2 BTC Insight : l'assistant de lecture

BTC Insight est le nom du produit dans sa forme actuelle. C'est un assistant de lecture du marché. Il collecte des données OHLCV depuis CoinGecko, les stocke en base, les agrège sur plusieurs timeframes (30 minutes, 1 heure, 4 heures, 1 jour), calcule des indicateurs techniques (RSI, MACD, SMA, Bollinger), et affiche tout cela dans un tableau de bord interactif.

BTC Insight ne prend aucune décision. Il informe. Il montre. Il structure.

### 1.3 INFINI : la cible finale

INFINI est le nom de la cible long terme. C'est un système décisionnel complet, capable non seulement de lire le marché, mais de l'interpréter, de produire des signaux, de les croiser avec du contexte, de simuler des décisions, de les tester sur l'historique, et éventuellement d'exécuter des opérations de manière encadrée.

La trajectoire n'est pas :

> tableau de bord → tableau de bord plus joli

La trajectoire est :

> **données de marché → intelligence analytique → intelligence décisionnelle → simulation → automatisation encadrée**

Chaque étape construit sur la précédente. Aucune ne peut être sautée. L'intelligence décisionnelle sans données fiables est du bruit. L'automatisation sans simulation est du risque pur.

### 1.4 Principes directeurs

Le projet suit cinq principes qui guident toutes les décisions de priorisation :

**Fiabilité des données avant tout.** Aucun signal, aucune décision, aucune automatisation ne vaut quoi que ce soit si les données sous-jacentes sont incohérentes, incomplètes ou mal alignées.

**Intelligence progressive.** On ne construit pas un moteur de décision avant d'avoir un moteur de signal qui fonctionne. On ne construit pas un moteur de signal avant d'avoir des indicateurs fiables. On ne fait pas de backtesting avant d'avoir un moteur de décision testable.

**Explicabilité permanente.** Chaque signal, chaque score, chaque décision doit pouvoir être expliqué. Pas de boîte noire. Le système doit pouvoir dire pourquoi il pense ce qu'il pense.

**Contrôle humain garanti.** L'automatisation est un outil, pas un pilote. L'humain reste le décisionnaire final, surtout quand de l'argent réel est en jeu.

**Itération rapide, release fréquente.** Le projet avance par incréments fonctionnels testés. Pas de big bang. Pas de refactor massif sans raison. Chaque livraison doit apporter une valeur concrète et vérifiable.

---

## 2. État des lieux du projet

### 2.1 Historique des releases

Le projet a progressé par itérations concrètes, chacune apportant un bloc fonctionnel testable :

| Version | Date | Contenu principal |
|---------|------|-------------------|
| v0.2 | Janvier 2026 | API candles, fetch CoinGecko, détection de gaps, stockage PostgreSQL |
| v0.3 | Janvier 2026 | Indicateurs techniques (RSI, MACD, SMA, Bollinger), utilitaires de temps |
| v0.4 | Janvier 2026 | APScheduler, fetch automatique, endpoint /scheduler/status |
| v0.5 | Janvier 2026 | Frontend Dashboard complet, graphiques Lightweight Charts, chips statut |
| v0.5.1 | Janvier 2026 | Resample 4h→1d, support du timeframe 1 jour, upsert dialect-aware |
| v0.5.2 | Mars 2026 | Merge branche resample 30m→1h, cap effectiveDays |
| v0.6.0 | Mars 2026 | Dual jobs scheduler (4h + 30m), tous timeframes actifs (30m, 1h, 4h, 1d) |

### 2.2 Backend — Ce qui est livré

**Architecture technique**

Le backend est construit sur FastAPI avec SQLAlchemy pour la couche de données. La structure est propre et suit une séparation claire : routes API, services métier, modèles, schémas, utilitaires.

Les composants backend livrés sont les suivants :

- **API candles** (`/market/candles`) : récupération des candles avec filtres timeframe, symbole, nombre de jours, limite.
- **API indicateurs** (`/market/indicators`) : calcul à la demande de RSI(14), MACD(12,26,9), SMA(20,50,200), Bollinger(20,2). Support du paramètre `include_candles` pour OHLCV complet et de `end_ts` pour reproductibilité backtest.
- **API gaps** (`/market/candles/gaps`) : analyse de la qualité des données avec séparation fraîcheur / complétude.
- **API scheduler** (`/scheduler/status`) : état du scheduler, dernier résultat, prochain run, état par job.
- **API fetch** (`POST /market/candles/fetch`) : déclenchement manuel d'un fetch CoinGecko.
- **API prix** (`/market/price`, `/market/info`) : prix courant et données de marché.
- **Scheduler dual-jobs** : deux jobs APScheduler indépendants. Le job 4h fetch 7 jours de données, stocke en timeframe 4h, puis resample en 1d. Le job 30m fetch 1 jour de données, stocke en timeframe 30m, puis resample en 1h.
- **Service de resample** : agrégation OHLCV générique (30m→1h, 4h→1d), idempotent via upsert.
- **Service CoinGecko** : client HTTP asynchrone, mapping symboles, gestion des timeouts.
- **Utilitaires de temps** : normalisation UTC, alignement bucket (30m, 1h, 4h, 1d), calcul de fenêtre glissante, statut de fraîcheur.

**Couverture de tests**

La couverture de tests est sérieuse. Le dernier run montre 110 tests collectés, dont 106 passent et 4 échouent sur des détails de contrat legacy (messages d'erreur en français vs anglais, comportement edge du job 30m sur le resample). Les tests couvrent :

- Santé de l'API (health, root)
- Alignement des buckets temporels (30m, 1h, 4h, 1d)
- Service d'indicateurs (calcul, warmup, NaN → null, complétude)
- Routes market (candles, filtres, limites)
- Scheduler legacy (config, lifecycle, jobs, status)
- Scheduler dual-jobs (création des 2 jobs, exécution isolée, contrat resample)
- Resample 4h→1d et 30m→1h (création, idempotence, agrégation OHLCV)
- Utilitaires de temps (normalisation, alignement, fenêtres, fraîcheur)

**Points d'attention backend**

- Quatre tests en échec sur des détails de contrat (message d'erreur, interval_minimum, isolation resample dans le job legacy). Ce sont des ajustements mineurs, pas des bugs structurels.
- Warnings "coroutine never awaited" lors des tests du scheduler, liés à l'interaction entre le mock de `_fetch_and_store` (async) et l'exécution synchrone dans les tests. Fonctionnellement sans impact.
- Le fichier `Dashboard.tsx` du frontend a été corrompu (contient des données API WHO au lieu du code React). Nécessite restauration.

### 2.3 Frontend — Ce qui est livré

**Architecture technique**

Le frontend est construit sur React 18 avec TypeScript, Material UI pour les composants, et Lightweight Charts pour les graphiques. Vite est utilisé comme bundler.

Les composants livrés sont les suivants :

- **Dashboard** : page principale avec sélection de timeframe et nombre de jours.
- **CandlestickChart** : graphique en chandeliers via Lightweight Charts.
- **IndicatorPanel** : affichage des indicateurs techniques (RSI, MACD, SMA, Bollinger).
- **PriceCard** : carte de prix courant.
- **DataFreshnessChip** : indicateur visuel de fraîcheur des données (FRESH / STALE / GAPS).
- **SchedulerChip** : indicateur de l'état du scheduler (ON / OFF).
- **StatusBar** et **StatusRow** : barre d'état globale.
- **ErrorBoundary** : gestion gracieuse des erreurs dans le graphique.

**Hooks personnalisés**

- `useCandles` : récupération des candles depuis l'API.
- `useIndicators` : récupération des indicateurs.
- `useMarketGaps` : analyse des gaps de données.
- `useSchedulerStatus` : état du scheduler.

**Types API**

Les types TypeScript sont bien définis pour `SchedulerStatus`, `MarketGapsResponse`, `MarketIndicatorsResponse`, `IndicatorPoint`, etc.

**Points d'attention frontend**

- Le fichier `Dashboard.tsx` est actuellement corrompu et doit être restauré depuis un commit antérieur.
- Le thème est figé en mode sombre. Pas de toggle dark/light.
- Pas de responsive mobile.
- Pas de persistance des préférences utilisateur (timeframe, nombre de jours).
- Les types `SchedulerStatus` ne reflètent pas encore la structure dual-jobs (champ `jobs` manquant).

### 2.4 Infrastructure et outillage

- **Base de données** : SQLite en développement/test, PostgreSQL prévu pour la production. Le code est déjà compatible via SQLAlchemy et le helper d'upsert dialect-aware.
- **Versioning** : Git avec tags sémantiques. Historique propre de 28 commits sur master.
- **CI/CD** : inexistant. Aucun pipeline automatisé.
- **Docker** : inexistant. Pas de containerisation.
- **Documentation** : CHANGELOG.md, README backend, matrice de traçabilité des exigences, roadmap (ce document).

### 2.5 Synthèse : livré / partiellement livré / non commencé

| Bloc fonctionnel | Statut | Version | Commentaire |
|------------------|--------|---------|-------------|
| Collecte de données marché (Binance + CoinGecko) | ✅ Livré | v0.2→v0.9.5 | Binance prioritaire, CoinGecko fallback, 14 timeframes |
| Stockage et alignement temporel | ✅ Livré | v0.2 | UTC, align_to_bucket, 14 timeframes |
| Resample multi-timeframe | ✅ Livré | v0.5.1 | 30m→1h, 30m→4h, 1h→4h, 4h→1d, idempotent |
| Scheduler automatique | ✅ Livré | v0.6 | Dual-jobs APScheduler (4h + 30m) via DataSourceRouter |
| Indicateurs techniques | ✅ Livré | v0.3 | RSI, MACD, SMA, Bollinger |
| Qualité des données (gaps, fraîcheur) | ✅ Livré | v0.2 | Backend complet, frontend chips, gestion NO_DATA |
| Interprétation des indicateurs (signaux) | ✅ Livré | v0.7 | 4 interpréteurs + score composite -100/+100 + résumé |
| Alertes et notifications | ✅ Livré | v0.8 | CRUD complet, évaluation auto, récurrence, presets |
| News / sentiment | ✅ Livré | v0.9 | RSS (3 sources), classifieur keyword, score d'impact, cache TTL |
| Moteur de décision | ✅ Livré | v1.0 | 8 règles, 3 scénarios, recommandation explicable, mode dégradé |
| Dashboard frontend | ✅ Livré | v0.5→v0.9.6 | Premium dark UI, 14 TF, 15 durées, prix live WebSocket |
| Source Binance (14 intervalles natifs) | ✅ Livré | v0.9.5 | Client HTTP async + DataSourceRouter |
| Prix temps réel WebSocket | ✅ Livré | v0.9.6 | Binance WebSocket, reconnexion auto |
| Tests backend | ✅ Livré | v1.0 | 417 tests, tous passing |
| Tests frontend | ❌ Non commencé | — | Aucun test E2E ni unitaire côté front |
| Backtesting | ✅ Livré | v1.1 | Replay historique, métriques, equity curve, journal trades |
| Multi-assets | ❌ Non commencé | — | Déplacé en v1.6 (après validation BTC) |
| Risk engine | ❌ Non commencé | — | — |
| Paper trading | ❌ Non commencé | — | — |
| Exécution automatisée | ❌ Non commencé | — | — |
| CI/CD | ❌ Non commencé | — | — |
| Docker / déploiement | ❌ Non commencé | — | — |
| Authentification | ❌ Non commencé | — | — |

---

## 3. Cartographie fonctionnelle

Le produit final INFINI se découpe en dix blocs fonctionnels majeurs, chacun représentant une capacité distincte du système.

### 3.1 Données de marché

Collecte, stockage, normalisation et agrégation des données OHLCV. C'est le socle fondamental. Sans données fiables, rien ne fonctionne.

Sous-blocs : fetch CoinGecko, stockage SQL, alignement temporel UTC, resample multi-timeframe, détection de gaps, gestion de la fraîcheur, support multi-symboles (futur).

### 3.2 Indicateurs techniques

Calcul des indicateurs classiques de l'analyse technique sur les données stockées. Aujourd'hui : RSI, MACD, SMA, Bollinger. Demain : extensions possibles (Ichimoku, Volume Profile, ATR, Stochastic, etc.).

Sous-blocs : calcul pandas/pandas-ta, gestion du warmup, sérialisation JSON avec NaN → null, complétude des séries.

### 3.3 Signaux et scoring

Interprétation des indicateurs. Transformer un RSI de 72 en "surachat modéré", un croisement MACD en "signal haussier confirmé", un prix sous SMA200 en "tendance baissière de fond".

Sous-blocs : interprétation individuelle par indicateur, score composite multi-indicateurs, niveau de confiance, consensus, raison du signal.

### 3.4 Moteur de décision

Règles métier qui transforment les signaux en scénarios actionnables. "Le RSI est en surachat, le MACD diverge, la SMA50 croise la SMA200 à la baisse : le scénario dominant est une correction de 5-10% dans les 48h, confiance 65%."

Sous-blocs : règles paramétrables, moteur d'évaluation, scénarios multiples, probabilité relative, API de décision structurée.

### 3.5 Simulation et backtesting

Capacité à rejouer les signaux et décisions sur l'historique. "Si j'avais suivi ce signal le 15 mars, qu'est-ce qui se serait passé ?" Validation empirique avant tout passage en réel.

Sous-blocs : replay historique, moteur de simulation, métriques de performance (Sharpe, max drawdown, win rate, profit factor), comparaison de stratégies.

### 3.6 Contexte et sentiment

Enrichissement du moteur de décision avec des informations extra-prix : news, sentiment de marché, événements macro, on-chain data (futur lointain).

Sous-blocs : collecte de news (RSS, API), classification (positif/négatif/neutre), scoring d'impact, intégration au moteur de décision.

### 3.7 Gestion du risque

Limites, garde-fous et conditions d'arrêt. C'est le système immunitaire d'INFINI. Il empêche le système de se mettre en danger.

Sous-blocs : stop-loss, take-profit, limites d'exposition, limites de perte journalière/hebdomadaire, kill switch, conditions d'arrêt automatique.

### 3.8 Paper trading

Exécution fictive en temps réel. Le système passe des ordres simulés sur le marché live, sans argent réel, et suit les positions comme si elles étaient réelles.

Sous-blocs : carnet d'ordres fictif, suivi de positions, PnL simulé, journal de trading, comparaison avec le marché.

### 3.9 Exécution automatisée

Connexion à un exchange réel pour passer de vrais ordres. C'est la phase la plus sensible. Elle ne doit arriver qu'après une validation complète par le paper trading et le backtesting.

Sous-blocs : connecteur exchange (Kraken, Binance via ccxt), moteur d'ordres (market, limit), sécurité, audit trail, supervision humaine, kill switch physique.

### 3.10 UX, pédagogie et supervision

L'interface qui rend tout cela compréhensible, même pour quelqu'un qui n'est pas trader professionnel. Mode simple, explications humaines, signaux lisibles, raisons affichées, monitoring temps réel.

Sous-blocs : mode expert / mode simple, explications en langage naturel, visualisation des décisions, tableau de bord de supervision, alertes visuelles et sonores.

---

## 4. Niveaux de maturité produit

Le projet se structure en cinq niveaux de maturité, chacun représentant un palier de capacité fondamentalement différent.

### Niveau 1 — Socle marché

**Capacité** : collecter, stocker, agréger et restituer des données de marché fiables.

**Statut actuel** : largement atteint. Les quatre timeframes sont opérationnels (30m, 1h, 4h, 1d), le resample fonctionne, le scheduler est en dual-jobs, la qualité des données est monitorée.

**Ce qui manque** : correction des 4 tests en échec, restauration du Dashboard.tsx corrompu, stabilisation des warnings async, tests frontend, support multi-symboles.

### Niveau 2 — Intelligence analytique

**Capacité** : calculer des indicateurs, les interpréter, produire un score consolidé, expliquer le score.

**Statut actuel** : les indicateurs sont calculés mais pas interprétés. Le système sait que le RSI vaut 72 mais ne sait pas ce que ça signifie. Il n'y a pas de score, pas de synthèse, pas d'explication.

**Ce qui manque** : tout le moteur de signal, le scoring, l'interprétation, la synthèse.

### Niveau 3 — Intelligence décisionnelle

**Capacité** : transformer les signaux en scénarios, évaluer la confiance, proposer une action.

**Statut actuel** : non commencé.

**Ce qui manque** : moteur de règles, scénarios, probabilités, API de décision.

### Niveau 4 — Simulation

**Capacité** : tester les décisions sur l'historique et en temps réel simulé.

**Statut actuel** : non commencé. Cependant, le paramètre `end_ts` dans l'API indicateurs a été pensé pour la reproductibilité backtest — c'est un signe que la simulation est dans l'ADN du projet.

**Ce qui manque** : moteur de backtest, métriques, paper trading.

### Niveau 5 — Automatisation

**Capacité** : exécuter des opérations réelles, sous contrôle strict.

**Statut actuel** : non commencé. C'est la phase la plus lointaine et la plus sensible.

**Ce qui manque** : connecteur exchange, risk engine, audit trail, kill switch.

---

## 5. Roadmap détaillée par phases

### Phase 3 — Consolidation produit (v0.7)

**Objectif** : stabiliser ce qui existe, corriger ce qui est cassé, poser les bases d'une progression saine.

**Pourquoi maintenant** : on ne peut pas avancer sérieusement avec un Dashboard.tsx corrompu, des tests en échec et aucun test frontend. La consolidation n'est pas du cosmétique, c'est de l'hygiène.

**Périmètre fonctionnel**

- Restauration du fichier Dashboard.tsx depuis le dernier commit fonctionnel.
- Correction des 4 tests backend en échec (message d'erreur `_timeframe_from_days`, interval_minimum, isolation resample job 30m).
- Résolution des warnings "coroutine never awaited" dans les tests scheduler.
- Mise à jour des types TypeScript frontend pour refléter la structure dual-jobs du scheduler.
- Ajout d'un toggle dark/light mode (ThemeProvider MUI).
- Responsive mobile basique (breakpoints, adaptation du layout).
- Persistance localStorage des préférences utilisateur (timeframe, nombre de jours).
- Documentation technique de base (architecture, conventions, setup pour nouveau développeur).

**Périmètre technique**

- Aucune nouvelle fonctionnalité métier.
- Nettoyage, stabilisation, documentation.
- Mise en place d'un lint strict côté frontend.

**Livrables**

- Dashboard.tsx restauré et fonctionnel.
- 110/110 tests backend green.
- Types frontend alignés sur l'API dual-jobs.
- Toggle dark/light.
- Responsive fonctionnel sur mobile.
- README mis à jour avec instructions de setup complètes.

**Dépendances** : aucune.

**Risques** : aucun risque technique significatif. Le risque principal est de sous-estimer l'effort de nettoyage et de se disperser.

**Critère de sortie** : tous les tests passent, le frontend build sans erreur, le Dashboard s'affiche correctement sur desktop et mobile, la documentation permet à un nouveau développeur de lancer le projet en moins de 15 minutes.

---

### Phase 4 — Moteur de signaux (v0.8)

**Objectif** : transformer les indicateurs bruts en signaux interprétés, scorés et explicables.

**Pourquoi maintenant** : c'est le passage du Niveau 1 (données) au Niveau 2 (intelligence). Sans cette phase, le produit reste un tableau de bord passif. Avec cette phase, il commence à penser.

**Périmètre fonctionnel**

- Définition d'un format standard de signal :
  ```
  {
    "indicator": "rsi_14",
    "value": 72.3,
    "interpretation": "surachat_modéré",
    "direction": "bearish",
    "strength": 0.65,
    "reason": "RSI au-dessus de 70 depuis 3 périodes, probabilité de correction élevée"
  }
  ```
- Interprétation de chaque indicateur existant :
  - RSI : zones de surachat (>70), survente (<30), neutre, divergences.
  - MACD : croisements signal, divergence histogramme, momentum.
  - SMA : position du prix par rapport aux moyennes, croisements (golden cross, death cross).
  - Bollinger : position dans les bandes, squeeze, breakout.
- Score composite multi-indicateurs : un score unique de -100 (très baissier) à +100 (très haussier), avec explication de la composition.
- Consensus : le système indique si les indicateurs convergent ou divergent.
- Endpoint API `/market/signals` retournant les signaux structurés.
- Composant frontend `SignalPanel` affichant les signaux avec couleurs, icônes et explications.

**Périmètre technique**

- Nouveau service `signal_service.py` dans le backend.
- Nouveau schéma `signal.py` pour la sérialisation.
- Nouvelle route `/market/signals`.
- Nouveau composant frontend.
- Tests unitaires pour chaque règle d'interprétation.

**Livrables**

- API `/market/signals` fonctionnelle.
- Score composite calculé et affiché.
- Explications en langage naturel pour chaque signal.
- Consensus affiché (convergence/divergence des indicateurs).
- Tests backend pour le service de signaux.

**Dépendances** : Phase 3 (consolidation) terminée.

**Risques**

- Risque de sur-ingénierie des règles d'interprétation. Il faut rester simple et itérer.
- Risque de faux positifs si les seuils sont mal calibrés. Le scoring doit être conservateur.

**Critère de sortie** : les signaux sont calculés pour les 4 timeframes, le score composite est affiché dans le frontend, chaque signal a une explication lisible, les tests passent.

---

### Phase 5 — Moteur de décision (v0.9)

**Objectif** : transformer les signaux en scénarios actionnables avec un niveau de confiance.

**Pourquoi maintenant** : les signaux seuls ne suffisent pas. Un RSI en surachat ne veut rien dire si le MACD est en pleine accélération haussière. Le moteur de décision croise, pondère, et propose.

**Périmètre fonctionnel**

- Définition de règles métier paramétrables :
  - Règle simple : "Si RSI > 70 ET MACD histogramme décroissant → signal de vente, confiance 60%".
  - Règle composite : croisement de signaux multi-timeframes.
- Moteur d'évaluation des règles :
  - Évaluation séquentielle des règles par ordre de priorité.
  - Score de confiance pondéré (0% à 100%).
  - Explication de la décision (quelles règles ont contribué, avec quel poids).
- Scénarios multiples :
  - Le système peut proposer plusieurs scénarios simultanés avec des probabilités relatives.
  - Exemple : "Scénario A (correction 5%, confiance 65%) vs Scénario B (continuation haussière, confiance 35%)".
- API `/decisions` retournant les scénarios structurés.
- Interface frontend `DecisionPanel` affichant les scénarios.

**Périmètre technique**

- Service `decision_service.py`.
- Modèle `Rule` en base pour les règles paramétrables.
- Moteur d'évaluation avec chaîne de responsabilité.
- API CRUD pour les règles.
- Tests unitaires et d'intégration.

**Livrables**

- API de décision fonctionnelle.
- Règles paramétrables via l'API.
- Scénarios avec confiance et explication.
- Interface frontend.
- Tests complets.

**Dépendances** : Phase 4 (signaux) terminée.

**Risques**

- Complexité des règles : il faut commencer avec un jeu de règles minimal et itérer.
- Biais de confirmation : le système doit présenter les scénarios contradictoires, pas seulement le plus probable.
- Sur-confiance : les pourcentages de confiance doivent être calibrés avec humilité.

**Critère de sortie** : au moins 5 règles fonctionnelles, scénarios générés automatiquement, explications lisibles, le système présente des scénarios contradictoires quand les signaux divergent.

---

### Phase 6 — Simulation et backtesting (v1.0)

**Objectif** : valider empiriquement la qualité des signaux et des décisions sur l'historique.

**Pourquoi maintenant** : on ne peut pas faire confiance à un moteur de décision qui n'a jamais été testé contre la réalité. Le backtesting est le crash-test du système.

**Périmètre fonctionnel**

- Moteur de replay historique :
  - Parcours chronologique des candles passées.
  - Recalcul des indicateurs, signaux et décisions à chaque pas de temps.
  - Simulation de positions (achat/vente) selon les décisions.
- Métriques de performance :
  - Taux de réussite (win rate).
  - Profit factor.
  - Ratio de Sharpe.
  - Maximum drawdown.
  - Durée moyenne des trades.
  - Ratio gain/perte moyen.
- Comparaison de stratégies : possibilité de tester plusieurs jeux de règles et de comparer les résultats.
- Equity curve : courbe de capital simulé dans le temps.
- Journal de trades : liste détaillée de chaque opération simulée avec raison, entrée, sortie, durée, PnL.
- Endpoint API `/backtest/run` et `/backtest/results`.
- Interface frontend avec equity curve, tableau des trades, métriques.

**Périmètre technique**

- Service `backtest_service.py`.
- Modèles `BacktestRun`, `BacktestTrade`.
- Moteur de simulation avec gestion du capital et des positions.
- Stockage des résultats en base.
- Visualisation frontend (graphique equity, tableau).

**Livrables**

- Backtesting fonctionnel sur au moins 30 jours d'historique.
- Métriques calculées et affichées.
- Equity curve visualisée.
- Journal de trades consultable.
- Comparaison possible de 2+ stratégies.

**Dépendances** : Phase 5 (décision) terminée. Nécessite un historique de données suffisant en base.

**Risques**

- Sur-optimisation (overfitting) : il est facile de créer des règles qui performent parfaitement sur le passé mais échouent sur le futur. Le système doit signaler le risque de sur-optimisation.
- Biais du survivant : ne tester que les scénarios gagnants.
- Données insuffisantes : CoinGecko gratuit limite l'historique. Il faudra peut-être envisager des sources de données historiques complémentaires.

**Critère de sortie** : backtest réalisable sur 30 jours minimum, métriques correctement calculées, equity curve affichée, aucune sur-optimisation évidente sur le jeu de test.

---

### Phase 7 — Alertes et notifications (v1.1)

**Objectif** : permettre à l'utilisateur de définir des conditions de déclenchement et d'être notifié quand elles se réalisent.

**Pourquoi maintenant** : une fois le moteur de signal et de décision en place, les alertes deviennent naturelles. Elles transforment le système de "passif" à "proactif" sans aller jusqu'à l'automatisation.

**Périmètre fonctionnel**

- Modèle d'alerte en base : condition (prix, RSI, MACD, score composite, seuil custom), statut (active/déclenchée/désactivée), historique.
- API CRUD `/alerts` (GET, POST, PUT, DELETE).
- Service AlertChecker intégré au scheduler : évaluation périodique des conditions.
- Notifications navigateur (Web Push API ou polling).
- Notifications externes optionnelles (webhook, Discord, Telegram).
- Interface frontend : formulaire de création, liste des alertes actives, historique des déclenchements.

**Périmètre technique**

- Modèle SQLAlchemy `Alert`.
- Service `alert_service.py`.
- Job scheduler dédié pour l'évaluation des alertes.
- Route API `/alerts`.
- Composant frontend `AlertPanel`.

**Livrables**

- Alertes sur prix, RSI, score composite.
- Notifications navigateur.
- Interface de gestion complète.
- Au moins un canal de notification externe.

**Dépendances** : Phase 4 (signaux) minimum. Idéalement Phase 5 (décision) pour les alertes sur score composite.

**Risques**

- Spam de notifications si les seuils sont mal calibrés.
- Latence : le scheduler doit être assez fréquent pour que les alertes soient utiles.

**Critère de sortie** : alertes fonctionnelles, notification reçue dans les 5 minutes suivant le déclenchement de la condition, interface de gestion opérationnelle.

---

### Phase 8 — Contexte et sentiment (v1.2)

**Objectif** : enrichir le moteur de décision avec des informations extra-prix.

**Pourquoi maintenant** : cette phase est volontairement placée après le moteur de décision et le backtesting. Le sentiment est un signal bruité et subjectif. Il ne doit être intégré que quand le cœur de décision est déjà solide et testable, pour ne pas introduire de bruit dans un système qui n'est pas encore stable.

**Périmètre fonctionnel**

- Collecte de news crypto via API (CryptoPanic, NewsAPI, flux RSS).
- Classification automatique : positif, négatif, neutre.
- Scoring d'impact : évaluation de l'importance relative d'une news.
- Intégration au moteur de décision : le sentiment devient un facteur supplémentaire dans le scoring, avec un poids configurable.
- Affichage dans le frontend : flux de news, score de sentiment, impact sur la décision.

**Périmètre technique**

- Service `sentiment_service.py`.
- Modèle `NewsItem` en base.
- Classification NLP basique (mots-clés, puis éventuellement modèle ML léger).
- Intégration dans `decision_service.py`.

**Livrables**

- Flux de news affiché.
- Score de sentiment calculé.
- Impact sur le moteur de décision visible et explicable.
- Tests de non-régression sur le moteur de décision avec et sans sentiment.

**Dépendances** : Phase 5 (décision) terminée, Phase 6 (backtest) idéalement terminée.

**Risques**

- News bruitées ou contradictoires.
- Biais de récence : les news récentes ont trop d'impact.
- Dépendance à des API externes gratuites avec des limites.
- Complexité NLP : la classification de sentiment en crypto est notablement difficile.

**Critère de sortie** : news collectées et classifiées, sentiment intégré comme facteur au moteur de décision avec poids configurable, le système fonctionne correctement avec le sentiment désactivé (pas de dépendance dure).

---

### Phase 9 — Risk engine (v1.3)

**Objectif** : poser les garde-fous nécessaires avant toute forme de trading, même simulé.

**Pourquoi maintenant** : le risk engine doit être en place avant le paper trading. Il n'y a pas de simulation sérieuse sans gestion du risque.

**Périmètre fonctionnel**

- Stop-loss paramétrable (fixe, trailing, basé sur ATR).
- Take-profit paramétrable.
- Limites d'exposition : montant maximum par position, par symbole, total.
- Limites de perte : perte maximale par jour, par semaine, total.
- Conditions d'arrêt automatique : si la perte atteint un seuil, tout s'arrête.
- Kill switch : bouton rouge accessible en un clic.
- Journal des décisions du risk engine : chaque intervention est logguée.

**Périmètre technique**

- Service `risk_service.py`.
- Configuration en base (paramètres de risque).
- Intégration dans le moteur de décision (le risk engine peut bloquer une décision).
- API pour configurer les paramètres.
- Interface frontend.

**Livrables**

- Stop-loss et take-profit fonctionnels.
- Limites d'exposition et de perte.
- Kill switch.
- Journal des interventions du risk engine.
- Tests unitaires et d'intégration.

**Dépendances** : Phase 5 (décision) terminée.

**Risques**

- Faux sentiment de sécurité : le risk engine ne protège pas contre des conditions de marché extrêmes (flash crash, liquidité nulle).
- Paramétrage trop lâche ou trop serré.

**Critère de sortie** : le risk engine bloque correctement une position qui dépasse les limites configurées, le kill switch arrête tout en moins de 2 secondes, le journal est exhaustif.

---

### Phase 10 — Paper trading (v1.4)

**Objectif** : simuler le trading en conditions réelles, sans argent.

**Pourquoi maintenant** : après le backtesting (passé) et le risk engine (garde-fous), le paper trading permet de valider en temps réel, sur le marché live.

**Périmètre fonctionnel**

- Simulation d'ordres en temps réel.
- Carnet de positions fictif.
- PnL simulé en continu.
- Journal de trading détaillé.
- Comparaison performance simulée vs marché.
- Dashboard de suivi : positions ouvertes, historique, métriques live.

**Périmètre technique**

- Service `paper_trading_service.py`.
- Modèles `PaperPosition`, `PaperTrade`.
- Job scheduler dédié pour l'évaluation continue.
- Interface frontend dédiée.

**Livrables**

- Paper trading fonctionnel sur BTC/USD.
- Positions ouvertes et fermées automatiquement selon les règles.
- PnL calculé et affiché.
- Journal consultable.
- Métriques de performance en temps réel.

**Dépendances** : Phase 6 (backtest), Phase 9 (risk engine) terminées.

**Risques**

- Le paper trading peut donner des résultats trop optimistes (pas de slippage, pas de latence d'exécution, pas de problème de liquidité).
- Tentation de passer trop vite en réel.

**Critère de sortie** : au moins 2 semaines de paper trading continu sans intervention, métriques stables, aucun bug critique dans le journal.

---

### Phase 11 — Exécution automatisée encadrée (v2.0)

**Objectif** : permettre au système de passer de vrais ordres sur un exchange, sous contrôle strict.

**Pourquoi maintenant** : c'est la phase finale. Elle ne doit arriver qu'après une validation complète du paper trading sur une période significative (minimum 1 mois).

**Périmètre fonctionnel**

- Connecteur exchange via ccxt (Kraken, Binance).
- Ordres market et limit.
- Exécution encadrée par le risk engine.
- Mode "confirmation humaine" : le système propose, l'humain valide.
- Mode "automatique" : le système exécute avec les garde-fous du risk engine.
- Audit trail complet : chaque décision, chaque ordre, chaque exécution est logguée avec raison, contexte et résultat.
- Kill switch physique et logiciel.
- Dashboard de supervision en temps réel.

**Périmètre technique**

- Service `execution_service.py`.
- Intégration ccxt.
- Sécurité des clés API (vault, chiffrement).
- Double validation pour les montants importants.
- Monitoring et alertes en cas d'anomalie.

**Livrables**

- Connexion fonctionnelle à au moins 1 exchange.
- Ordres exécutés correctement.
- Risk engine actif sur chaque opération.
- Audit trail complet.
- Kill switch fonctionnel.
- Mode confirmation humaine par défaut.

**Dépendances** : toutes les phases précédentes terminées. Phase 10 (paper trading) validée sur au moins 1 mois.

**Risques**

- Risque financier réel. C'est la première phase où de l'argent réel est en jeu.
- Bugs d'exécution (double exécution, mauvais montant, mauvais sens).
- Défaillance de l'exchange (API down, latence, erreur).
- Flash crash : le marché peut bouger de 20% en quelques minutes.
- Sécurité des clés API : compromission = perte totale.

**Critère de sortie** : 1 semaine de trading réel avec micro-positions (montants minimaux), 0 anomalie, audit trail complet, kill switch testé en conditions réelles.

---

### Phase 12 — UX produit final (v2.1)

**Objectif** : rendre le produit utilisable par quelqu'un qui n'est ni trader professionnel, ni ingénieur, ni statisticien.

**Pourquoi en dernier** : l'UX est un multiplicateur, pas un fondement. Il vaut mieux avoir un système qui fonctionne avec une interface austère qu'un système joli qui ne sait rien faire. L'UX est une phase de polissage qui arrive quand le cœur est solide.

**Périmètre fonctionnel**

- Mode simple vs mode expert :
  - Mode simple : "Le marché est plutôt haussier aujourd'hui. Confiance : modérée. Raison : les indicateurs techniques convergent vers un signal positif."
  - Mode expert : tous les chiffres, tous les indicateurs, tous les détails.
- Explications en langage naturel pour chaque signal, chaque décision, chaque opération.
- Visualisation des décisions : pourquoi le système a acheté, vendu, attendu.
- Tutoriel intégré pour les concepts (RSI, MACD, etc.).
- Dashboard de supervision : vue d'ensemble de tout le système.
- Monitoring : état de chaque composant, alertes système.

**Livrables**

- Mode simple et expert fonctionnels.
- Explications en langage naturel partout.
- Dashboard de supervision complet.
- Documentation utilisateur.

---

### Phase 13 — Déploiement production (v2.2)

**Objectif** : rendre le système déployable, maintenable et sécurisé en production.

**Périmètre fonctionnel et technique**

- Docker Compose (backend + frontend + PostgreSQL).
- CI/CD GitHub Actions (tests, build, deploy).
- Migration SQLite → PostgreSQL définitive.
- Authentification JWT (login, register, sessions).
- HTTPS avec reverse proxy (Nginx ou Caddy).
- Monitoring (Prometheus + Grafana ou équivalent).
- Backup automatique de la base de données.
- Rate limiting sur l'API.

**Dépendances** : idéalement après Phase 9 minimum (risk engine), car la production implique des enjeux de sécurité.

---

## 6. Priorisation argumentée

### Pourquoi les signaux avant les alertes

Les alertes sans intelligence sont des seuils bruts ("RSI > 70 → alerte"). Ce n'est pas fondamentalement différent de ce que fait n'importe quel outil existant. Les signaux structurés et scorés donnent aux alertes un sens réel. "Le score composite est passé en zone de risque → alerte" est beaucoup plus puissant que "RSI > 70 → alerte".

### Pourquoi le moteur de décision avant le backtesting

On ne peut pas tester ce qui n'existe pas. Le backtesting a besoin de règles à évaluer. Sans moteur de décision, le backtest est un exercice vide.

### Pourquoi le sentiment arrive tard

Le sentiment est le signal le plus bruité de tous. Les news crypto sont souvent contradictoires, manipulatrices, ou simplement hors sujet. Intégrer le sentiment dans un moteur de décision qui n'est pas encore solide, c'est ajouter du bruit à du bruit. Le sentiment est un enrichissement, pas un fondement.

### Pourquoi le risk engine avant le paper trading

Le paper trading sans gestion du risque crée de mauvaises habitudes. Même en simulation, il faut respecter les limites, poser des stops, et s'entraîner à la discipline. Le risk engine doit être le réflexe, pas l'exception.

### Pourquoi le paper trading avant l'exécution réelle

C'est une évidence, mais elle mérite d'être explicite. Aucun système de trading ne devrait toucher de l'argent réel sans avoir été validé en simulation pendant une période significative. La tentation de "tester avec un petit montant" est un piège. Le paper trading gratuit et sans risque est la seule validation légitime.

### Pourquoi l'UX finale arrive en dernier

Investir du temps dans une interface parfaite pour un système qui ne sait pas encore ce qu'il fait est du gaspillage. L'UX actuelle (Dashboard, chips, graphique) est suffisante pour développer et tester. L'UX finale est un investissement de polissage qui n'a de sens que quand le cœur fonctionnel est stabilisé.

### Pourquoi ne pas brûler du temps sur le cosmétique

Le projet n'est pas un concours de design. Chaque heure passée sur une animation, une transition, ou un dégradé de couleur est une heure qui n'est pas passée sur le moteur de signal, le scoring, ou le backtesting. Le cosmétique viendra quand le cerveau sera construit.

---

## 7. UX, accessibilité et pédagogie

### 7.1 Principe fondamental

Le projet vise à être compréhensible par quelqu'un qui n'est pas expert. Ce n'est pas un outil réservé aux quants. C'est un assistant qui doit pouvoir expliquer ce qu'il fait et pourquoi.

### 7.2 Mode simple

Le mode simple doit :

- Résumer la situation en une phrase. "Le marché BTC est en tendance haussière modérée. Les indicateurs techniques sont globalement positifs. Pas de signal d'alerte."
- Utiliser des couleurs claires : vert = positif, rouge = négatif, orange = prudence, gris = neutre.
- Afficher un score global compréhensible (jauge visuelle).
- Ne pas afficher de chiffres bruts sauf demande explicite.
- Proposer des explications accessibles : "Le RSI est un indicateur qui mesure si un actif a été trop acheté ou trop vendu récemment."

### 7.3 Mode expert

Le mode expert doit :

- Afficher tous les indicateurs numériques.
- Permettre la personnalisation des paramètres (longueur RSI, bandes de Bollinger, etc.).
- Afficher les règles actives du moteur de décision.
- Donner accès aux résultats de backtesting détaillés.
- Permettre l'export des données.

### 7.4 Contrôle humain

Si le système évolue vers l'automatisation :

- L'humain doit pouvoir voir chaque décision avant exécution (mode confirmation).
- L'humain doit pouvoir arrêter tout à tout moment (kill switch).
- L'humain doit pouvoir comprendre pourquoi le système a pris une décision (audit trail).
- Le système ne doit jamais mentir sur son niveau de confiance.
- Le système doit signaler quand il ne sait pas (incertitude élevée, signaux contradictoires).

### 7.5 Pédagogie intégrée

Chaque concept technique affiché dans l'interface doit avoir une info-bulle ou un lien vers une explication simple. L'utilisateur ne devrait jamais se retrouver face à un terme qu'il ne comprend pas sans avoir un moyen immédiat d'en comprendre le sens.

---

## 8. Risques et garde-fous

### 8.1 Faux signaux

Les indicateurs techniques ne sont pas des prédictions. Ce sont des mesures statistiques qui ont une certaine corrélation avec les mouvements futurs, mais qui peuvent être faux. Le RSI peut rester en zone de surachat pendant des semaines dans une tendance forte.

**Garde-fou** : ne jamais présenter un signal comme une certitude. Toujours afficher le niveau de confiance. Toujours afficher les signaux contradictoires.

### 8.2 Biais de confiance

Plus un système donne des signaux qui s'avèrent corrects, plus l'utilisateur lui fait confiance aveuglément. C'est dangereux.

**Garde-fou** : afficher les statistiques de performance réelles (taux de réussite, drawdown). Rappeler régulièrement que les performances passées ne garantissent pas les performances futures. Intégrer un rappel explicite dans l'interface.

### 8.3 Sur-optimisation

Créer des règles qui performent parfaitement sur l'historique mais échouent en conditions réelles. C'est le piège le plus classique du backtesting.

**Garde-fou** : séparer les données en échantillon d'entraînement et de validation. Signaler quand une stratégie a un nombre anormalement élevé de paramètres. Comparer avec une stratégie naïve (buy and hold).

### 8.4 Automatisation trop précoce

La tentation de passer en automatique avant que le système ne soit suffisamment validé.

**Garde-fou** : imposer un minimum de 1 mois de paper trading avant toute exécution réelle. Commencer avec des montants minimaux. Augmenter progressivement.

### 8.5 Dépendance à un indicateur unique

S'appuyer trop sur un seul indicateur (typiquement le RSI) au détriment d'une vue globale.

**Garde-fou** : le score composite doit être la métrique de référence, pas un indicateur unique. L'interface ne doit pas mettre un indicateur en avant plus que les autres.

### 8.6 Qualité et fraîcheur des données

CoinGecko gratuit a des limites : rate limiting, données OHLC sans volume réel, résolution limitée.

**Garde-fou** : monitorer en continu la fraîcheur des données (déjà en place). Afficher clairement quand les données sont stale. Prévoir des sources alternatives. Ne jamais prendre de décision sur des données périmées.

### 8.7 News bruitées

Le marché crypto est rempli de bruit : rumeurs, FUD, shilling, manipulation médiatique.

**Garde-fou** : le sentiment ne doit jamais avoir un poids majoritaire dans le moteur de décision. Il doit être configurable et désactivable. Les sources doivent être sélectionnées avec soin.

### 8.8 Risque financier réel

En phase d'exécution automatisée, de l'argent réel est en jeu.

**Garde-fous** :
- Kill switch immédiat.
- Limites de perte strictes.
- Montants minimaux au démarrage.
- Audit trail exhaustif.
- Jamais plus d'argent que ce qu'on peut se permettre de perdre.
- Le système n'a pas accès aux retraits (clés API avec permissions limitées).

### 8.9 Risque technique

Bugs, pannes, erreurs d'exécution, double exécution d'ordres.

**Garde-fous** :
- Tests exhaustifs avant chaque release.
- CI/CD avec tests automatisés.
- Monitoring en temps réel.
- Alertes en cas d'anomalie.
- Rollback possible.

---

## 9. Conclusion opérationnelle

### Ce qu'est le projet aujourd'hui

BTC Insight est un assistant de lecture du marché Bitcoin fonctionnel. Il collecte des données OHLCV sur quatre timeframes, calcule des indicateurs techniques, et affiche le tout dans un tableau de bord interactif avec monitoring de la qualité des données.

Le socle technique est solide : 110 tests backend, architecture propre, scheduler dual-jobs, resample multi-timeframe, types TypeScript bien définis.

### Ce qu'il n'est pas encore

BTC Insight ne pense pas. Il ne sait pas interpréter un RSI de 72 ou un croisement MACD. Il n'a pas de score, pas de signal structuré, pas de moteur de décision, pas de backtesting, pas de simulation, pas d'alertes, pas de risk engine.

Le chemin entre "afficher un RSI" et "exécuter un trade automatique avec confiance" est long, technique, et parsemé de pièges. Chaque étape doit être rigoureusement validée avant de passer à la suivante.

### La prochaine priorité

La prochaine action concrète est la **Phase 3 : consolidation produit**. Corriger ce qui est cassé (Dashboard.tsx, tests en échec), stabiliser ce qui existe, poser les bases pour la suite. C'est un investissement de quelques jours qui sécurise tout le reste.

Immédiatement après : la **Phase 4 : moteur de signaux**. C'est le passage du "j'affiche des chiffres" au "je comprends ce que les chiffres veulent dire". C'est la transformation qui donne au produit son identité.

### Comment piloter la suite

Trois règles simples :

**Une phase à la fois.** Ne pas commencer la Phase 5 avant que la Phase 4 ne soit validée. La tentation de paralléliser est forte, mais elle mène à des fondations instables.

**Tester avant d'avancer.** Chaque phase doit avoir ses tests. Chaque livrable doit avoir son critère de validation. Si les tests ne passent pas, on ne passe pas à la suite.

**Ne pas se disperser.** Le projet avance vite quand il est concentré. Chaque feature request "ce serait bien si..." doit être évaluée contre la question : "est-ce que ça fait avancer vers INFINI, ou est-ce que c'est du cosmétique qui peut attendre ?"

---

## Annexe — Vue timeline

```
2026
├── Avril (réalisé)
│   ├── [✅] v0.6.0 — Socle marché complet (4 timeframes, dual-jobs)
│   ├── [✅] v0.7.0 — Moteur de signaux (52 tests)
│   ├── [✅] v0.8.0 — Alertes & Notifications (48 tests)
│   ├── [✅] v0.9.0 — News & Sentiment (43 tests)
│   ├── [✅] v0.9.1 — Smart Alert Presets (12 stratégies)
│   ├── [✅] v0.9.2 — Premium Dark Trading UI
│   ├── [✅] v0.9.3 — Layout intelligent responsive
│   ├── [✅] v0.9.5 — Binance Service + DataSourceRouter (45 tests)
│   ├── [✅] v0.9.6 — 14 timeframes Binance + WebSocket prix live (44 tests)
│   ├── [✅] v1.0.0 — Moteur de décision (75 tests) — 417 tests total
│   ├── [✅] v1.1.0 — Backtesting / Simulation (31 tests) — 448 tests total
│   └── [✅] v1.1.1 — Vérification Historique Time-Travel (33 tests) — 481 tests total
│
├── Mai (en cours)
│   ├── [✅] v1.2.3a — Persistance News RSS en DB (33 tests) — 620 tests total
│   ├── [🔄] v1.2.3b — CryptoCompare News historique (PROCHAINE ÉTAPE)
│   └── [ ] v1.2.4 — Intégration news historique dans walk-forward
│
├── Juin
│   ├── [ ] v1.2b — Sentiment Historique : CryptoPanic + Santiment (~100€/mois)
│   └── [ ] v1.3.0 — Risk Engine
│
├── Juillet
│   └── [ ] v1.4.0 — Paper Trading
│
├── Août
│   ├── [ ] v1.2c — Modèle ML sentiment basique (classification titres news)
│   └── [ ] v1.5.0 — Production Ready (Docker, CI/CD, Auth)
│
├── Septembre
│   └── [ ] v1.6.0 — Multi-Assets (ETH, SOL... — seulement si BTC validé)
│
├── Octobre+
│   └── [ ] v2.0.0 — INFINI Mode Autonome
│
├── Q4 2026 — Q1 2027 : PHASE ML CONVERGENT (v3.0+) 🧠
│   ├── [ ] v3.0 — Dataset unifié + Feature Engineering (40-50h)
│   │   ├── Fusion données techniques + sentiment historique
│   │   ├── Lag features, rolling stats, interactions
│   │   └── Train/validation/test split walk-forward
│   │
│   ├── [ ] v3.1 — Modèles ML individuels (60-80h)
│   │   ├── Gradient Boosting (XGBoost/LightGBM)
│   │   ├── LSTM/GRU pour séries temporelles
│   │   ├── NLP sentiment (FinBERT fine-tuné)
│   │   └── Comparaison vs règles manuelles v1.0
│   │
│   ├── [ ] v3.2 — Modèle convergent fusion (50-60h)
│   │   ├── Stacking/Blending des modèles
│   │   ├── Détection de régime de marché
│   │   ├── Calibration de confiance
│   │   └── Intégration au DecisionService
│   │
│   └── [ ] v3.3 — Online learning + monitoring (50-60h)
│       ├── Apprentissage incrémental continu
│       ├── Drift detection + auto-retraining
│       ├── Dashboard ML (accuracy, features, alertes)
│       └── Fallback automatique vers rule-based
│
└── 2027+
    └── [ ] Exploitation, maintenance, évolutions continues
```

Cette timeline est indicative. Les dates dépendent du rythme de développement réel, du temps disponible, et des découvertes en cours de route. L'ordre des phases, en revanche, n'est pas négociable.

---

**Fin du document.**

