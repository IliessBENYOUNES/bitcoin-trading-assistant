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

| Bloc fonctionnel | Statut | Commentaire |
|------------------|--------|-------------|
| Collecte de données marché (CoinGecko) | ✅ Livré | Fetch async, upsert, gestion des erreurs |
| Stockage et alignement temporel | ✅ Livré | UTC, align_to_bucket, 4 timeframes |
| Resample multi-timeframe | ✅ Livré | 30m→1h et 4h→1d, idempotent |
| Scheduler automatique | ✅ Livré | Dual-jobs APScheduler, monitoring |
| Indicateurs techniques | ✅ Livré | RSI, MACD, SMA, Bollinger |
| Qualité des données (gaps, fraîcheur) | ✅ Livré | Backend complet, frontend chips |
| Dashboard frontend | ⚠️ Partiellement livré | Fonctionnel mais Dashboard.tsx corrompu |
| Tests backend | ✅ Livré | 110 tests, couverture large |
| Tests frontend | ❌ Non commencé | Aucun test E2E ni unitaire côté front |
| Interprétation des indicateurs | ❌ Non commencé | Pas de scoring, pas de synthèse |
| Signaux et scoring | ❌ Non commencé | — |
| Moteur de décision | ❌ Non commencé | — |
| Alertes et notifications | ❌ Non commencé | — |
| Multi-assets | ❌ Non commencé | Câblé pour (symbole paramétrable) |
| Backtesting | ❌ Non commencé | — |
| News / sentiment | ❌ Non commencé | — |
| Risk engine | ❌ Non commencé | — |
| Paper trading | ❌ Non commencé | — |
| Exécution automatisée | ❌ Non commencé | — |
| CI/CD | ❌ Non commencé | — |
| Docker / déploiement | ❌ Non commencé | — |
| Authentification | ❌ Non commencé | — |

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
├── Avril
│   ├── [✅] v0.6.0 — Dual jobs, tous timeframes
│   ├── [🔄] v0.7.0 — Consolidation produit (Phase 3)
│   └── [ ] v0.8.0 — Moteur de signaux (Phase 4)
│
├── Mai
│   ├── [ ] v0.9.0 — Moteur de décision (Phase 5)
│   └── [ ] v1.0.0 — Simulation / Backtesting (Phase 6)
│
├── Juin
│   ├── [ ] v1.1.0 — Alertes & Notifications (Phase 7)
│   └── [ ] v1.2.0 — Contexte & Sentiment (Phase 8)
│
├── Juillet
│   ├── [ ] v1.3.0 — Risk Engine (Phase 9)
│   └── [ ] v1.4.0 — Paper Trading (Phase 10)
│
├── Août-Septembre
│   ├── [ ] v2.0.0 — Exécution automatisée (Phase 11)
│   ├── [ ] v2.1.0 — UX produit final (Phase 12)
│   └── [ ] v2.2.0 — Déploiement production (Phase 13)
│
└── Octobre+
    └── [ ] Exploitation, maintenance, évolutions
```

Cette timeline est indicative. Les dates dépendent du rythme de développement réel, du temps disponible, et des découvertes en cours de route. L'ordre des phases, en revanche, n'est pas négociable.

---

**Fin du document.**

