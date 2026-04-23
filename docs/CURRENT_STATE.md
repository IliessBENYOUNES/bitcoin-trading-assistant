# 📊 Current State — Bitcoin Trading Assistant

> **Dernire mise  jour :** 23 avril 2026
> **Version :** v2.0.31-fees-batch2
> **Branche :** `experiment/v2-fees-and-1m`
> **Dernier commit :** fix(multi-strategy): F3 bug micro_sl=0.0 + F4 trailing min_peak 2x fees v2.0.31-fees-batch2

---

## 1. Vue d'ensemble

Bitcoin Trading Assistant (alias **BTC Insight → INFINI v1**) est un outil d'aide à la lecture et à la **décision** sur le marché Bitcoin. Il collecte des données OHLCV depuis **Binance** (CoinGecko fallback), les agrège sur **14 timeframes**, calcule des indicateurs techniques, produit des signaux avec score composite, évalue des alertes, collecte des news avec analyse de sentiment, génère des recommandations explicables, valide empiriquement via backtesting et time-travel, gère le risque (SL/TP, kill switch), et simule le trading en temps réel via un paper trading multi-slot avec profils, levier auto, diagnostic, et trailing stop.

| Élément | Valeur |
|---------|--------|
| Version courante | **v2.0.31-fees-batch2** |
| Backend | FastAPI 0.109 + SQLAlchemy 2.0 + Python 3.12 |
| Frontend | React 18 + TypeScript 5 + Vite 5 + MUI 5 + Framer Motion |
| Base de données | PostgreSQL (prod) / SQLite (tests) |
| Tests backend | **1856 tests passing**, 1 skipped, 0 failed |
| Frontend build | **tsc + vite build** sans erreur |
| Phase courante | **v2.0.31-fees-batch2 livr** €” F3 bug micro_sl=0.0 + F4 trailing min_peak 2x fees (multi-strategy) |

### ⚠️ État de maturité honnête

L'Étape 2 (INFINI v1) est **fonctionnellement très avancée** côté simulation et observabilité. Le **pivot stratégique v2.0.0** a posé les fondations d'un moteur économiquement viable.

