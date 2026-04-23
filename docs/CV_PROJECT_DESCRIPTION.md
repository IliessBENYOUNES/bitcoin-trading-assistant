# 📄 Bitcoin Trading Assistant — Description CV (FR / EN)

> Document prêt à copier-coller dans un CV, un portfolio, LinkedIn ou une lettre de motivation.
> Deux versions complètes (française + anglaise) + variantes courtes.
> Dernière mise à jour : 19 avril 2026 — basé sur la version v2.0.30 du projet.

---

## ⚠️ Nature du projet — à lire avant toute utilisation

> **Ce projet est strictement personnel.** Il n'a été réalisé dans le cadre d'**aucune entreprise**, d'aucun client, d'aucune mission professionnelle ni d'aucun cursus académique. Il ne constitue **pas une expérience professionnelle salariée ou contractuelle**.
>
> Il s'agit d'un projet d'apprentissage, de recherche et d'expérimentation, conçu, développé, financé et maintenu intégralement par moi-même, sur mon temps libre, sans rémunération ni commande externe.
>
> Lors de son utilisation sur un CV ou un portfolio, il doit donc être présenté dans une rubrique dédiée : **« Projets personnels »**, **« Projets open-source / side projects »** ou **« Personal projects »** — et **jamais** dans la rubrique « Expériences professionnelles ».

> ⚠️ **Project nature — please read before any use.**
> This is a **strictly personal project**. It was **not** carried out for any company, client, professional engagement or academic program. It does **not** constitute paid or contractual professional experience.
>
> It is a learning, research and experimentation project, fully designed, developed, funded and maintained by myself, on my own time, with no compensation or external commission.
>
> When listed on a CV or portfolio, it must therefore appear in a dedicated section such as **"Personal Projects"**, **"Side Projects"** or **"Open-source projects"** — and **never** in the "Professional Experience" section.

---

## 📊 Chiffres clés du projet

| Métrique | Valeur |
|----------|--------|
| Backend Python (LOC) | ~24 466 |
| Frontend TS/TSX (LOC) | ~14 236 |
| **Total** | **~38 700 LOC** |
| Fichiers Python (`backend/app`) | 90 |
| Fichiers TS/TSX (`frontend/src`) | 46 |
| Fichiers de tests | 40 |
| **Tests Pytest passants** | **1 773** |
| Versions livrées | 30 itérations majeures (v2.0.0 → v2.0.30) |
| Trades analysés (audit statistique) | 831 + 46 |
| Période de développement | 2025 – 2026 |

---

## 🇫🇷 Version française — longue (CV / portfolio détaillé)

### **Bitcoin Trading Assistant (BTC Insight)** — Projet personnel full-stack
*2025 – 2026 · Python / FastAPI · React / TypeScript · PostgreSQL · 38k+ LOC · 1 773 tests automatisés*

Conception et développement d'une plateforme complète d'aide à la décision et de **paper trading** sur le marché Bitcoin, intégrant ingestion de données temps réel, indicateurs techniques, moteur de signaux, simulation multi-stratégie avec **gestion réaliste des frais et du slippage**, et boucle d'amélioration statistique pilotée par les données.

**Stack technique**
- **Backend :** FastAPI 0.109, SQLAlchemy 2.0, Python 3.12, APScheduler, Pytest
- **Frontend :** React 18, TypeScript 5, Vite 5, MUI 5, Framer Motion
- **Données :** PostgreSQL (prod), SQLite (tests), WebSocket Binance + REST fallback, RSS news + analyse de sentiment
- **Architecture :** services métier découplés, schémas Pydantic, hooks React typés, git worktree pour fork expérimental isolé

**Réalisations clés**
- **Pipeline temps réel** : ingestion OHLCV Binance (CoinGecko fallback), agrégation sur **14 timeframes**, calcul d'indicateurs (RSI, MACD, SMA, Bollinger, StochRSI, ATR, VWAP) avec scheduler tolérant aux pannes
- **Moteur de décision rule-based** avec score composite, 4 profils paramétrables (conservative / balanced / aggressive / scalping), filtres structurels (price position, range/ATR, volume, micro-tendance) et gates économiques (rejet pré-trade si gain attendu < 2× frais)
- **Paper trading multi-slot** : exécution simultanée de plusieurs stratégies avec capital partagé, levier auto, **modèle de coûts Binance réaliste** (0,31 % round-trip), 8 mécanismes de sortie hiérarchisés (SL/TP, trailing relatif, breakeven, micro-stop, gain erosion, candle reversal, stale exit, signal contraire)
- **Couche de "vérité" runtime** : journal tick-par-tick auditable, corrélation trade ↔ mouvement BTC réel, détection de sorties prématurées, export enrichi, mode autonome headless
- **Backtesting & time-travel walk-forward** sur historique, audit comparatif de 2 moteurs (master + fork `experiment/v2-fees`) sur **831 + 46 trades** avec corrélations Pearson, distributions et heatmaps score × durée — identification de 13 insights statistiques traduits en gates de production (heures bloquées 13–16 UTC, plafond de score, range/ATR minimum, fee-multiple breakeven)
- **Système d'alertes & news** : CRUD alertes avec moteur d'évaluation, collecte RSS multi-source, scoring de sentiment et d'impact
- **Frontend riche** : dashboard temps réel avec mini-chart 1 m, panneaux signaux/alertes/news/diagnostic, journal d'évaluation par profil, certification serveur du profil actif, mode low-bandwidth
- **Qualité logicielle** : **1 773 tests Pytest passants**, `tsc --noEmit` zéro erreur, conventional commits, traçabilité d'exigences (FR-xxx), 30 versions documentées avec changelog rigoureux
- **Méthodologie data-driven** : chaque itération du moteur (~30) part d'une analyse statistique du journal de trades précédent ; les corrections sont des hypothèses falsifiables validées par re-test