**Ce qui est solide :**
- Moteur de décision rule-based fonctionnel
- **[v2.0.0] Slot aggressive sanctuarisé** comme moteur principal de valeur
- **[v2.0.1] Slot aggressive rendu vivant** — Timeframe 4h→1h (4× plus réactif), buy_threshold 25→20, sell_threshold 20→15. Le slot ne change pas d'identité (TP 1%, SL 1%, durée 48h, pas de trailing, pas de gate économique) mais franchit enfin les seuils d'entrée en runtime. 13 tests dédiés.
- **[v2.0.2] Corrélation runtime BTC** — Service `RuntimeCorrelationService` qui corrèle chaque trade avec le mouvement BTC réel : tendance à l'entrée, mouvement pendant le trade, mouvement post-sortie, détection de sorties prématurées (stale + BTC favorable après), efficacité de capture. Endpoint `GET /audit/runtime-correlation`.
- **[v2.0.2] Learning enrichi contexte BTC** — 5 nouvelles colonnes sur `LearningSignal` : `btc_trend_at_entry`, `btc_move_during_pct`, `btc_move_after_exit_pct`, `missed_favorable_move`, `capture_efficiency_pct`. Le learning sait maintenant si un trade a été fermé trop tôt par rapport au mouvement BTC réel.
- **[v2.0.0] Economic viability gate** — refuse les trades scalping non-viables après frais
- **[v2.0.0] Momentum fade restricted** — ne sort que si le pic dépasse le seuil d'amplitude ET que la sortie est net-positive
- **[v2.0.0] Structural proofs gate** — exige ≥2 preuves structurelles (volume, micro-trend, price_position, range) pour entrer en scalping
- **[v2.0.0] Scoring refondu** — oscillateurs (Bollinger, StochRSI) dégradés à 0.3x en tendance, price_position boosté à 1.4x
- **[v2.0.3] Paramètres scalping recalibrés** — buy_threshold 30 (was 25), min_score 30 (was 25), trailing activation 0.15% (was 0.20%), short_min_score 30 (was 25)
- **[v2.0.4] Gate micro-tendance assoupli** — `min_micro_trend_long` abaissé de 2→1. L'audit post-v2.0.3 montre 966/966 ticks scalping (100%) bloqués par `micro_trend_insufficient` (mt_score=-2, decision_score=65). Le gate à mt≥2 exigeait une tendance confirmée, empêchant toute entrée. mt≥1 = début de reprise suffisant, mt≤0 toujours bloqué.
- **[v2.0.6] Gate micro-tendance DÉSACTIVÉ** — `min_micro_trend_long` abaissé de 1→0. L'audit post-v2.0.4 montre 135/135 ticks scalping (100%) encore bloqués par `micro_trend_insufficient` (mt_score=-2, decision_score=65, market_quality=59). Le gate à mt≥1 restait trop restrictif dans les phases latérales/baissières. Désactivé (0 = code skip), la protection micro-trend reste via structural_proofs (mt≥3 = 1 preuve sur 4).
- **[v2.0.6] Certification profil UI** — Bandeau vert `🔒 Profil certifié par le serveur` affichant le profil réellement actif côté backend (synchronisé via `status.account.active_profile` à chaque poll). Alerte orange clignotante si désynchronisation détectée.
- **[v2.0.6] Timer de position UI** — Chronomètre live `hh:mm:ss` sur chaque position ouverte, basé sur `entry_ts`, rafraîchi chaque seconde.
- **[v2.0.7] Sorties scalping recalibrées pour marchés en range** — L'audit runtime du premier trade scalping débloqué révèle que le peak atteint 0.14% (juste sous l'activation trailing à 0.15%), le trailing ne s'active JAMAIS, et le stale exit à 15 min laisse fondre les gains. Corrections : stale 15→5 min (3× plus rapide), stale négatif 5→2 min, trailing activation 0.15→0.10% (protège les petits gains), trail 0.10→0.06% (moins de give-back). 6 tests dédiés.
- **[v2.0.8] FIX CRITIQUE : Trailing stop prioritaire + breakeven stop** — BUG : le stale_negative_exit (2 min) était vérifié AVANT le trailing stop dans le code. Quand une position gagnante (peak > activation 0.10%) retombait en négatif, le stale fermait en perte au lieu du trailing qui aurait fermé en profit. Fix : (1) Réordonnancement — trailing stop vérifié AVANT stale exit (priorité maximale), (2) Breakeven stop — nouveau filet de sécurité : si peak ≥ activation/2 (0.05%) et PnL retombe ≤ 0%, fermeture immédiate au breakeven au lieu d'attendre le stale. Le stale ne gère plus que les positions jamais profitables. 4 tests dédiés.
- **[v2.0.8] SHORTS BIDIRECTIONNELS** — Le robot n'ouvrait AUCUN short car : (1) le reversal exigeait 2 signaux overbought (RSI ≥ 70 + StochRSI ≥ 80) — quasi impossible en range avec RSI à 55, (2) le filtre `short_min_score` exigeait abs(score) ≥ 30 pour un trade CONTRARIAN — absurde car un score positif CONFIRME le surachat. Fix : (1) Seuil reversal abaissé de 2→1 signal, (2) Nouveau signal "majorité bearish" (si ≥2 règles bearish > bullish), (3) `short_min_score` supprimé pour les reversals (gardé pour les shorts non-reversal). Le robot peut maintenant alterner long/short en range. 7 tests dédiés.
- **[v2.0.9] TRAILING STOP RELATIF** — L'ancien trailing absolu (recul fixe de 0.06%) perdait 50-60% du gain sur les petits peaks (0.10-0.12%). Le nouveau trailing relatif (`trailing_stop_drop_ratio=0.30`) sort quand le gain a reculé de 30% par rapport à son pic, quelle que soit la taille du gain. Peak 0.12% → exit à 0.084% (garde 70%). Peak 0.50% → exit à 0.35% (garde 70%). Plus le gain est gros, plus le trailing tolère de recul en absolu — fini les sorties prématurées qui grignotaient les gains. 5 tests dédiés.
- **[v2.0.10] DOWNTREND PROTECTION** — Les données montrent que 7/33 trades entrent LONG pendant que le BTC descend, perdant -$10.44 en stale exits. Le score technique de 65 est en retard (indicateurs 15min lagging) et reste bullish pendant le pullback. Corrections : (1) **Veto bearish** : si `micro_trend_score < 0` et direction = long (non-reversal), le trade est bloqué. (2) **Reversal enrichi** : `micro_trend_score ≤ -2` injecte un signal overbought dans le reversal check → favorise les SHORT contrarians au lieu des LONG perdants. (3) **mq_data calculé AVANT le reversal** : le market quality est maintenant évalué en premier pour alimenter le reversal et le veto. 11 tests dédiés.
- **[v2.0.11] ANTI-CHURN REVERSAL + COOLDOWN RÉDUIT** — Deux problèmes runtime identifiés sur 30 trades : (1) **Boucle reversal-churn** : les shorts `mean_reversion_short` étaient fermés par signal contraire après ~50sec car le même score bullish (+66) qui déclenchait le reversal fermait aussi le trade (seuil 30). Fix : pour les reversals, le signal contraire ne ferme que si le score a AUGMENTÉ au-delà du score d'entrée (+1). (2) **Cooldown trop long** : le cooldown de 2min empêchait de capter le prochain signal après un renversement. Fix : `cooldown_minutes` 2→1, `max_cooldown_minutes` 10→5, `STALE_NEGATIVE_FLOOR` 4→2 (le `bearish_veto` v2.0.10 protège en amont). 12 tests dédiés.
- **[v2.0.12] GAIN EROSION STOP** — Protection des petits gains (sous le seuil d'activation du trailing). Le trailing ne s'active qu'à 0.04% (~$1). Les gains entre $0 et $1 fondaient sans protection jusqu'au stale négatif (2 min) qui fermait en perte. Le gain erosion stop (`gain_erosion_ratio=0.30`) sort dès que le gain a perdu 30% de son pic, AVANT que le gain retombe à 0% (breakeven). Conditions : peak ≥ 0.01% (~$0.25) ET peak < activation trailing (0.04%). Au-dessus du trailing, le trailing relatif (15% drop) prend le relais. Peak +$0.60 → exit si gain < $0.42 (érosion > 30%). Sauve $0.42 au lieu de -$1.20. 18 tests dédiés.
- **[v2.0.13] TICK MOMENTUM CONFIRMATION** — Gate d'entrée par micro price-action. Analyse les ticks récents (~10 sec) pour confirmer que le prix va dans la direction du trade AVANT d'ouvrir. SHORT → le prix doit être en baisse. LONG → le prix doit être en hausse. Élimine les shorts qui entrent pendant que le prix monte et restent négatifs 2 min jusqu'au stale exit. Nouveau service `TickMomentumService` avec buffer circulaire en mémoire. Remplace conceptuellement le cooldown aveugle : on ne bloque pas par le TEMPS mais par la DIRECTION du prix. 20 tests dédiés.
- **[v2.0.14] CANDLE DIRECTION OVERRIDE** — En mode scalping, la direction du trade est déterminée par la direction RÉELLE du prix sur les 30 dernières secondes (bougie verte → LONG, bougie rouge → SHORT), au lieu de suivre le score technique lagging 15 min. Élimine le biais 100% short quand les indicateurs restent bearish en marché ranging. Le score technique est gardé comme filtre de qualité (|score| >= 10 quand override actif). Le bearish_veto et le scalping_reversal sont SKIPPÉS car la bougie EST la confirmation de direction. Le check "attendre" est BYPASSÉ : même si les indicateurs 15 min sont indécis, le prix bouge et on entre dans sa direction. 9 tests dédiés.
- **[v2.0.15] CANDLE DIRECTION INDICATOR (UI)** — Nouveau champ `entry_candle_direction` ("green"/"red"/null) stocké sur chaque trade à l'ouverture de position. Le frontend affiche un dot coloré (🟢/🔴) avec tooltip à côté de chaque position ouverte ET dans le journal des trades. Le tooltip indique la cohérence direction/bougie (✅ cohérent ou ⚠️ incohérent). En scalping override, la couleur vient du tick momentum. Pour les autres profils, le `micro_trend_score` du market quality est utilisé comme proxy. 7 tests dédiés.
- **[v2.0.15] REST PRICE FALLBACK** — Le hook `useLivePrice` ajoute un fallback REST API (`/market/price`) quand le WebSocket Binance ne se connecte pas dans les 5 secondes. Polling toutes les 10s via Binance REST (même source que le backend). Le PriceTicker affiche "REST" en orange au lieu de "LIVE" en rouge quand le fallback est actif. Le footer affiche "Mode REST (prix ~10s)". Corrige le problème de prix stale (~5 min de retard) quand le WebSocket est inaccessible.
- **[v2.0.17] CANDLE DIRECTION LEARNING PATTERNS** — Le LearningService analyse la cohérence entrée→sortie des bougies (4 catégories : same_aligned, same_counter, reversed_favor, reversed_against). Méta-pattern même couleur vs changement. Croisement durée × cohérence. Suggestions automatiques (réduire stale_negative si reversed_against dominent, relever min_micro_trend_long si entrée contre-tendance est pire). 9 tests dédiés.
- **[v2.0.18] CANDLE REVERSAL EXIT** — Nouveau type de sortie active `closed_candle_reversal`. Quand la couleur de la bougie s'inverse par rapport à l'entrée (green→red pour un long, red→green pour un short) et persiste pendant ≥3 secondes, la position est fermée immédiatement. Basé sur l'observation empirique que les trades profitables gardent la même couleur de pastille, tandis que les perdants changent de couleur. Vérifié APRÈS le trailing/breakeven/gain erosion et AVANT le stale exit. 12 tests dédiés.
- **[v2.0.18] REVERSAL DELAY TRACKING** — Nouveau champ `reversal_delay_seconds` sur `PaperTrade` et `LearningSignal`. Mesure le temps entre le changement de couleur de bougie et la fermeture effective. Permet au modèle ML d'apprendre la vitesse de réaction optimale (fast <5s vs slow ≥5s). Pattern 9 dans le learning : analyse statistique des délais de reversal et comparaison sortie reversal vs sortie normale.
- **[v2.0.18] UI LAYOUT RESTRUCTURÉ** — TAB 2 (Trading) restructuré : Risk Panel en bandeau compact pleine largeur en haut (replié par défaut, toujours accessible), Paper Trading en pleine largeur en dessous, Journal et Diagnostic pleine largeur. Plus de layout 42%/58% côte à côte.
- **[v2.0.19] AGGRESSIVE SLOT PROTECTION** — L'analyse du run de 33 trades a révélé que le slot aggressive (trade #597) a perdu -$10.32 en dérivant 3h sans aucune protection trailing/gain_erosion. Corrections : (1) `stale_negative_exit_minutes=60` (vs 180 héritée du stale normal) → coupe les positions perdantes après 1h max, (2) `trailing_stop_activation_pct=0.15` + `trailing_stop_drop_ratio=0.30` → protège 70% des gains intraday, (3) `gain_erosion_ratio=0.50` → coupe si les petits gains fondent de 50%.
- **[v2.0.19] CANDLE REVERSAL FIX** — La feature v2.0.18 (candle reversal exit) n'a jamais déclenché en production (0/32 trades). Cause : `detect_direction()` utilisait `MIN_MOVE_PCT=0.002%` ($1.42) avec une fenêtre de 15s (~3 ticks), trop insensible pour les micro-mouvements scalping. Fix : (1) `detect_direction()` accepte maintenant un `min_move_pct` personnalisable, (2) `check_candle_reversal` utilise un seuil réduit de 0.001% ($0.71), (3) fenêtre élargie de 15→30 secondes pour capturer plus de ticks.
- **[v2.0.19] OVERRIDE ANTI-CHURN** — Les trades ouverts via tick momentum override (entry_reason="vendre") étaient immédiatement fermés par signal contraire car le score bullish (+66) > seuil de sortie (30). Fix : (1) Entry reason préfixé `tick_override_{direction}`, (2) logique `is_reversal` étendue pour protéger les override trades comme les mean_reversion (seuil de sortie relevé à abs(score_entrée)+1).
- **[v2.0.20] FIX BIAIS 100% SHORT SCALPING** — Le tick momentum override (v2.0.14) était censé éliminer le biais short en suivant la direction réelle du prix. Mais le gate **structural proofs** (v2.0.0) bloquait TOUS les LONGs de l'override car il vérifiait `micro_trend_score ≥ 3` — un indicateur **lagging 15 min** négatif en marché bearish. L'override détectait "prix monte → LONG" mais les structural proofs disaient "micro_trend bearish → pas de LONG". Résultat : seuls les SHORTs passaient (micro_trend négatif = proof pour short). Fix : bypass complet des structural proofs quand `tm_override_active=True`. La direction réelle du prix (30 sec) EST la preuve structurelle. Les protections restantes (economic gate, market quality, min_score, risk engine) suffisent. 2 tests dédiés.
- **[v2.0.22] SAS D'ENTRÉE SÉCURISÉ (ENTRY AIRLOCK)** — Quand tous les gates passent, au lieu d'ouvrir immédiatement la position, le système entre dans un "SAS" (sas d'entrée). Pendant ~10-15 secondes, le prix est observé virtuellement (comme si on avait ouvert). Si le PnL virtuel reste négatif → l'entrée est annulée, on ne perd RIEN. Si le PnL virtuel devient positif et y reste → l'entrée réelle est confirmée au prix courant. **Range caution** : si le prix est en haut de range (>70%) et qu'on veut un LONG, ou en bas de range (<30%) et qu'on veut un SHORT, le SAS rejette immédiatement dès le premier tick négatif (position structurellement dangereuse). Nouveau service `EntrySasService` (in-memory, pattern identique à `TickMomentumService`). Résout le problème catastrophique du trade #620 (-$15.27 en 36s) : le PnL virtuel serait resté négatif → jamais ouvert. 39 tests dédiés.
- **[v2.0.23+v2.0.25] MICRO STOP LOSS** — Garde-fou inconditionnel : si le PnL latent dépasse un seuil négatif, sortie IMMÉDIATE. [v2.0.25] Recalibré 0.01%→0.05% après analyse de 345 trades : à 0.01%, le micro SL tuait 130 trades (100% perdants, -$59.44). Le seuil de 0.05% (-$1.25 sur $2500) laisse 1-2 ticks de respiration tout en restant 4× plus serré que le SL classique.
- **[v2.0.24+v2.0.25] COOLDOWN RECALIBRÉ** — `max_trades_per_day` 30→999 (illimité). [v2.0.25] Cooldown relevé après analyse de 345 trades : les boucles micro SL→re-entry créaient du churn destructeur (gap médian 64s). `cooldown_minutes` 0.17→1.0, `min_cooldown` 0.17→0.5, `max_cooldown` 1.0→3.0.
- **[v2.0.25] SL/TP STOP-LIMIT** — Le SL/TP exécute désormais au prix de l'ordre au lieu du prix courant. Avant, des gaps entre ticks (5 sec) causaient des pertes 4× supérieures au SL attendu (trade #629 : -$21.76 vs SL -0.20%). Perte max par SL bornée à loss_cut_pct.
- **[v2.0.26] TREND ALIGNMENT FILTER** — Bloque les SHORTs via tick_override quand le score technique est fortement bullish (score > 50). L'analyse de 92 trades (v2.0.25) montre que les shorts scalping perdent -$8.93 (47% WR) quand le score est à +64/+65 et BTC monte globalement. Le tick_override ouvre un short sur bougie rouge 30s, mais le marché bullish fait remonter le prix → le short est fermé en perte par "signal contraire". Le filtre ne bloque PAS les shorts non-override (mean_reversion). Seuil configurable via `trend_alignment_score_threshold` (default None, 50 pour scalping). 8 tests dédiés.
- **[v2.0.27] TREND ALIGNMENT SYMÉTRIQUE** — Le filtre v2.0.26 ne bloquait que les SHORTs en marché bullish. Ajout du filtre miroir : les LONGs via tick_override sont maintenant aussi bloqués quand le score est fortement bearish (score < -threshold). Une bougie verte 30s en tendance baissière est un faux signal. Le filtre est bidirectionnel : SHORT bloqué quand score > +50, LONG bloqué quand score < -50. 5 tests supplémentaires (total 12).
- **[v2.0.27] MINI CHART BTC 1M** — Nouveau graphique compact en chandeliers 1 minute sur l'onglet Trading. Affiche les 60 dernières bougies (1h) avec focus auto sur les 15 dernières minutes. Données directement depuis Binance REST (polling 30s), mise à jour en temps réel via WebSocket live price. Désactivé automatiquement en mode low-bandwidth ou hors de l'onglet Trading. Composant `MiniChart.tsx` + hook `useMiniCandles.ts`.
- **[v2.0.28] REFONTE PROTECTIONS AGGRESSIVE** — L'analyse du run v2.0.27 (58 trades) révèle que le slot aggressive n'avait AUCUNE protection pré-entrée (pas de SAS, pas de micro SL, pas de smart cooldown). Le trade #1108 a perdu 100% d'un pic de 0.705%, le trade #1102 a perdu -$6.60. Corrections : (1) **SAS d'entrée** ajouté (10s observation, 5s positif requis) — filtre les mauvaises entrées. (2) **Micro SL à 0.15%** ($3.75 max) — coupe les retournements post-entrée au lieu d'attendre le SL swing à -1.0% ($25). (3) **Smart cooldown** (min 1 min, max 5 min) — adaptatif selon le résultat du trade précédent. (4) **Trailing recalibré** : activation 0.15→0.25% (laisse les swings se développer), drop ratio 0.30→0.20 (protège 80% au lieu de 70%). (5) **Gain erosion assoupli** 0.50→0.70 (les swings oscillent naturellement). (6) **Cooldown réduit** 15→5 min (plus d'opportunités intraday).
- **[v2.0.28] COOLDOWN SCALPING OPTIMISÉ** — L'analyse des 3 runs montre que le cooldown de 1 min (v2.0.25) est devenu disproportionné maintenant que le micro SL est à 0.05% (plus 0.01%). Les boucles churn qui justifiaient le cooldown long sont cassées par le nouveau micro SL. Corrections : `cooldown_minutes` 1.0→0.5 (30s), `min_cooldown` 0.5→0.25 (15s), `max_cooldown` 3.0→2.0 (2 min).
- **[v2.0.28] GAIN EROSION RECALIBRÉ** — (1) Seuil minimum global relevé 0.01%→0.02% ($0.50) — les peaks < $0.50 sont du bruit de tick qui polluait le journal avec des exits à +$0.12-$0.18. (2) Ratio scalping assoupli 0.30→0.40 — donne plus de marge aux petits gains pour se développer vers le trailing (0.04%).
- **[v2.0.4] Export enrichi** — Service `EnrichedExportService` + endpoint `GET /audit/enriched-export`. Export tick-par-tick avec : prix BTC, variation %, décision moteur, score, raison de non-trade, position ouverte/fermée, PnL, market quality. Inclut ventilation des refus par gate + détection des tendances BTC ratées.
- **[v2.0.4] Learning runtime** — Nouvelle méthode `LearningService.learn_from_runtime()` + endpoint `POST /learning/learn-runtime`. Analyse les TickActivityLog (pas les trades fermés) pour identifier les gates sur-bloquants et proposer des assouplissements en mode shadow. Suggestions 15 (micro-trend dominant) et 16 (gate unique > 70%).
- **[v2.0.3-fix] Auto-activation paper trading** — L'endpoint `POST /paper/tick` auto-active le compte si inactif. Le frontend (`doAutoTick`, `manualTick`, `handleStartAuto`) fait aussi du self-healing : si le tick retourne "inactive", activation automatique + retry. L'utilisateur final n'a plus jamais besoin de faire de requête POST manuelle.
- **[v2.0.0-fix] Stale exit corrigé** — Le seuil de stagnation des profils tight utilise désormais `trailing_stop_activation_pct` (0.20%) au lieu de `profit_take_pct` (0.8%). Un trade à +0.46% n'est plus fermé comme "stagnant" — le trailing stop gère la sortie.
- **[v2.0.0-fix] Multi-slot préservé après full reset** — `max_open_positions` default passé de 1 à 3 dans `FullResetRequest` et `PaperAccountCreate`. Avant, un full reset recréait le compte en mono-position, empêchant le slot aggressive de tourner. Désormais, le multi-slot est toujours actif par défaut.
- **[v2.0.5-fix] Préservation du profil actif lors du reset** — INCIDENT GRAVE : le full reset écrasait `active_profile` vers "conservative" (default SQLAlchemy). Corrigé : le profil est capturé avant la purge et restauré dans le nouveau compte. La route autonomous/start force le profil demandé. Le frontend restaure le profil après reset. 11 tests de non-régression ajoutés.
- Backtesting et time-travel walk-forward
- Paper trading multi-slot avec profils et levier auto
- Diagnostic fréquence et opportunités manquées
- **Modèle de coûts de trading** (presets optimistic/realistic/stressed)
- **Audit de vérité** (expectancy nette, drawdown vérifié, impact levier/trailing, verdict)
- **Audit scalping dédié** (exit distribution, trailing, score saturation, long/short, levier)
- **Scalping recalibré v1.8.1** (trailing stop élargi, scoring plus sélectif, levier conservateur, short amélioré)
- **Protection Reset UI** (bouton Full Reset séparé avec confirmation typed "RESET")
- **Gate formelle v2.0** (8 critères objectifs, status READY/PARTIAL/NOT_READY)
- **[v1.9] Campagnes de validation (PaperRun)** — démarrer/arrêter/comparer des runs avec métriques brut+net
- **[v1.9] Smart Cooldown** — cooldown contextuel (réduit après stale/trailing flat, allongé après SL/perte)
- **[v1.9] Cooldown Diagnostic** — visibilité du cooldown dans le diagnostic (délais, distribution, signaux perdus)
- **[v1.9] Learning Layer explicable** — LearningSignal + StrategyFeedback, patterns, suggestions shadow, promote/rollback
- **[v1.9.1] Anti-micro-PnL** — TP/SL recalibrés au-dessus du cost model (0.5%/0.4%), min_hold_seconds (30s), sortie signal adoucie
- **[v1.9.1] Smart Cooldown anti-churn** — pénalise les réentrées après trades flat (×1.5 au lieu de ×0.5)
- **[v1.9.1] Learning économique** — catégories useful/insignificant/churn/loss_useful/loss_destructive, coûts estimés, PnL net
- **[v1.9.1] Suggestions anti-churn** — détection automatique du taux de churn + insignifiants → suggestions d'ajustement
- **[v1.9.2] Audit resets complet** — contrat métier clair pour Full Reset (purge totale : trades, ticks, learning, feedback, runs, risk) et Reset Perte Jour (daily loss only). Confirmation backend obligatoire (confirm="RESET"). Réponse détaillée avec compteurs de purge. Refresh frontend cohérent de tous les panels après reset.
- **[v1.9.3] Short Optimization** — Réduction des trades short sans valeur économique, augmentation de la valeur par trade
  - **Short exit score threshold** : seuil configurable pour signal contraire (20 au lieu de 10) — les shorts respirent
  - **Short min score** : filtre économique des shorts (score minimum 25 pour ouvrir un short mean-reversion)
  - **Short min hold** : durée minimale spécifique aux shorts (60s vs 30s) — empêche les fermetures-éclair
  - **Convergence boost** : boost non-linéaire du score quand les indicateurs convergent, compression si divisés — casse l'homogénéité 69-71
  - **Run Value Audit** : service + endpoint `/audit/run-value` — diagnostic complet de la valeur économique par trade
  - **Learning Layer v2** : suggestions short-spécifiques (short_min_score, short_exit_score_threshold, short_min_hold_seconds)
  - **Dataset stats short** : métriques short_trades_useful, short_trades_insignificant, pct_short_economically_useful
- **[v1.9.4] Correction surcorrection short** — Rebalancement complet long/short
  - **Mean reversion ≥2 signaux** : exige 2 oscillateurs convergents (RSI overbought + StochRSI overbought) au lieu d'1 seul. En marché haussier, 1 RSI overbought est normal, pas un signal de short.
  - **Short exit score threshold 35** (était 20) : en marché haussier, score 20+ est permanent → les shorts se faisaient tuer immédiatement. Avec 35, il faut un vrai signal haussier fort.
  - **Short min score 40** (était 25) : les shorts à abs(score)<40 sont rejetés. Plus sélectif sur la qualité des shorts.
  - **Short min hold 90s** (était 60s) : plus de temps pour le pullback se développer.
  - **SL resserré 0.35%** (était 0.4%) : ratio R/R amélioré de 1.25:1 à 1.43:1 (TP 0.5% / SL 0.35%). Pertes mieux contrôlées.
  - **Tech score seuil 95** (était 90) : moins de faux positifs de surachat.
- **[v1.9.5] Stabilisation globale moteur scalping** — Fin des surcorrections, convergence du comportement
  - **R:R théorique 2.4:1** : TP élargi 0.5%→0.6%, SL resserré 0.35%→0.25%. Les pertes maximales passent de $8.75 à $6.25 sur $2500.
  - **Stale exit asymétrique** : positions en perte sortent après 8 min (au lieu de 15). Positions plates gardent 15 min. Cela évite que les positions dérivent vers le SL pendant 15 min.
  - **Trailing stop recalibré** : activation relevée 0.08%→0.15% (plus de micro-activations), trail resserré 0.12%→0.10% (protège mieux les gains une fois activé).
  - **Momentum fade configurable** : rétention relevée 40%→55% (les trades gardent 55% de leur pic avant de sortir, au lieu de 45%).
  - **Shorts rebalancés** : short_min_score 40→30 (2-convergence suffit), exit threshold 35→25 (compromis), min hold 90→60s (pullbacks rapides).
  - **Seuils d'entrée relevés** : buy 20→25, sell 15→20, min_score 15→20. Filtre les longs médiocres qui finissaient en stale/SL.
  - **Signal contraire longs relevé** : score -10→-15. Plus de tolérance au bruit avant de fermer.
  - **Convergence boost amélioré** : facteur 0.4→0.5 (scores plus différenciés), compression 0.85→0.75 (setups ambigus mieux pénalisés).
  - **StabilityAuditService** : nouveau service de diagnostic de stabilité — détection oscillation directionnelle, homogénéité des scores, R:R effectif, domination des sorties, verdict UNSTABLE/IMPROVING/STABLE.
  - **Learning stability** : 3 nouvelles suggestions (déséquilibre directionnel, R:R asymétrique, sortie dominante destructrice).
  - **Endpoint GET /audit/stability** : diagnostic de stabilité accessible via API.
- **[v1.9.6] Correction bug critique + stabilisation moteur** — Invariant slot garanti, pertes réduites
  - **Bug critique double ouverture slot corrigé** : race condition TOCTOU fermée. Guard applicatif dans `_open_position()` + verrou HTTP dans endpoint tick. Impossible d'ouvrir 2 positions sur le même slot.
  - **SL encore resserré 0.25%→0.20%** : R:R théorique 3:1. Perte max $6.25→$5.00.
  - **Stale exit perte accéléré 8min→5min** : positions en perte sortent encore plus vite.
  - **Short rebalancé** : min_score 30→25, exit threshold 25→30, min hold 60→45s.
- **[v1.9.7] Mode autonome backend (headless / low-bandwidth)** — Le robot peut tourner sans frontend
  - **AutonomousManager** : singleton thread-safe qui exécute des ticks côté serveur à intervalle configurable (5s-1h)
  - **Endpoints** : `POST /paper/autonomous/start`, `POST /paper/autonomous/stop`, `GET /paper/autonomous/status`
  - **Mode headless** : le robot trade de manière autonome côté backend. Fermer le navigateur n'arrête PAS le robot.
  - **Low-bandwidth frontend** : toggle dans la toolbar qui coupe le WebSocket Binance et réduit les pollings (alertes 60s→300s, news 300s→900s)
  - **useLivePrice paramétrable** : le WebSocket peut être désactivé via `{ enabled: false }`
  - **15 tests** pour le mode autonome (unitaires + endpoints)
- **[v1.9.8] Pivot stratégique moteur scalping** — No-trade zone, score décompressé, market structure
  - **MarketStructureService** : évaluation qualité marché (price_position, range/ATR, volume_ratio, micro-trend, VWAP)
  - **No-trade zone** : le moteur refuse de trader si quality_score < 35 (configurable). Bloque les marchés bruités, tight range, sans volume.
  - **Filtre longs médiocres** : `long_quality_filter=True` bloque les longs au milieu du range sans micro-tendance haussière.
  - **Score décompressé** : poids Bollinger/StochRSI réduits en tendance (0.6→0.4, 0.7→0.5), convergence boost conditionné au volume, compression renforcée.
  - **Nouveaux signal interpreters** : `interpret_price_position()`, `interpret_range_quality()` — signaux basés sur la structure réelle du marché.
  - **Learning v3** : suggestions stale-négatif dominant, longs homogènes à WR faible.
  - **55 tests** : MarketStructureService, interpreters, score decompression, gating, profil, learning.
- 1808 tests backend, tsc clean
- **[v1.9.9] Lot correctif structurel — Audit de vérité runtime** — Le moteur sait enfin dire NON
  - **Runtime trace** : 8 nouvelles colonnes dans tick_activity_log (market_quality_score, volume_ratio, price_position_pct, range_width_atr, micro_trend_score, vwap_distance_pct, quality_gate_passed, quality_gate_reason). Chaque tick est auditable.
  - **Anti-saturation score technique** : soft ceiling à 88 (était 100), convergence boost exige vol_ratio ≥ 1.2 (était 0.8) et raw_score ≥ 0.75 (était 0.6), dilution par signaux NEUTRAL (4%/signal), plafond exceptionnel 95 (vol ≥ 1.5x + unanimité parfaite).
  - **Quality gate = veto réel** : scalping min_market_quality 35→45, aggressive a désormais un gate (25). Mid-range veto renforcé : exige micro_trend_score ≥ 3 (était > 0).
  - **Anti-churn stale négatif** : stale cooldown multiplier inversé 0.5→2.0 (AUGMENTE au lieu de réduire). Stale négatif → multiplicateur 3x + plancher 4 min. max_cooldown scalping 5→10 min.
  - **34 tests ciblés** : runtime trace (4), anti-saturation (6), quality gate veto (8), anti-churn (8), non-régression (8).
- 1808 tests backend, tsc clean

**Ce qui manque structurellement avant v2.0 :**
- ⚠️ **Validation runtime prolongée** : Les métriques sont disponibles mais n'ont pas encore été validées sur un run de 30+ trades.
- ⚠️ **Gate v2.0 = NOT_READY** : La gate existe mais le système n'a pas encore assez de trades pour passer les critères.

**État du run live v2.0.3 (11 avril 2026) :**
- Robot lancé en mode Scalping (multi-slot : scalping + aggressive)
- Après ~10 min : 0 trades ouverts — **comportement attendu**
- Scalping bloqué par gate micro-tendance (`micro_trend_score = -2` < 2 requis)
- Aggressive bloqué par score insuffisant (17 < buy_threshold 20)
- BTC ~$73 550 en micro-tendance baissière → pas d'opportunité détectée
- Le robot attend une vraie opportunité au lieu d'entrer sur du bruit (c'est le but de v2.0.3)

---

## 2. Architecture

```
bitcoin-trading-assistant/
├── CLAUDE.md                   # Source unique de vérité agent IA
├── backend/                    # API FastAPI
│   ├── app/
│   │   ├── main.py             # Point d'entrée, lifespan, CORS
│   │   ├── config.py           # Settings (pydantic-settings, .env)
│   │   ├── database.py         # Engine SQLAlchemy + session
│   │   ├── api/routes/
│   │   │   ├── health.py       # GET /health, /health/db
│   │   │   ├── market.py       # GET /market/candles, indicators, gaps, price, signals
│   │   │   ├── decision.py     # GET /market/decision
│   │   │   ├── backtest.py     # POST /backtest/run
│   │   │   ├── verification.py # /backtest/history/*, /backtest/verify, /backtest/walk-forward
│   │   │   ├── sentiment.py    # /sentiment/history/*
│   │   │   ├── alerts.py       # CRUD /alerts + POST /alerts/check
│   │   │   ├── news.py         # GET /news, GET /news/sentiment, /news/history/*
│   │   │   ├── risk.py         # /risk/config, status, evaluate, kill-switch, record-loss
│   │   │   ├── paper_trading.py # /paper/* (14 endpoints)
│   │   │   ├── learning.py     # /learning/* (12 endpoints - runs, learning, patterns)
│   │   │   └── scheduler.py    # GET /scheduler/status, POST trigger
│   │   ├── models/             # Modèles SQLAlchemy (10 tables)
│   │   ├── schemas/            # Schémas Pydantic (15 fichiers)
│   │   ├── services/           # Logique métier (25 services)
│   │   ├── tasks/              # Jobs planifiés (APScheduler)
│   │   └── utils/              # Utilitaires
│   └── tests/                  # 1808 tests pytest
├── frontend/src/               # React 18 + TypeScript
│   ├── components/             # Panels UI
│   ├── hooks/                  # Custom hooks React
│   ├── api/                    # Appels API typés
│   ├── pages/                  # Dashboard
│   └── types/                  # Types TypeScript
└── docs/                       # Documentation
```

---

## 3. Fonctionnalités livrées (résumé)

### 3.1 Backend — Endpoints (59 au total)

| Groupe | Count | Exemples |
|--------|-------|----------|
| Health | 2 | `/health`, `/health/db` |
| Market | 7 | candles, fetch, gaps, indicators, signals, price, info |
| Decision | 1 | `/market/decision` |
| Backtest | 6 | run, history/load, range, verify, walk-forward, integrity |
| Sentiment | 4 | history/load, range, coverage, at-date |
| Alerts | 6 | CRUD + check + notifications |
| News | 6 | list, sentiment, history/persist, range, coverage, at-date |
| Risk | 7 | config CRUD, status, evaluate, kill-switch, record-loss |
| Paper Trading | 17 | account, status, tick, trades, metrics, close, journal, style, profile, diagnostic, missed-opps, leverage-analysis, **autonomous/start, stop, status** |
| Scheduler | 3 | status, trigger/4h, trigger/30m |

### 3.2 Multi-Slot Paper Trading (v1.7)

| Fonctionnalité | Status |
|----------------|--------|
| Positions parallèles (jusqu'à 3) | ✅ |
| Slots nommés (balanced, scalping, aggressive) | ✅ |
| Auto-mode multi-slot (balanced + scalping) | ✅ |
| Scalping mean reversion bidirectionnel | ✅ |
| SL/TP direction-aware (long + short) | ✅ |
| Per-slot cooldown et daily counter | ✅ |
| Trailing stop scalping (activation + trail) | ✅ |

### 3.3 Frontend — Composants principaux

Dashboard, PaperTradingPanel (multi-slot), JournalPanel, DiagnosticPanel, DecisionPanel, BacktestPanel, VerificationPanel, RiskPanel, SignalPanel, AlertPanel + Presets, NewsPanel, PriceTicker (WebSocket), CandlestickChart.

---

## 4. Tests

| Fichier | Tests |
|---------|-------|
| test_health.py | 3 |
| test_indicators.py | 35 |
| test_market.py | 4 |
| test_scheduler.py | 16 |
| test_scheduler_dual_jobs.py | 15 |
| test_scheduler_resample_1d.py | 7 |
| test_scheduler_resample_1h.py | 6 |
| test_scheduler_news.py | 11 |
| test_cryptocompare.py | 30 |
| test_signals.py | 88 |
| test_alerts.py | 48 |
| test_news.py | 43 |
| test_decision.py | 122 |
| test_backtest.py | 31 |
| test_verification.py | 79 |
| test_binance_and_router.py | 89 |
| test_news_history.py | 33 |
| test_sentiment_history.py | 42 |
| test_risk.py | 57 |
| test_price_service.py | 15 |
| test_time_buckets.py | 24 |
| test_paper_trading.py | 141 |
| test_journal_and_profiles.py | 84 |
| test_diagnostic.py | 55 |
| test_reality_gap.py | 48 |
| test_autonomous.py | 15 |
| test_market_structure.py | 55 |
| test_economic_value.py | 40 |
| test_enriched_export.py | 25 |
| test_entry_sas.py | 39 |
| test_micro_stop_loss.py | 18 |
| test_pivot_v200.py | 174 |
| test_runtime_correlation.py | 17 |
| test_runtime_truth.py | 34 |
| test_scalping_audit.py | 37 |
| test_smart_cooldown.py | 51 |
| test_stability.py | 67 |
| test_short_optimization.py | 67 |
| test_learning.py | 31 |
| test_candle_reversal.py | 12 |
| **TOTAL** | **1808** ✅ |

---

## 5. Vision : BTC Insight → INFINI

| Étape | Versions | Description | Status |
|-------|----------|-------------|--------|
| **1** BTC Insight | v0.2 → v0.9 | Assistant visuel, pédagogique | ✅ Complet |
| **2** INFINI v1 | v1.0 → v1.7 | Assistant décisionnel + simulation | ✅ Fonctionnel |
| **2b** Reality Gap | v1.8-v1.9 | Coûts, campagnes, audit, gate v2.0 | ✅ Complet |
| **2c** Pivot stratégique | v2.0.0-v2.0.28 | Scalping viable, aggressive protégé, gates d'entrée | ✅ En cours (itérations) |
| **3** INFINI v2 | v2.1+ | Robot autonome (sous contrôle humain) | ⬜ Futur |
| **4** INFINI v3 | v3.0+ | Modèle ML convergent | ⬜ Futur |

---

## 6. État des phases v1.8-v2.0

> **Phase Reality Gap complétée.** Le pivot stratégique v2.0.0 a été livré et itéré jusqu'à v2.0.28.
> **Prochaine étape** : Validation runtime prolongée, puis v2.1+ (exécution réelle).

| Sous-phase | Description | Status |
|------------|-------------|--------|
| v1.8.1 | TradingCostModel (frais, spread, slippage, presets) | ✅ Livré |
| v1.8.2 | PaperRun — Campagnes de validation organisées | ✅ Livré (v1.9.0) |
| v1.8.3 | TruthAudit — Audit de vérité des métriques | ✅ Livré |
| v1.8.4 | V2Gate — Gate formelle avant exécution réelle | ✅ Livré |
| v2.0.0 | Pivot stratégique (economic gate, structural proofs, scoring refondu) | ✅ Livré |
| v2.0.1-v2.0.28 | Itérations scalping + aggressive (SAS, micro SL, trend alignment, etc.) | ✅ Livré |

---

## 7. Ce qui n'est PAS encore fait

| Feature | Priorité | Status |
|---------|----------|--------|
| **Modèle de coûts de trading** | 🔴 CRITIQUE | ✅ v1.8.0 |
| **Audit de vérité métriques** | 🔴 Haute | ✅ v1.8.0 |
| **Gate formelle v2.0** | 🔴 Haute | ✅ v1.8.0 |
| **Campagnes de validation (PaperRun)** | 🟠 Moyenne | ✅ v1.9.0 |
| Robot autonome (connecteur exchange) | Haute | ⬜ v2.0 (bloqué) |
| Docker Compose / CI/CD / Auth JWT | Moyenne | ⬜ Futur |
| Multi-Assets (ETH, SOL...) | Basse | ⬜ Futur |

---

## 8. Problèmes connus

| # | Problème | Sévérité | Notes |
|---|----------|----------|-------|
| 1 | ~~Pas de modèle de coûts de trading~~ | ~~🔴 CRITIQUE~~ | ✅ Résolu v1.8.0 : TradingCostModel avec presets optimistic/realistic/stressed |
| 2 | ~~Pas de campagnes de validation~~ | ~~🟠 Haute~~ | ✅ Résolu v1.9.0 : PaperRun |
| 3 | ~~Métriques non auditées~~ | ~~🟠 Haute~~ | ✅ Résolu v1.8.0 : TruthAuditService |
| 4 | Warnings pytest `_fetch_and_store` non awaited | ⚠️ Low | Cosmétique |
| 5 | Vite build warning chunk > 500 kB | ⚠️ Low | Code-splitting possible |
| 6 | ~~Diagnostic "93% bloqué par positions" persistant après fermeture~~ | ~~🔴 Haute~~ | ✅ Résolu v1.9.2 : full reset purge toutes les tables + diagnostic filtre par date création compte |
| 7 | ~~P&L / RiskConfig non remis à zéro au reset~~ | ~~🔴 Haute~~ | ✅ Résolu v1.9.2 : full reset remet tout à zéro (daily_loss, kill_switch, portfolio_value, learning, runs) |
| 8 | ~~Full reset ne purgeait pas learning/feedback/runs~~ | ~~🔴 Haute~~ | ✅ Résolu v1.9.2 : full reset purge learning_signal, strategy_feedback, paper_run |
| 9 | ~~JournalPanel/DiagnosticPanel non rafraîchis après reset~~ | ~~🔴 Haute~~ | ✅ Résolu v1.9.2 : tradeVersion incrémenté après reset → refresh propagé |
| 10 | ~~RiskPanel non rafraîchi après full reset~~ | ~~🟠 Moyenne~~ | ✅ Résolu v1.9.2 : RiskPanel reçoit refreshTrigger |
| 11 | ~~Pas de confirmation backend pour full reset~~ | ~~🟠 Moyenne~~ | ✅ Résolu v1.9.2 : confirm="RESET" obligatoire |
| 12 | ~~Bug critique double ouverture du même slot~~ | ~~🔴 CRITIQUE~~ | ✅ Résolu v1.9.6 : guard applicatif dans _open_position() + verrou HTTP dans endpoint tick. 5 tests prouvant l'invariant. |
| 13 | ~~Gate économique scalping mathématiquement impossible~~ | ~~🔴 CRITIQUE~~ | ✅ Résolu v2.0.0-fix : `expected_capture_pct` était None (fallback 0.20%) vs seuil requis 0.465% → 100% de refus. Fixé à 0.50%. |
| 14 | ~~Multi-slot perdu après full reset~~ | ~~🔴 CRITIQUE~~ | ✅ Résolu v2.0.0-fix : `max_open_positions` default 1→3 dans `FullResetRequest` et `PaperAccountCreate`. Le slot aggressive survit au reset. |

---

## 9. Contrats Métier des Resets (v1.9.2)

### 9.1 Reset Perte Jour (`POST /risk/reset-daily-loss`)

**Périmètre strict — ne touche qu'au risque journalier :**

| Action | Détail |
|--------|--------|
| ✅ Remet `daily_loss_current` à 0.0 | Compteur de perte journalière remis à zéro |
| ✅ Met à jour `daily_loss_reset_date` | Aujourd'hui |
| ✅ Désactive kill switch SI "Perte journalière" | Seulement si `kill_switch_reason` contient "Perte journalière" |
| ✅ Nettoie `kill_switch_triggered_at` | Seulement si le kill switch est désactivé |
| ❌ NE touche PAS aux trades | Aucun trade supprimé |
| ❌ NE touche PAS au capital | Le compte reste identique |
| ❌ NE touche PAS au learning | Les learning_signal restent |
| ❌ NE touche PAS aux runs | Les paper_run restent |
| ❌ NE touche PAS aux tick_logs | Les tick_activity_log restent |
| ❌ NE désactive PAS un kill switch manuel | Si raison != "Perte journalière", il reste actif |

### 9.2 Full Reset (`POST /paper/account/reset`)

**Purge totale — repart de zéro :**

| Table | Action | Justification |
|-------|--------|---------------|
| `paper_trade` | 🗑️ Supprimé | Les trades sont liés à l'ancien compte |
| `paper_account` | 🗑️ Supprimé + recréé | Le compte est recréé avec le nouveau capital |
| `tick_activity_log` | 🗑️ Supprimé | Les ticks référencent l'ancien account_id, pollueraient le diagnostic |
| `learning_signal` | 🗑️ Supprimé | Les trade_id deviennent orphelins, les patterns sont obsolètes |
| `strategy_feedback` | 🗑️ Supprimé | Les suggestions sont basées sur des données mortes |
| `paper_run` | 🗑️ Supprimé | Les campagnes sont liées à l'ancien état |
| `risk_config` | 🔄 Réinitialisé | daily_loss=0, kill_switch=off, portfolio_value=nouveau capital |

**Sécurité :**
- Exige `confirm: "RESET"` dans le body de la requête
- Refus 400 si absent ou incorrect
- Retourne un `FullResetResponse` avec compteurs de purge détaillés

**Refresh frontend :**
- `tradeVersion` incrémenté → JournalPanel + DiagnosticPanel rafraîchis
- `onResetComplete` propagé → RiskPanel rafraîchi
- `lastTick` remis à null
- Auto-mode arrêté

---

## 10. Comment lancer

```bash
# Backend
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v

# TypeScript check
cd frontend && npx tsc --noEmit

# Mode headless (via API — pas besoin de frontend)
# 1. Démarrer le backend
# 2. Lancer le robot autonome :
curl -X POST http://localhost:8000/paper/autonomous/start -H "Content-Type: application/json" -d '{"interval_seconds": 10, "profile": "scalping"}'
# 3. Vérifier le statut :
curl http://localhost:8000/paper/autonomous/status
# 4. Arrêter :
curl -X POST http://localhost:8000/paper/autonomous/stop
```