**Compétences mises en œuvre :** architecture full-stack, conception API REST, modélisation domain-driven, ingénierie quantitative (analyse statistique, gestion du risque, modélisation de coûts), TDD, observabilité, refactoring continu, documentation technique soutenue.

---

## 🇫🇷 Version française — courte (CV 1 page)

### **Bitcoin Trading Assistant** — *Projet personnel full-stack* · 2025 – 2026
*Python / FastAPI · React / TypeScript · PostgreSQL · 38k+ LOC · 1 773 tests*

Plateforme complète d'aide à la décision et de paper trading sur le marché Bitcoin avec gestion réaliste des frais Binance.

- Pipeline temps réel : ingestion Binance (WebSocket + REST fallback), agrégation **14 timeframes**, indicateurs (RSI, MACD, Bollinger, ATR, VWAP)
- Moteur de décision rule-based avec score composite, 4 profils, gates économiques pré-trade et filtres structurels
- Paper trading multi-slot avec **modèle de coûts Binance réaliste** (0,31 % round-trip) et 8 mécanismes de sortie hiérarchisés
- Backtesting walk-forward, audit statistique de 877 trades (Pearson, heatmaps) → 13 gates de production data-driven
- Alertes, news RSS + sentiment, mode autonome headless, frontend MUI temps réel
- **1 773 tests Pytest**, `tsc` zéro erreur, 30 versions documentées, conventional commits, traçabilité d'exigences

---

## 🇬🇧 English version — long (CV / detailed portfolio)

### **Bitcoin Trading Assistant (BTC Insight)** — Personal full-stack project
*2025 – 2026 · Python / FastAPI · React / TypeScript · PostgreSQL · 38k+ LOC · 1,773 automated tests*

Designed and built a complete Bitcoin **decision-support and paper-trading platform**, covering real-time data ingestion, technical indicators, signal engine, multi-strategy simulation with **realistic fee and slippage modeling**, and a data-driven statistical improvement loop.

**Tech stack**
- **Backend:** FastAPI 0.109, SQLAlchemy 2.0, Python 3.12, APScheduler, Pytest
- **Frontend:** React 18, TypeScript 5, Vite 5, MUI 5, Framer Motion
- **Data:** PostgreSQL (prod), SQLite (tests), Binance WebSocket + REST fallback, RSS news pipeline with sentiment analysis
- **Architecture:** decoupled service layer, Pydantic schemas, typed React hooks, git worktree for an isolated experimental fork

**Key achievements**
- **Real-time pipeline:** OHLCV ingestion from Binance (CoinGecko fallback), aggregation across **14 timeframes**, indicator computation (RSI, MACD, SMA, Bollinger, StochRSI, ATR, VWAP) with a fault-tolerant scheduler
- **Rule-based decision engine** with composite scoring, four configurable profiles (conservative / balanced / aggressive / scalping), structural filters (price position, range/ATR, volume, micro-trend) and **economic pre-trade gates** (rejects trades whose expected gain is below 2× fees)
- **Multi-slot paper trading:** concurrent strategy execution sharing capital, auto-leverage, **realistic Binance cost model** (0.31% round-trip), 8 prioritized exit mechanisms (SL/TP, relative trailing, breakeven, micro-stop, gain erosion, candle reversal, stale exit, contrary signal)
- **Runtime "truth" layer:** auditable tick-by-tick journal, correlation between each trade and actual BTC movement, premature-exit detection, enriched export, headless autonomous mode
- **Backtesting & walk-forward time-travel** over historical data; comparative audit of two engines (master + `experiment/v2-fees` fork) over **831 + 46 trades** using Pearson correlations, distributions and score × duration heatmaps — produced 13 statistical insights translated into production gates (blocked UTC hours 13–16, score cap, min range/ATR, breakeven fee-multiple)
- **Alerts & news subsystem:** alert CRUD with evaluation engine, multi-source RSS collection, sentiment and impact scoring
- **Rich frontend:** real-time dashboard with 1-minute mini-chart, signal/alert/news/diagnostic panels, per-profile evaluation journal, server-side profile certification badge, low-bandwidth mode
- **Engineering quality:** **1,773 passing Pytest cases**, zero-error `tsc --noEmit`, conventional commits, requirement traceability (FR-xxx), 30 documented versions with a strict changelog
- **Data-driven methodology:** every engine iteration (~30) starts from a statistical analysis of the previous trading journal; fixes are framed as falsifiable hypotheses re-validated by tests

**Skills demonstrated:** full-stack architecture, REST API design, domain-driven modeling, quantitative engineering (statistical analysis, risk management, cost modeling), TDD, observability, continuous refactoring, sustained technical documentation.

---

## 🇬🇧 English version — short (1-page CV)

### **Bitcoin Trading Assistant** — *Personal full-stack project* · 2025 – 2026
*Python / FastAPI · React / TypeScript · PostgreSQL · 38k+ LOC · 1,773 tests*

End-to-end Bitcoin decision-support and paper-trading platform with realistic Binance fee modeling.

- Real-time pipeline: Binance ingestion (WebSocket + REST fallback), aggregation across **14 timeframes**, indicators (RSI, MACD, Bollinger, ATR, VWAP)
- Rule-based decision engine with composite scoring, 4 configurable profiles, economic pre-trade gates and structural filters
- Multi-slot paper trading with **realistic Binance cost model** (0.31% round-trip) and 8 prioritized exit mechanisms
- Walk-forward backtesting and statistical audit of 877 trades (Pearson, heatmaps) → 13 data-driven production gates
- Alerts, RSS news + sentiment, headless autonomous mode, real-time MUI frontend
- **1,773 Pytest cases**, zero-error `tsc`, 30 documented versions, conventional commits, requirement traceability

---

## 💼 Variante LinkedIn / "Featured project" (FR)

🚀 **Bitcoin Trading Assistant** — Plateforme full-stack de paper trading BTC

J'ai construit de A à Z une application complète pour analyser le marché Bitcoin et simuler des stratégies de trading dans des conditions réalistes (frais Binance, slippage, levier).

🔧 **Stack :** FastAPI · SQLAlchemy · React · TypeScript · PostgreSQL
📊 **Échelle :** ~38 700 LOC · 1 773 tests Pytest · 30 versions livrées
🎯 **Particularité :** chaque itération du moteur est pilotée par une analyse statistique des trades précédents (corrélations Pearson, heatmaps, distributions) — pas d'intuition, que de la donnée.

Modules : ingestion temps réel, indicateurs techniques, moteur de décision rule-based, paper trading multi-slot, backtesting walk-forward, alertes, news + sentiment, mode autonome headless.

#Python #FastAPI #React #TypeScript #Trading #DataEngineering #FullStack

---

## 💼 LinkedIn / "Featured project" (EN)

🚀 **Bitcoin Trading Assistant** — Full-stack BTC paper-trading platform

End-to-end personal project: a complete app to analyze the Bitcoin market and simulate trading strategies under realistic conditions (Binance fees, slippage, leverage).

🔧 **Stack:** FastAPI · SQLAlchemy · React · TypeScript · PostgreSQL
📊 **Scale:** ~38,700 LOC · 1,773 Pytest cases · 30 shipped versions
🎯 **What makes it different:** every engine iteration is driven by a statistical analysis of the previous trade log (Pearson correlations, heatmaps, distributions) — no gut feeling, just data.

Modules: real-time ingestion, technical indicators, rule-based decision engine, multi-slot paper trading, walk-forward backtesting, alerts, news + sentiment, headless autonomous mode.

#Python #FastAPI #React #TypeScript #Trading #DataEngineering #FullStack

---

## 🏷️ Tags / mots-clés (utiles pour ATS et SEO)

Python, FastAPI, SQLAlchemy, Pydantic, Pytest, APScheduler, asyncio, REST API, WebSocket, PostgreSQL, SQLite, React, TypeScript, Vite, MUI, Material-UI, hooks, full-stack, quantitative trading, paper trading, backtesting, walk-forward, technical indicators, RSI, MACD, Bollinger, ATR, VWAP, signal engine, risk management, Binance API, CoinGecko, RSS, sentiment analysis, statistical analysis, Pearson correlation, data-driven, TDD, conventional commits, requirement traceability, observability, fault tolerance, git worktree.

---

*Document généré pour usage CV / portfolio. Adapter le ton et la longueur selon la cible (recruteur tech vs RH généraliste vs startup vs grand groupe).*

