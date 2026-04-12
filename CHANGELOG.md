# Changelog

All notable changes to this project will be documented in this file.

## [2.0.20] - 2026-04-13

### Fixed
- **FIX BIAIS 100% SHORT SCALPING** — Le tick momentum override (v2.0.14) détectait correctement les LONGs (prix en hausse) mais le gate structural proofs (v2.0.0) les bloquait systématiquement. Ce gate vérifie `micro_trend_score ≥ 3` pour les LONGs — un indicateur lagging 15 min, négatif en marché bearish. Résultat : 100% des trades scalping étaient des SHORTs car seuls ceux-ci passaient le gate (micro_trend négatif = preuve pour short). Fix : bypass des structural proofs quand `tm_override_active=True` — la direction réelle du prix sur 30 sec EST la preuve structurelle.

### Changed
- `_tick_single_slot` : structural proofs gate bypassé quand tick momentum override est actif (`not tm_override_active`).

### Technical
- Modifié : `backend/app/services/paper_trading_service.py` — 1 ligne : ajout condition `and not tm_override_active` au structural proofs gate
- Ajouté : `backend/tests/test_pivot_v200.py` — Classe `TestScalpingV2020` avec 2 tests (bypass structural proofs + non-régression)
- Tests : 1732 (+2)

## [2.0.19] - 2026-04-12

### Fixed
- **AGGRESSIVE SLOT PROTECTION** — Le slot aggressive (trade #597) a perdu -$10.32 en dérivant 3h sans trailing stop ni stale négatif. Ajout de `stale_negative_exit_minutes=60`, `trailing_stop_activation_pct=0.15`, `trailing_stop_drop_ratio=0.30`, `gain_erosion_ratio=0.50`. Impact estimé : transforme les pertes de -$10 (3h dérive) en -$2 à -$3 (60 min max).
- **CANDLE REVERSAL FIX** — La feature v2.0.18 n'a JAMAIS déclenché en production (0/32 trades). `detect_direction()` utilisait un seuil fixe `MIN_MOVE_PCT=0.002%` trop élevé avec une fenêtre de 15s (~3 ticks à 5s/tick). Fix : `detect_direction()` accepte un `min_move_pct` personnalisable, `check_candle_reversal` utilise 0.001% (plus sensible), fenêtre 15→30s (plus de ticks).
- **OVERRIDE ANTI-CHURN** — Les trades tick_override étaient immédiatement fermés par signal contraire (<1 min) car le score bullish (+66) dépassait le seuil de sortie (30). Fix : entry_reason préfixé `tick_override_` + logique `is_reversal` étendue pour protéger les overrides comme les mean_reversion (seuil relevé à `abs(score_entrée)+1`).

### Changed
- `TickMomentumService.detect_direction()` : nouveau paramètre optionnel `min_move_pct` (None=cls.MIN_MOVE_PCT).
- `TickMomentumService.check_candle_reversal()` : passe `min_move_pct=0.001` à detect_direction pour sensibilité accrue.
- Profil `aggressive` : +4 nouveaux paramètres de protection (trailing, gain_erosion, stale_negative).
- Profil `scalping` : `candle_reversal_window_seconds` 15→30.
- `_tick_single_slot` : entry_reason des override trades préfixé `tick_override_{direction}`.
- `_tick_single_slot` : `is_reversal` check étendu pour inclure `tick_override_` (long et short).
- 2 tests mis à jour (`test_aggressive_not_affected`, `test_aggressive_has_no_gain_erosion`).

### Technical
- Modifié : `backend/app/services/tick_momentum_service.py` — `detect_direction` accept `min_move_pct`, `check_candle_reversal` uses 0.001%
- Modifié : `backend/app/services/trading_profile_service.py` — Aggressive profile +4 params, scalping reversal window 30s
- Modifié : `backend/app/services/paper_trading_service.py` — `tick_override_` prefix + `is_reversal` extended
- Modifié : `backend/tests/test_pivot_v200.py` — 2 tests updated for aggressive profile changes
- Tests : 1730 (inchangé)

## [2.0.18] - 2026-04-12

### Added
- **CANDLE REVERSAL EXIT** — Nouveau type de sortie active `closed_candle_reversal`. Quand la couleur de la bougie s'inverse par rapport à l'entrée et persiste ≥3 secondes, la position est fermée immédiatement. Basé sur l'observation que les trades profitables gardent la même couleur de pastille (E=S), tandis que les perdants changent de couleur.
- **REVERSAL DELAY TRACKING** — Nouveau champ `reversal_delay_seconds` sur `PaperTrade` et `LearningSignal`. Mesure le temps entre le changement de couleur et la fermeture effective. Permet au ML d'apprendre la vitesse de réaction optimale.
- **PATTERN 9 — REVERSAL DELAY ANALYSIS** — Le learning analyse les trades par délai de reversal : fast (<5s) vs slow (≥5s), et compare les trades avec reversal vs sans reversal pour quantifier l'impact de la sortie active.
- **UI LAYOUT PLEINE LARGEUR** — TAB 2 restructuré : Risk Panel en bandeau compact pleine largeur (replié par défaut), Paper Trading/Journal/Diagnostic en pleine largeur. Fini le layout 42%/58% côte à côte.
- **3 nouveaux params profil** : `candle_reversal_exit_enabled`, `candle_reversal_min_seconds`, `candle_reversal_window_seconds`.
- **12 nouveaux tests** : détection reversal (8 tests TickMomentumService), learning avec reversal_delay (2 tests), patterns reversal delay (2 tests).
- Script de migration `migrate_v2018.py`.

### Changed
- `TickMomentumService` : nouveau buffer `_reversal_start` pour tracker le début du reversal, méthodes `check_candle_reversal()` et `reset_reversal()`.
- `_tick_single_slot` : vérification candle reversal APRÈS trailing/breakeven/gain_erosion et AVANT stale exit.
- `_open_position` : reset du tracker reversal à chaque nouvelle position.
- `EXIT_TYPE_LABELS` frontend enrichi : +3 types (breakeven, gain_erosion, candle_reversal).
- `CandleDirectionDot` : nouveau prop `reversalDelay` pour afficher le délai dans le tooltip de sortie.
- Dashboard TAB 2 : layout de side-by-side (Risk lg=5 + Paper lg=7) vers stacked full-width.

### Technical
- Modifié : `backend/app/models/paper_account.py` — Nouveau champ `reversal_delay_seconds REAL nullable`
- Modifié : `backend/app/models/learning.py` — Nouveau champ `reversal_delay_seconds REAL nullable`
- Modifié : `backend/app/schemas/journal.py` — 3 nouveaux params TradingProfileParams (candle_reversal_*)
- Modifié : `backend/app/schemas/paper_trading.py` — `reversal_delay_seconds` sur Response + ExportItem
- Modifié : `backend/app/services/tick_momentum_service.py` — `_reversal_start`, `check_candle_reversal()`, `reset_reversal()`
- Modifié : `backend/app/services/paper_trading_service.py` — Sortie candle reversal dans le tick loop
- Modifié : `backend/app/services/trading_profile_service.py` — Profil scalping avec candle_reversal_exit_enabled=True
- Modifié : `backend/app/services/learning_service.py` — Pattern 9 (reversal delay) + record_sample enrichi
- Modifié : `frontend/src/pages/Dashboard.tsx` — Layout TAB 2 restructuré
- Modifié : `frontend/src/components/PaperTradingPanel.tsx` — EXIT_TYPE_LABELS enrichi, reversalDelay prop
- Modifié : `frontend/src/types/api.ts` — reversal_delay_seconds sur PaperTradeItem + ExportItem
- Nouveau : `backend/tests/test_candle_reversal.py` — 12 tests
- Nouveau : `backend/migrate_v2018.py` — Migration SQLite
- Tests : 1718 → 1730 (+12)

## [2.0.17] - 2026-04-12

### Added
- **CANDLE DIRECTION LEARNING PATTERNS** — Le `LearningService.analyze_patterns()` analyse désormais la cohérence entrée→sortie des bougies comme **pattern d'apprentissage prioritaire**. 4 catégories : `same_aligned` (momentum conservé ✅), `same_counter` (piégé contre-courant), `reversed_favor` (reversal gagnant), `reversed_against` (momentum perdu ❌).
- **MÉTA-PATTERN CONSISTENCY vs REVERSAL** — Comparaison globale des trades "même couleur" vs "changement de couleur" avec delta WR et delta PnL. Permet de quantifier l'avantage de rester dans le momentum.
- **CROISEMENT DURÉE × CANDLE** — Analyse croisée : scalps rapides (<2min) à même couleur vs changement, trades lents (≥2min) avec reversal. Identifie les configurations optimales (court + même couleur = bon scalp).
- **SUGGESTION CANDLE REVERSAL** — Si les trades avec changement de couleur défavorable sont massivement perdants (WR < 35%), le learning suggère de réduire `stale_negative_exit_minutes` pour couper plus vite quand le momentum se retourne.
- **SUGGESTION ENTRÉE CONTRE-TENDANCE** — Si entrer contre le momentum micro (long sur bougie rouge) est nettement pire qu'entrer aligné, le learning suggère de relever `min_micro_trend_long`.
- **PASTILLE SORTIE FALLBACK** — Dans le journal, la pastille de sortie (S) s'affiche même pour les anciens trades sans `exit_candle_direction` en déduisant la couleur de `exit_price` vs `entry_price`.
- **PASTILLES ENRICHIES** — Chaque pastille contient un mini-label "E"/"S", séparateur →, tooltip avec type de sortie (✅ TP, ❌ SL, ⚠️ Signal...) et PnL sur la pastille de sortie.
- **9 nouveaux tests** : candle patterns (same_aligned, reversed_against, meta, durée×candle, shorts, impact), suggestions candle (reversal destructive, contre-tendance, mixed results).

### Changed
- `CandleDirectionDot` : pastille agrandie 14→20px, mini-label "E"/"S" intégré, props `exitType` et `pnl` pour tooltip enrichi.
- `TradeRow` : fallback `exitCandle` calculé client-side, séparateur → entre pastilles, `exitType` + `pnl` passés au tooltip sortie.
- `EXIT_TYPE_LABELS` : mapping lisible des statuts de sortie pour le tooltip.

### Technical
- Modifié : `backend/app/services/learning_service.py` — Pattern 7 (candle consistency), Pattern 8 (durée×candle), Suggestion 15 (reversal destructive), Suggestion 16 (contre-tendance)
- Modifié : `backend/tests/test_learning.py` — +9 tests (classes TestCandleDirectionPatterns + TestCandleDirectionSuggestions)
- Modifié : `frontend/src/components/PaperTradingPanel.tsx` — Pastilles enrichies + fallback sortie
- Tests : 1709 → 1718 (+9)

## [2.0.16] - 2026-04-12

### Added
- **EXIT CANDLE DIRECTION** — Nouveau champ `exit_candle_direction` ("green"/"red") stocké à la fermeture de chaque position. Permet de savoir dans quel sens allait le prix au moment de la sortie.
- **PASTILLE DOUBLE (Entrée + Sortie)** — Dans le journal des trades, chaque ligne affiche maintenant deux pastilles colorées : 🟢/🔴 pour l'entrée ET pour la sortie, avec tooltip adapté pour chaque phase.
- **TIMESTAMPS PRÉCIS** — Affichage de la date/heure/seconde exacte d'entrée (format "12 avr. 14:32:05") sur les positions ouvertes et dans le journal des trades. Tooltip montrant entrée + sortie au survol.
- **DURÉE EXACTE EN SECONDES** — Colonne "Durée" enrichie avec format "2m 34s" ou "1h 05m 12s" au lieu de "0.1h". Nouveau champ `duration_seconds` calculé dans le schema Pydantic.
- **DURÉE DU RUN EN TEMPS RÉEL** — Nouveau composant `RunDurationTimer` affiché dans la barre du robot actif (auto + headless). Compteur hh:mm:ss mis à jour chaque seconde avec couleur Bitcoin orange.
- **ENRICHISSEMENT ML** — `LearningSignal` enrichi avec `entry_candle_direction` et `exit_candle_direction` pour permettre au futur modèle ML d'apprendre les patterns d'entrée/sortie par couleur de bougie.
- Script de migration `migrate_v2016.py` pour les nouvelles colonnes.
- **8 nouveaux tests** : modèle exit_candle_direction, schema duration_seconds, _close_position avec exit candle, LearningSignal enrichi.

### Changed
- `CandleDirectionDot` supporte un prop `type="entry"|"exit"` avec labels et tooltips adaptés à chaque phase.
- `TradeRow` : nouvelle colonne "Heure" avec timestamp précis + colonne "Durée" avec format lisible.
- `PositionTimer` et `RunDurationTimer` coexistent : le premier pour la position, le second pour le run complet.
- Hook `usePaperTrading` : nouvel état `autoStartedAt` pour tracker le début du run frontend.
- Headless mode : le `RunDurationTimer` remplace l'affichage statique de l'uptime.

### Technical
- Modifié : `backend/app/models/paper_account.py` — Nouvelle colonne `exit_candle_direction VARCHAR(10)` nullable
- Modifié : `backend/app/models/learning.py` — Nouvelles colonnes `entry_candle_direction`, `exit_candle_direction`
- Modifié : `backend/app/schemas/paper_trading.py` — `exit_candle_direction`, `duration_seconds`, `model_post_init`
- Modifié : `backend/app/services/paper_trading_service.py` — `_close_position` détermine exit candle via tick momentum ou fallback prix
- Modifié : `backend/app/services/learning_service.py` — `record_sample` copie les candle directions
- Modifié : `frontend/src/types/api.ts` — `exit_candle_direction`, `duration_seconds`
- Modifié : `frontend/src/hooks/usePaperTrading.ts` — `autoStartedAt` state
- Modifié : `frontend/src/components/PaperTradingPanel.tsx` — Composants enrichis
- Tests : 1701 → 1709 (+8)

## [2.0.15] - 2026-04-12

### Added
- **CANDLE DIRECTION INDICATOR (UI)** — Nouveau champ `entry_candle_direction` ("green"/"red"/null) stocké sur chaque `PaperTrade` à l'ouverture de position. Affiche un dot coloré (🟢/🔴) avec tooltip de cohérence direction/bougie à côté de chaque position dans le PaperTradingPanel.
- **REST PRICE FALLBACK** — Le hook `useLivePrice` ajoute un fallback REST API (`/market/price`) si le WebSocket Binance ne se connecte pas dans les 5 secondes. Polling toutes les 10s. Le PriceTicker affiche "REST" en orange au lieu de "LIVE".
- Nouveau champ `source: 'websocket' | 'rest' | null` dans `useLivePrice` pour tracer l'origine du prix.
- Composant `CandleDirectionDot` dans PaperTradingPanel : dot coloré + tooltip avec vérification cohérence direction/bougie.
- Script de migration `migrate_v2015.py` pour la nouvelle colonne.
- **7 nouveaux tests** : modèle, schema, service `_open_position`, endpoint status.

### Changed
- `PriceTicker` : nouveau badge "REST" orange quand le prix vient du fallback REST API (au lieu de "OFFLINE" gris).
- Footer Dashboard : affiche "Mode REST (prix ~10s)" quand le fallback est actif.
- Direction de la bougie déterminée par tick momentum override (scalping) ou micro_trend_score (autres profils).

### Fixed
- **Prix stale ~5 min de retard** quand le WebSocket Binance est inaccessible : le fallback REST appelle Binance REST API (même source) via le backend.
- **Pastille candle direction toujours null après restart** — Le buffer tick momentum est vide après restart → `detect_direction()` retourne `insufficient_data` → aucune source ne détermine la couleur. Ajout d'un fallback final basé sur la direction du trade (long→green, short→red) qui garantit toujours une valeur.

### Technical
- Modifié : `backend/app/models/paper_account.py` — Nouvelle colonne `entry_candle_direction VARCHAR(10)` nullable
- Modifié : `backend/app/schemas/paper_trading.py` — Champ dans PaperTradeResponse + PaperTradeExportItem
- Modifié : `backend/app/services/paper_trading_service.py` — Détermination et passage de la direction bougie
- Nouveau : `backend/migrate_v2015.py` — Migration DB
- Modifié : `backend/tests/test_paper_trading.py` — 7 nouveaux tests TestEntryCandleDirection
- Modifié : `frontend/src/types/api.ts` — Champ dans PaperTradeItem + PaperTradeExportItem
- Modifié : `frontend/src/components/PaperTradingPanel.tsx` — CandleDirectionDot composant + intégration
- Modifié : `frontend/src/hooks/useLivePrice.ts` — Fallback REST, source tracking
- Modifié : `frontend/src/components/PriceTicker.tsx` — Prop source, badge REST
- Modifié : `frontend/src/pages/Dashboard.tsx` — Propagation source, footer REST status
- **1701 tests** backend, tous passing

## [2.0.14] - 2026-04-12

### Added
- **CANDLE DIRECTION OVERRIDE** — En mode scalping, la direction du trade est désormais déterminée par la direction RÉELLE du prix sur les 30 dernières secondes (bougie verte → LONG, bougie rouge → SHORT), au lieu de suivre le score technique lagging 15 min. Élimine le biais 100% short quand les indicateurs restent bearish en marché ranging.
- Nouvelle méthode `TickMomentumService.detect_direction()` : détecte la direction dominante du prix sans attendre de direction souhaitée, retourne "long", "short", ou None (flat/insufficient).
- Nouveaux champs `tick_momentum_override_direction`, `tick_momentum_min_score` dans `TradingProfileParams`.
- Nouveau status de non-trade `tick_momentum_no_direction` + labels `tick_momentum_override` dans REASON_LABELS.
- **9 nouveaux tests** : 6 tests unitaires `detect_direction()` + 3 tests d'intégration override/flat.

### Changed
- **Fenêtre tick momentum 10→30 secondes** : 10 sec ne suffisait pas en cas de volatilité, 30 sec donne 6 ticks (~5 sec/tick) pour une analyse fiable de la direction.
- **MIN_MOVE_PCT 0.001→0.002%** : calibré pour 30 sec de fenêtre, filtre le bruit sans bloquer les vrais mouvements.
- **MAX_BUFFER_SIZE 200→500** : supporte la fenêtre élargie.
- **Score minimum réduit à 10 quand l'override est actif** : le score n'est plus qu'un filtre de qualité (marché actif), pas un signal de direction.
- **Bearish veto SKIPPÉ** quand l'override est actif : la bougie EST la confirmation de direction, le micro_trend 15 min n'est plus pertinent.
- **Scalping reversal SKIPPÉ** quand l'override est actif : la bougie décide la direction, pas les oscillateurs.
- **"attendre" BYPASSÉ** quand l'override est actif : le score "attendre" signifie que les indicateurs 15 min sont indécis, mais le prix bouge quand même. Permet des LONG même quand le score est entre -20 et +30.

### Fixed
- **Biais 100% short** : les indicateurs 15 min restaient bearish en marché ranging, produisant uniquement des recommendations SHORT. Aucun LONG n'était possible. L'override permet des LONG quand le prix monte.

### Technical
- Modifié : `backend/app/services/tick_momentum_service.py` — Ajout `detect_direction()`, buffer 500, MIN_MOVE 0.002%
- Modifié : `backend/app/schemas/journal.py` — 2 nouveaux champs override
- Modifié : `backend/app/services/paper_trading_service.py` — Override direction + skip bearish_veto/reversal/attendre
- Modifié : `backend/app/services/trading_profile_service.py` — window 30s, override=True, min_score=10
- Modifié : `backend/app/services/journal_service.py` — Labels override
- Modifié : `backend/tests/test_pivot_v200.py` — 9 nouveaux tests + mise à jour tests existants
- **1694 tests** backend, tous passing

## [2.0.13] - 2026-04-12

### Added
- **TICK MOMENTUM CONFIRMATION** — Nouveau gate d'entrée qui analyse les ticks récents (~10 sec) pour confirmer que le prix va dans la direction du trade AVANT d'ouvrir. SHORT → le prix doit être en baisse. LONG → le prix doit être en hausse. Élimine les shorts qui entrent pendant que le prix monte et restent négatifs 2 min jusqu'au stale exit → perte systématique.
- Nouveau service `TickMomentumService` : buffer en mémoire de prix tick-par-tick, analyse de direction avec fenêtre temporelle configurable, calcul du ratio ticks montants/descendants.
- Nouveaux champs `tick_momentum_enabled`, `tick_momentum_window_seconds`, `tick_momentum_min_ticks` dans `TradingProfileParams`.
- Nouveau status de non-trade `tick_momentum_mismatch` + label dans REASON_LABELS.
- **20 tests `TestTickMomentumServiceV2013` + `TestTickMomentumIntegrationV2013`** :
  - Config profils (scalping=enabled, aggressive/conservative=disabled)
  - Service unitaire (record, buffer, direction up/down/flat, window filtering, up_ratio)
  - 3 tests d'intégration avec vrais ticks dans paper_trading_service

### Changed
- Le cooldown fixe n'est plus le seul gate d'entrée : le tick momentum valide la direction du prix en temps réel, indépendamment du timer.
- Le scalping n'entre plus dans un short quand le prix est en hausse sur les 10 dernières secondes.

### Technical
- Nouveau : `backend/app/services/tick_momentum_service.py` — Service complet avec buffer circulaire
- Modifié : `backend/app/schemas/journal.py` — 3 nouveaux champs tick_momentum_*
- Modifié : `backend/app/services/paper_trading_service.py` — Enregistrement tick + gate momentum
- Modifié : `backend/app/services/trading_profile_service.py` — tick_momentum activé sur scalping
- Modifié : `backend/app/services/journal_service.py` — Label tick_momentum_mismatch
- Modifié : `backend/tests/test_pivot_v200.py` — 20 nouveaux tests
- **1685 tests** backend, tous passing

## [2.0.12] - 2026-04-12

### Added
- **GAIN EROSION STOP** — Nouveau mécanisme de sortie qui protège les petits gains (sous le seuil d'activation du trailing). Le trailing ne s'active qu'à 0.04% (~$1). Les gains entre $0 et $1 fondaient sans protection. Le gain erosion stop sort dès que le gain a perdu 30% de son pic (ratio=0.30, garde 70%). S'active uniquement si peak ≥ 0.01% (~$0.25) ET peak < activation trailing (0.04%). Au-dessus, le trailing relatif (15% drop) prend le relais.
- Nouveau champ `gain_erosion_ratio` dans `TradingProfileParams` (None=désactivé pour profils classiques)
- Nouveau status de sortie `closed_gain_erosion` + label dans REASON_LABELS
- **18 tests `TestGainErosionStopV2012`** :
  - Config profils (scalping=0.30, aggressive/conservative=None)
  - Logique mathématique (fire/no-fire/peak minimum/above trailing)
  - Ordre dans le code (après trailing, avant breakeven)
  - 3 tests d'intégration avec vrais ticks (LONG fire, LONG no-fire, SHORT fire)

### Changed
- Le breakeven stop ne gère plus que les cas où le gain retombe à ≤ 0% ET le gain erosion ne s'est pas déclenché (peak < 0.01% ou gain erosion désactivé).

### Technical
- Modifié : `backend/app/schemas/journal.py` — Nouveau champ `gain_erosion_ratio`
- Modifié : `backend/app/services/paper_trading_service.py` — Gain erosion stop inséré entre trailing et breakeven
- Modifié : `backend/app/services/trading_profile_service.py` — `gain_erosion_ratio=0.30` sur scalping
- Modifié : `backend/app/services/journal_service.py` — Label `closed_gain_erosion`
- Modifié : `backend/tests/test_pivot_v200.py` — 18 nouveaux tests + adaptation test breakeven existant
- **1665 tests** backend, tous passing ✅

## [2.0.11] - 2026-04-12

### Fixed
- **BOUCLE REVERSAL-CHURN — 30 trades identiques en boucle** — Les shorts `mean_reversion_short` étaient fermés par signal contraire après ~50 secondes car le même score bullish (+66) qui déclenchait le reversal fermait aussi le trade (seuil signal contraire = 30, score = 66 ≥ 30 → fermeture → cooldown → réouverture → boucle infinie). Corrigé : pour les reversals, le signal contraire ne ferme que si le score a **augmenté au-delà du score d'entrée +1**. Un short ouvert à score=66 ne ferme plus par signal contraire tant que le score reste ≤ 66. Les autres mécanismes de sortie (trailing, stale, SL/TP) restent inchangés.
- **COOLDOWN TROP LONG — Rate manquée après renversement de tendance** — Le cooldown de 2 minutes empêchait de capter le prochain signal après un renversement de tendance. En 2 minutes, la tendance peut déjà s'inverser entre 2 bougies. Le `bearish_veto` (v2.0.10) protège maintenant en amont, rendant les longs cooldowns anti-churn redondants.
  - `cooldown_minutes` : 2 → **1** minute
  - `max_cooldown_minutes` : 10.0 → **5.0** minutes
  - `STALE_NEGATIVE_FLOOR` : 4.0 → **2.0** minutes

### Added
- **Protection reversal signal contraire (SHORT)** — Pour les trades `mean_reversion_short`, le seuil de signal contraire est relevé à `max(short_exit_th, abs(entry_score) + 1)`. Un reversal entré à score=66 ne ferme que si score ≥ 67.
- **Protection reversal signal contraire (LONG)** — Pour les trades `mean_reversion_long`, le signal contraire ne ferme que si `abs(current_score) > abs(entry_score)` (la pression bearish a augmenté depuis l'entrée).
- **12 tests `TestReversalSignalContraireProtection`** :
  - `test_reversal_short_not_closed_by_same_score` — score=66 à l'entrée, score=66 au tick → pas de fermeture
  - `test_reversal_short_closed_by_higher_score` — score=66 à l'entrée, score=67 au tick → fermeture signal contraire
  - `test_non_reversal_short_still_uses_standard_threshold` — trade non-reversal → seuil standard 30
  - `test_reversal_short_closed_by_trailing_stop` — le trailing fonctionne toujours indépendamment
  - `test_reversal_short_closed_by_stale` — le stale exit fonctionne toujours indépendamment
  - `test_reversal_long_not_closed_by_same_score` — long reversal protégé symétriquement
  - `test_reversal_long_closed_by_stronger_bearish` — long reversal fermé si bearish augmente
  - `test_non_reversal_long_still_uses_standard_threshold` — long non-reversal → seuil standard
  - `test_cooldown_reduced_to_1_minute` — cooldown scalping = 1 min
  - `test_max_cooldown_reduced_to_5` — max cooldown scalping = 5.0 min
  - `test_stale_negative_floor_reduced_to_2` — plancher stale négatif = 2.0 min
  - `test_bearish_veto_still_active` — le veto v2.0.10 fonctionne toujours

### Technical
- Modifié : `backend/app/services/paper_trading_service.py` — Protection reversal dans la logique signal contraire (SHORT et LONG)
- Modifié : `backend/app/services/trading_profile_service.py` — `cooldown_minutes` 2→1, `max_cooldown_minutes` 10→5
- Modifié : `backend/app/services/smart_cooldown_service.py` — `STALE_NEGATIVE_FLOOR` 4→2
- Modifié : 7 fichiers de tests — assertions adaptées aux nouvelles valeurs de cooldown
- **1647 tests** backend, tous passing ✅

## [2.0.10] - 2026-04-12

### Fixed
- **DOWNTREND PROTECTION — 7 trades LONG perdants (-$10.44) pendant que le BTC descend** — Le score technique de 65 est basé sur des indicateurs 15min en retard (RSI, SMA, EMA) qui restent bullish pendant un pullback. Le robot entrait LONG à répétition, perdant à chaque fois via stale_negative_exit en 2 min. Le problème est à l'**entrée**, pas à la **sortie**.

### Added
- **Veto bearish micro-trend** — Bloque les LONG quand `micro_trend_score < 0` (tendance baissière objective sur les dernières candles). Les shorts et les reversals ne sont PAS bloqués. Raison de non-trade : `bearish_veto`.
- **Reversal enrichi avec micro-trend (Source 4)** — Le reversal check reçoit maintenant `mq_data`. Si `micro_trend_score ≤ -2`, un signal overbought est injecté → favorise les SHORT contrarians au lieu d'entrer LONG en downtrend. Symétriquement, `micro_trend ≥ 3` injecte un signal oversold → favorise LONG.
- **Market quality calculé AVANT le reversal** — Réordonnancement de `_tick_single_slot()` : le mq_data est maintenant calculé en premier pour alimenter le reversal check et le veto bearish.
- **11 tests `TestDowntrendProtectionV2010`** :
  - `test_reversal_fires_with_bearish_micro_trend` — micro_trend=-3 → short reversal
  - `test_reversal_fires_with_bullish_micro_trend` — micro_trend=+3 → long reversal
  - `test_reversal_no_fire_with_neutral_micro_trend` — micro_trend=-1 → pas de signal
  - `test_reversal_backward_compatible_without_mq_data` — sans mq_data → reversal classique
  - `test_reversal_micro_trend_plus_bearish_majority_cumulates` — double signal bearish
  - `test_veto_bearish_blocks_long_when_micro_trend_negative` — veto activé
  - `test_veto_bearish_does_not_block_short` — shorts non affectés
  - `test_veto_bearish_does_not_block_reversal` — reversals non affectés
  - `test_veto_bearish_allows_long_when_micro_trend_positive` — long autorisé si mt ≥ 0
  - `test_veto_bearish_allows_long_when_micro_trend_zero` — neutre = OK
  - `test_market_quality_computed_before_reversal` — ordre vérifié par introspection

### Technical
- Modifié : `backend/app/services/paper_trading_service.py` — Réordonnancement mq_data avant reversal, veto bearish, reversal Source 4 micro-trend, signature `_scalping_reversal_check(decision, mq_data=None)`
- Modifié : `backend/app/services/journal_service.py` — Nouveau label `bearish_veto` dans `REASON_LABELS`
- Modifié : `backend/tests/test_pivot_v200.py` — 11 nouveaux tests downtrend protection
- **1635 tests** backend, tous passing ✅

## [2.0.9] - 2026-04-12

### Fixed
- **TRAILING STOP RELATIF — Les gains étaient rongés par le trailing absolu** — L'ancien trailing (recul fixe de 0.06%) perdait 50-60% du gain sur les petits peaks (0.10%-0.12%) typiques du scalping. Exemple : peak +0.12%, exit à +0.06% = 50% du gain perdu. Le nouveau système est **proportionnel au gain** : on sort quand le gain a reculé de 30% par rapport à son pic. Peak +0.12% → exit à +0.084% (30% perdu max). Peak +0.50% → exit à +0.35% (toujours 30% max). Le paramètre `trailing_stop_drop_ratio=0.30` remplace `trailing_stop_pct=0.06` pour le scalping.

### Added
- **Paramètre `trailing_stop_drop_ratio`** dans `TradingProfileParams` — ratio de recul relatif au pic (0.30 = sortie quand gain < 70% du pic). Remplace `trailing_stop_pct` si défini, sinon fallback vers le mode absolu.
- **5 tests `TestTrailingStopRelativeV209`** :
  - `test_relative_trailing_keeps_70pct_of_small_gain` — peak modeste → garde ~70%
  - `test_relative_trailing_no_fire_when_gain_above_retention` — gain au-dessus du seuil → pas de trailing
  - `test_relative_trailing_big_gain_more_room` — gros gain → tolère plus de recul absolu qu'avant
  - `test_relative_trailing_short_symmetric` — trailing relatif fonctionne pour les shorts
  - `test_relative_trailing_preserves_more_than_absolute` — preuve mathématique : le relatif garde toujours plus que l'absolu pour les peaks < 0.20%

### Technical
- Modifié : `backend/app/schemas/journal.py` — Nouveau champ `trailing_stop_drop_ratio` dans `TradingProfileParams`
- Modifié : `backend/app/services/trading_profile_service.py` — `trailing_stop_drop_ratio=0.30` dans le preset scalping
- Modifié : `backend/app/services/paper_trading_service.py` — Logique trailing refondue : mode relatif (prioritaire) avec fallback absolu
- Modifié : `backend/tests/test_pivot_v200.py` — 5 nouveaux tests trailing relatif

## [2.0.8] - 2026-04-12

### Fixed
- **FIX CRITIQUE : Trailing stop prioritaire + breakeven stop** — BUG : le `stale_negative_exit` (2 min) était vérifié AVANT le trailing stop dans `_tick_single_slot()`. Quand une position gagnante (peak ≥ activation 0.10%) retombait en négatif, le stale fermait la position en perte (-$1.41) au lieu du trailing stop qui aurait fermé en profit (+$1.50 typique). L'ordre des exit checks était : SL/TP → Expiration → **Stale** → Trailing → Momentum. Le stale court-circuitait le trailing.
  - **Réordonnancement** : trailing stop vérifié AVANT stale exit. Nouvel ordre : SL/TP → Expiration → **Trailing stop** → **Breakeven stop** → Stale → Momentum.
  - **Breakeven stop (nouveau)** : filet de sécurité — si peak ≥ activation/2 (0.05%) et PnL retombe ≤ 0%, fermeture immédiate au breakeven. Protège les positions qui étaient profitables mais n'atteignaient pas le seuil d'activation du trailing. Sans ce filet, ces positions étaient fermées en perte par le stale négatif (-$1 à -$5).
  - **Stale exit préservé** : gère uniquement les positions qui n'ont JAMAIS été en profit significatif (peak < 0.05%).

- **SHORTS BIDIRECTIONNELS — 0 short en 24h** — Le robot n'ouvrait AUCUN short en marché range car :
  1. Le reversal check exigeait **2 signaux overbought** (RSI ≥ 70 + StochRSI ≥ 80) — quasi impossible en range avec RSI à 55
  2. Le filtre `short_min_score` exigeait abs(score) ≥ 30 pour un trade **contrarian** — absurde car un score bullish positif CONFIRME le surachat
  - **Seuil reversal 2→1** : un seul signal overbought/oversold suffit pour déclencher un reversal
  - **Nouveau signal "majorité bearish"** : si ≥2 règles bearish sont satisfaites ET plus de bearish que bullish → overbought signal. Détecte les retournements en range même sans RSI extrême
  - **`short_min_score` supprimé pour reversals** : le filtre abs(score) bloquait les trades contrarians. Gardé uniquement pour les shorts directionnels (non-reversal). La protection contre les mauvais shorts est assurée par trailing stop, breakeven stop, et stale exit

### Added
- **4 tests `TestTrailingStopPriorityV208`** :
  - `test_trailing_fires_before_stale_negative` — position peak > activation qui retombe en négatif → trailing ferme (pas stale)
  - `test_breakeven_stop_protects_small_gains` — peak entre activation/2 et activation, PnL retombe à 0% → breakeven ferme
  - `test_stale_still_works_for_never_profitable` — position jamais profitable → stale négatif ferme normalement
  - `test_exit_priority_order` — vérification statique que trailing/breakeven apparaissent AVANT stale dans le source code
- **7 tests `TestShortBidirectionalV208`** :
  - `test_reversal_fires_with_bearish_majority` — 2 bearish > 0 bullish → short reversal
  - `test_reversal_fires_with_bullish_majority` — 2 bullish > 0 bearish → long reversal
  - `test_reversal_no_fire_with_equal_rules` — égalité → pas de reversal
  - `test_short_trailing_stop_symmetric` — calcul PnL symétrique pour short
  - `test_short_breakeven_stop_symmetric` — breakeven protection pour short
  - `test_no_short_min_score_for_reversals` — short_min_score ne bloque plus les reversals
- **Tests mis à jour dans 3 fichiers** : `test_scalping_audit.py`, `test_short_optimization.py`, `test_stability.py` — adaptés au seuil de reversal à 1

### Technical
- Modifié : `backend/app/services/paper_trading_service.py` — Réordonnancement exit checks + breakeven stop + refonte `_scalping_reversal_check` (seuil 2→1, majorité bearish, bypass short_min_score)
- Modifié : `backend/tests/test_pivot_v200.py` — 11 nouveaux tests (4 trailing priority + 7 shorts bidirectionnels)
- Modifié : `backend/tests/test_scalping_audit.py` — 3 tests reversal mis à jour pour seuil à 1
- Modifié : `backend/tests/test_short_optimization.py` — 7 tests reversal mis à jour (3 modifiés, 3 ajoutés, 1 supprimé)
- Modifié : `backend/tests/test_stability.py` — 3 tests reversal mis à jour (1 modifié, 1 ajouté)
- Nombre total de tests : 1608→1617 (9 ajoutés net)

## [2.0.7] - 2026-04-12

### Changed
- **Sorties scalping recalibrées pour marchés en range** — L'audit runtime du premier trade scalping débloqué (ID #448) révèle le problème : peak à +0.14% (< activation trailing 0.15%), le trailing ne s'activait JAMAIS. La position dérivait pendant 15 min (stale) en perdant tous les gains accumulés (+$3.51 au pic, retombé à +$2.23).
  - `stale_exit_minutes` 15→**5** : rotation 3× plus rapide, libère le slot pour de meilleures opportunités
  - `stale_negative_exit_minutes` 5→**2** : couper les pertes encore plus vite
  - `trailing_stop_activation_pct` 0.15%→**0.10%** : protège les gains dès +0.10% (le peak à 0.14% aurait activé)
  - `trailing_stop_pct` 0.10%→**0.06%** : trail plus serré, recul max 0.06% depuis le peak avant fermeture
  - Capture minimale garantie : 0.10% - 0.06% = 0.04% ($1 sur $2500)

### Added
- **6 tests `TestScalpingV207FastExit`** : validation des 4 paramètres recalibrés + capture minimum + isolation aggressive

### Technical
- Modifié : `backend/app/services/trading_profile_service.py` — 4 paramètres scalping recalibrés
- Modifié : 8 fichiers de test — assertions mises à jour pour les nouvelles valeurs
- Nombre total de tests : 1598→1604 (6 ajoutés, 0 supprimé).

## [2.0.6] - 2026-04-12

### Changed
- **Gate micro-tendance DÉSACTIVÉ** (`min_micro_trend_long` 1→0) — L'audit post-v2.0.4 révèle 135/135 ticks scalping (100%) encore bloqués par `micro_trend_insufficient`. Tous avaient `micro_trend_score=-2`, `decision_score=65`, `market_quality=59`. Le gate à mt≥1 restait trop restrictif dans les phases latérales. Désactivé : la protection micro-trend reste via `structural_proofs` (mt≥3 = 1 preuve sur 4 requises).

### Added
- **Certification profil UI** (`🔒 Profil certifié par le serveur`) — Bandeau vert affichant le profil réellement actif côté backend, synchronisé via `status.account.active_profile` à chaque poll. Alerte orange clignotante en cas de désynchronisation frontend/backend.
- **`active_profile` dans PaperAccountResponse** — Le champ est désormais remonté dans chaque réponse `/paper/status`, éliminant la dépendance à un appel `GET /paper/profile` séparé.
- **Timer de position live** — Chronomètre `hh:mm:ss` (ou `mm:ss` si < 1h) sur chaque carte de position ouverte, basé sur `entry_ts`, rafraîchi chaque seconde.
- **4 tests mis à jour** pour refléter `min_micro_trend_long=0` (+ 1 nouveau test `economic_gate_still_active`).

### Technical
- Modifié : `backend/app/services/trading_profile_service.py` — `min_micro_trend_long` scalping 1→0
- Modifié : `backend/app/schemas/paper_trading.py` — `active_profile` ajouté à `PaperAccountResponse`
- Modifié : `frontend/src/types/api.ts` — `active_profile` ajouté à `PaperAccountItem`
- Modifié : `frontend/src/components/PaperTradingPanel.tsx` — Composant `PositionTimer`, bandeau certification profil, sync `backendProfile` via polling
- Modifié : `backend/tests/test_pivot_v200.py` — Tests `TestScalpingV206MicroTrendDisable` (remplace `V204`)
- Nombre total de tests : 1598 (0 ajouté net).

## [2.0.5] - 2026-04-12

### Fixed
- **INCIDENT GRAVE : Bascule silencieuse du profil actif vers "conservative"** — Le full reset (`reset_account()`) détruisait le compte et en recréait un avec le default SQLAlchemy `active_profile="conservative"`, écrasant le profil choisi par l'utilisateur (ex: scalping). Le même problème existait dans `get_or_create_account()` lors de la création initiale d'un compte. Corrigé : le profil est maintenant **capturé avant la purge** et **restauré dans le nouveau compte**. La route `POST /paper/autonomous/start` pose désormais le profil explicitement.
- **Frontend : `handleFullReset` ne restaurait pas le profil** — Après un full reset, le frontend ne rappelait jamais `setPaperProfile()`. Le profil "conservative" (default) persistait. Corrigé : `handleFullReset` restaure explicitement le profil sélectionné après le reset.
- **Frontend : `handleStartAuto` ne posait pas le profil** — Le mode auto custom démarrait sans poser le profil sélectionné. Corrigé : appel `setPaperProfile()` avant le démarrage.

### Added
- **11 tests de non-régression** (`TestProfilePreservation`) :
  - Full reset préserve scalping / aggressive / balanced
  - Full reset avec `preserve_profile` explicite
  - `get_or_create_account` avec profil ne crée pas conservative
  - `get_or_create_account` ne réécrit pas un profil existant
  - `POST /paper/tick` ne modifie pas le profil
  - `POST /paper/account` ne modifie pas le profil existant
  - `POST /paper/account/reset` préserve le profil
  - Full reset sans compte existant → conservative (attendu)
  - `POST /paper/autonomous/start` avec profile=scalping → scalping

### Technical
- Modifié : `backend/app/services/paper_trading_service.py` — `reset_account()` capture et restaure le profil ; `get_or_create_account()` accepte `active_profile`
- Modifié : `backend/app/services/autonomous_manager.py` — `_set_profile()` passe le profil à `get_or_create_account`
- Modifié : `backend/app/api/routes/paper_trading.py` — `start_autonomous()` force `account.active_profile = request.profile`
- Modifié : `frontend/src/components/PaperTradingPanel.tsx` — `handleFullReset` restaure le profil ; `handleStartAuto` pose le profil
- Nombre total de tests : 1587→1598 (11 ajoutés, 0 supprimé).

## [2.0.4] - 2026-04-11

### Changed
- **Gate micro-tendance assoupli** (`min_micro_trend_long` 2→1) — L'audit post-v2.0.3 révèle que 966/966 ticks scalping (100%) sont bloqués par `micro_trend_insufficient`. Tous avaient `micro_trend_score=-2` et `decision_score=65` (bien au-dessus du seuil 30). Le gate à mt≥2 exigeait une tendance haussière confirmée ; mt≥1 suffit pour un début de reprise. mt≤0 reste bloqué.
- **Safety bounds learning** — Ajout de `min_micro_trend_long: (0, 5)` aux bornes de sécurité du learning service.

### Added
- **Export enrichi tick-par-tick** (`EnrichedExportService`) — Service + schéma + endpoint `GET /audit/enriched-export`. Export complet de chaque tick avec :
  - Prix BTC + variation % inter-tick
  - Décision moteur (action, score, confidence)
  - Raison de non-trade + catégorie de rejet
  - Position ouverte, PnL latent/réalisé
  - Market quality context (micro_trend_score, volume_ratio)
  - Ventilation des refus par gate (`GateBlockDistribution`)
  - Détection des tendances BTC ratées (`MissedTrendAnalysis`)
- **Learning runtime** (`LearningService.learn_from_runtime()`) — Analyse les TickActivityLog pour identifier les gates sur-bloquants. Endpoint `POST /learning/learn-runtime`.
  - Suggestion 15 : détecte si le gate micro-trend bloque > 50% des ticks avec score > buy_threshold
  - Suggestion 16 : détecte si un seul gate bloque > 70% des ticks buy/sell
- **33 nouveaux tests** :
  - `test_enriched_export.py` (25) : export vide, avec données, gate distribution, variation BTC, tendances ratées, learn_from_runtime, safety bounds, endpoints
  - `TestScalpingV204MicroTrendRelax` dans `test_pivot_v200.py` (8) : mt=1 passe, mt=0 bloqué, mt négatif bloqué, autres params inchangés

### Technical
- Nouveau : `backend/app/schemas/enriched_export.py` — Schémas Pydantic (EnrichedTickRow, GateBlockDistribution, MissedTrendAnalysis, EnrichedExportSummary, EnrichedExportResponse)
- Nouveau : `backend/app/services/enriched_export_service.py` — Service d'export enrichi (~270 LOC)
- Nouveau : `backend/tests/test_enriched_export.py` — 25 tests
- Modifié : `backend/app/services/trading_profile_service.py` — min_micro_trend_long 2→1 + commentaire d'audit
- Modifié : `backend/app/services/learning_service.py` — +SAFETY_BOUNDS min_micro_trend_long, +learn_from_runtime() (~120 LOC)
- Modifié : `backend/app/api/routes/audit.py` — +endpoint GET /audit/enriched-export
- Modifié : `backend/app/api/routes/learning.py` — +endpoint POST /learning/learn-runtime
- Modifié : `backend/app/schemas/__init__.py` — exports enriched_export
- Modifié : `backend/tests/test_pivot_v200.py` — 8 tests ajoutés (TestScalpingV204MicroTrendRelax), 1 test modifié (min_micro_trend_long 2→1)
- Nombre total de tests : 1554→1587 (33 ajoutés, 0 supprimé).

## [2.0.3] - 2026-04-11

### Changed
- **Scalping plus sélectif** — Mini-lot correctif post-audit runtime (57 trades, 52 closed_stale = 91.2%, 4 trailing_stop seulement).
  - **buy_threshold 25→30** : exige un signal directionnel plus fort pour ouvrir un long scalping. Filtre les entrées sur bruit.
  - **min_score 25→30** : relève le plancher de score composite minimum. Les trades à score faible qui finissaient stale sont rejetés.
  - **trailing_stop_activation_pct 0.20→0.15** : le trailing s'active plus tôt. L'audit montre que 91% des trades n'atteignaient jamais 0.20%. En abaissant à 0.15%, plus de trades activent le trailing (seul vrai créateur de valeur du run). Trail maintenu à 0.10%.

### Added
- **Gate micro-tendance obligatoire** (`min_micro_trend_long=2`) — Nouveau paramètre `TradingProfileParams.min_micro_trend_long`. Le scalping exige désormais un `micro_trend_score ≥ 2` pour ouvrir un long. C'est un VETO indépendant des preuves structurelles (qui vérifient ≥ 3 mais ne sont qu'1 preuve parmi 4). Sans micro-tendance, pas d'entrée long.
- **Raison de non-trade `micro_trend_insufficient`** dans le journal — Nouveau label pour le diagnostic des entrées rejetées par le gate micro-tendance.
- **14 nouveaux tests** (`TestScalpingV203MiniLot` dans `test_pivot_v200.py`) :
  - Configuration : buy_threshold 30, min_score 30, trailing_activation 0.15, min_micro_trend_long 2
  - Isolation : paramètres non ciblés inchangés, aggressive sanctuarisé, conservative non affecté
  - Économie : gate économique toujours valide, capture minimum cohérente
- **3 tests mis à jour** (`TestScalpingRecalibration` dans `test_scalping_audit.py`, `TestScalpingProfileV200` + `TestReasonLabels` dans `test_pivot_v200.py`)

### Fixed
- **Auto-activation paper trading** — Le compte paper trading est désormais auto-activé quand un tick est demandé. Avant, si le compte était inactif (après un full reset ou au premier lancement), le tick retournait "Paper trading désactivé. Activez-le via POST /paper/account." et l'utilisateur devait faire une requête POST manuelle. Maintenant :
  - **Backend** : `POST /paper/tick` auto-active le compte si inactif (+ configure multi-slot ≥3)
  - **Frontend** : `doAutoTick` et `manualTick` font du self-healing (si "inactive" → activation + retry)
  - **Frontend** : `handleStartAuto` (bouton "Auto custom") active le compte comme "Lancer le Robot"
  - **Backend** : Le message d'erreur est devenu user-friendly ("Cliquez sur Lancer le Robot" au lieu de "POST /paper/account")

### Technical
- Modifié : `backend/app/schemas/journal.py` — Ajout champ `min_micro_trend_long` à `TradingProfileParams`
- Modifié : `backend/app/services/trading_profile_service.py` — Preset scalping recalibré (3 paramètres + 1 nouveau)
- Modifié : `backend/app/services/paper_trading_service.py` — Gate micro-trend dans la boucle d'entrée (~30 LOC) + message UX "Cliquez sur Lancer le Robot"
- Modifié : `backend/app/api/routes/paper_trading.py` — Auto-activation du compte dans `POST /paper/tick`
- Modifié : `backend/app/services/journal_service.py` — Label `micro_trend_insufficient` ajouté à `REASON_LABELS`
- Modifié : `frontend/src/hooks/usePaperTrading.ts` — Self-healing dans `doAutoTick` et `manualTick` (inactive → activate + retry)
- Modifié : `frontend/src/components/PaperTradingPanel.tsx` — `handleStartAuto` active le compte avant de démarrer
- Modifié : `backend/tests/test_pivot_v200.py` — 14 tests ajoutés, 2 mis à jour
- Modifié : `backend/tests/test_scalping_audit.py` — 3 tests mis à jour
- Modifié : `backend/tests/test_paper_trading.py` — 1 test endpoint mis à jour (inactive → no_price après auto-activation)
- Nombre total de tests : 1542→1554 (14 ajoutés, 0 supprimé).

## [2.0.2] - 2026-04-11

### Added
- **RuntimeCorrelationService** — Service de corrélation trades vs mouvement BTC réel
  - Corrèle chaque trade fermé avec les bougies BTC (1h, fallback 4h) : tendance à l'entrée (up/down/flat), mouvement BTC pendant le trade, mouvement BTC après la sortie.
  - **Détection de sorties prématurées** : identifie les trades `closed_stale` suivis d'un mouvement BTC favorable (>0.15%). Flag `missed_favorable_move`.
  - **Efficacité de capture** : mesure le % du mouvement BTC réellement capturé par le trade (0% si direction contraire, 100% si prise optimale, cap à 100%).
  - **Détection de mouvements manqués** : identifie les gaps entre trades pendant lesquels BTC a bougé significativement sans position ouverte.
  - **Endpoint `GET /audit/runtime-correlation`** avec paramètre `missed_threshold_pct` configurable.
- **Learning enrichi contexte BTC** — 5 nouvelles colonnes sur `LearningSignal` :
  - `btc_trend_at_entry` (VARCHAR(10)) : tendance BTC au moment de l'entrée
  - `btc_move_during_pct` (FLOAT) : variation BTC % pendant le trade
  - `btc_move_after_exit_pct` (FLOAT) : variation BTC % dans la bougie post-sortie
  - `missed_favorable_move` (INTEGER) : flag si sortie stale prématurée + BTC favorable après
  - `capture_efficiency_pct` (FLOAT) : % du mouvement BTC capturé
- **`_compute_btc_context()`** dans `LearningService.record_sample()` — enrichit automatiquement chaque échantillon d'apprentissage avec le contexte BTC (graceful degradation si pas de bougies).
- **17 nouveaux tests** (`test_runtime_correlation.py`) :
  - `TestRuntimeCorrelationService` (10) : DB vide, trades sans bougies, 1 trade + bougies, fallback 4h, missed movement, premature stale, capture efficiency (positif + négatif), summary stats
  - `TestLearningBtcContext` (4) : record sample avec/sans bougies, missed favorable flaggé, non-stale non flaggé
  - `TestRuntimeCorrelationEndpoint` (3) : 200 vide, paramètre threshold, summary zéro
- **Migration `migrate_v202.py`** — Ajout des 5 colonnes BTC context à la table `learning_signal` en PostgreSQL.

### Technical
- Nouveau fichier : `backend/app/services/runtime_correlation_service.py` (~320 LOC)
- Nouveau fichier : `backend/app/schemas/runtime_correlation.py` (~100 LOC)
- Nouveau fichier : `backend/tests/test_runtime_correlation.py` (~465 LOC)
- Nouveau fichier : `backend/migrate_v202.py`
- Modifié : `backend/app/models/learning.py` (5 colonnes ajoutées)
- Modifié : `backend/app/services/learning_service.py` (`_compute_btc_context()` ajouté)
- Modifié : `backend/app/schemas/learning.py` (5 champs ajoutés à `LearningSignalItem`)
- Modifié : `backend/app/api/routes/audit.py` (endpoint `GET /audit/runtime-correlation` ajouté)
- Nombre total de tests : 1525→1542 (17 ajoutés, 0 supprimé).

## [2.0.1] - 2026-04-10

### Changed
- **Slot aggressive rendu vivant** — Le slot aggressive était muet en runtime car le timeframe 4h produisait un score quasi-statique (~24) sous le buy_threshold global (25). L'action restait "attendre" sur chaque tick.
  - **Timeframe 4h→1h** : 4× plus de données fraîches, scores plus dynamiques. Le 1h reste "macro" vs le 15m scalping. `history_days` reste 7 (168 candles 1h = couverture suffisante pour les indicateurs).
  - **buy_threshold explicite 25→20** : le score runtime (~24) passe désormais le seuil. Avant, le seuil global 25 bloquait systématiquement.
  - **sell_threshold explicite 20→15** : permet les shorts agressifs avec un score modérément négatif, compensant le biais haussier structurel de BTC.

### Added
- **13 tests** (`TestAggressiveSlotCalibration` dans `test_paper_trading.py`) :
  - Configuration : timeframe 1h, buy_threshold 20, sell_threshold 15
  - Distinction scalping : timeframe ≠, TP >, SL >, durée >, pas de trailing, pas de gate économique, pas de proofs structurels, stale exit 12× plus long
  - Intégration multi-slot : fonctionne dans l'orchestrateur avec scalping
  - Seuils : score 21 → "acheter" (OK), score 24 bloqué avec ancien seuil 25 → passe avec nouveau 20
  - Test de régression short : score -16 → "vendre" avec nouveau sell_threshold 15

### Technical
- `PROFILE_PRESETS["aggressive"]` : 3 paramètres modifiés (`analysis_timeframe`, `buy_threshold`, `sell_threshold`). Tous les autres paramètres inchangés — l'identité du slot est préservée.
- Nombre total de tests : 1512→1525 (13 ajoutés, 0 supprimé).

## [2.0.0] - 2026-04-10

### Fixed
- **Gate économique scalping mathématiquement impossible** — `expected_capture_pct` était `None`, ce qui retombait sur `trailing_stop_activation_pct` = 0.20%. Or le seuil requis = RT cost (0.31%) × min_ev_multiple (1.5) = 0.465%. Donc 0.20% < 0.465% → **FAIL sur 100% des ticks scalping**. Corrigé à `expected_capture_pct=0.50` (capture réaliste entre trailing 0.20% et TP 0.80%), ce qui donne 0.50% > 0.465% ✓.
- **Stale exit tue les trades profitables (trade #364)** — Le seuil de stagnation des profils tight utilisait `profit_take_pct` (0.8%). Un trade à +0.46% après 15 min était classé "stagnant" (0.46 < 0.8) et fermé en `closed_stale`, alors que le trailing stop (activation 0.20%) était actif et aurait dû gérer la sortie. Corrigé : le seuil utilise désormais `trailing_stop_activation_pct` (0.20%) quand disponible, avec fallback sur `profit_take_pct`. Résultat : un trade à +0.46% n'est plus stagnant → le trailing stop gère.
- **Multi-slot perdu après full reset** — `FullResetRequest.max_open_positions` et `PaperAccountCreate.max_open_positions` avaient un default de 1. Le frontend envoyait le reset sans `max_open_positions`, donc le compte était recréé en mono-position. Le slot aggressive ne pouvait plus tourner en parallèle du scalping. Corrigé : default passé de 1 à 3 dans les deux schemas. L'endpoint `autonomous/start` configure aussi `max_open_positions` inconditionnellement (pas seulement quand `is_active=False`).

### Added
- **Economic viability gate** — Le moteur scalping évalue le coût round-trip AVANT d'ouvrir un trade. Si la capture attendue ne couvre pas 1.5× le coût RT (realistic = 0.31%), le trade est refusé. Méthode `TradingCostModel.estimate_economic_viability()`. Raison de rejet loggée : `economic_viability_low`.
- **Structural proofs gate** — Le scalping exige ≥2 preuves structurelles (volume ≥1.0x, micro-trend ≥3, price_position favorable, range_width_atr ≥1.5) pour ouvrir. Sans preuves, le trade est refusé. Raison : `structural_proof_insufficient`.
- **Momentum fade restricted** — Nouveau mode `restricted` : le momentum fade ne se déclenche que si le pic ≥ 0.35% ET que la sortie est net-positive après coûts estimés. Le momentum fade en mode `enabled` (aggressive, balanced) reste inchangé.
- **Tick logging enrichi** — 4 nouvelles colonnes : `estimated_round_trip_cost`, `min_capture_required_pct`, `economic_gate_passed`, `rejection_category`. Chaque rejet est catégorisé : economic, structure, volume, no_trade_zone, cooldown, score, risk.
- **41 nouveaux tests** (`test_pivot_v200.py`) : economic viability (8), momentum fade restricted (4), structural proofs (3), scoring refondu (8), profil scalping v2.0 (7), non-régression aggressive (6), tick logging (3), reason labels (2).
- **Migration DB** : `migrate_v200.py` pour PostgreSQL (4 colonnes ajoutées à `tick_activity_log`).

### Changed
- **Slot aggressive sanctuarisé** — Description mise à jour, marqué comme moteur principal de valeur. Pas de gate économique, pas de structural proofs, momentum fade normal. Aucun paramètre modifié.
- **Scoring refondu** — Bollinger 0.4→0.3 et StochRSI 0.5→0.3 en tendance (contexte seulement, plus base d'entrée). Price_position 1.0→1.4, range_quality 0.8→1.2 en tendance. RSI 0.6→0.5 en tendance.
- **Profil scalping refondu** — TP 0.6%→0.8%, trailing activation 0.15%→0.20%, max_trades 50→30, min_score 20→25, market_quality 45→50, volume_ratio 0.7→0.8, economic_gate_enabled=True, min_ev_multiple=1.5, min_structural_proofs=2, momentum_fade_mode=restricted, momentum_fade_min_amplitude_pct=0.35.

### Technical
- `TradingCostModel.estimate_economic_viability()` : évaluation pré-entrée avec round_trip_cost, min_capture_required, expected_net_pnl, is_viable, rejection_reason.
- `TradingProfileParams` : 5 nouveaux champs (economic_gate_enabled, min_ev_multiple, expected_capture_pct, momentum_fade_mode, momentum_fade_min_amplitude_pct, min_structural_proofs).
- `TickActivityLog` : 4 nouvelles colonnes nullable (estimated_round_trip_cost, min_capture_required_pct, economic_gate_passed, rejection_category).
- `JournalService.log_tick()` : accepte les 4 nouveaux paramètres.
- `REASON_LABELS` : 2 nouvelles raisons (economic_viability_low, structural_proof_insufficient).
- Nombre total de tests : 1460→1512.

## [1.9.9] - 2026-04-10

### Fixed
- **Score technique ne sature plus à 100** — Le soft ceiling plafonne à 88 en conditions normales (95 avec volume ≥ 1.5x + unanimité parfaite). Les signaux NEUTRAL diluent réellement le score (-4%/signal). Le convergence boost exige vol_ratio ≥ 1.2 (était 0.8) et raw_score ≥ 0.75 (était 0.6).
- **Quality gate = veto réel** — Seuil scalping relevé 35→45. Mid-range veto renforcé : micro_trend_score ≥ 3 requis (était > 0). Le profil aggressive a désormais un gate minimum (25).
- **Anti-churn stale négatif** — Multiplicateur stale INVERSÉ de 0.5 (réduisait le cooldown !) à 2.0 (le double). Stale négatif : multiplicateur 3x + plancher 4 min incompressible. max_cooldown scalping 5→10 min.

### Added
- **Runtime trace quality gate** — 8 nouvelles colonnes dans `tick_activity_log` : `market_quality_score`, `volume_ratio`, `price_position_pct`, `range_width_atr`, `micro_trend_score`, `vwap_distance_pct`, `quality_gate_passed`, `quality_gate_reason`. Chaque tick est auditable : pourquoi un trade a été autorisé ou refusé.
- **34 nouveaux tests** (`test_runtime_truth.py`) : runtime trace (4), anti-saturation (6), quality gate veto (8), anti-churn (8), non-régression (8).

### Technical
- `_check_market_quality()` retourne désormais un tuple `(reason, quality_data)` au lieu d'un simple string, pour propager les données de qualité au journal.
- `JournalService.log_tick()` accepte les paramètres quality gate.
- `SmartCooldownService` : pénalité spécifique stale_negative avec détection `last_pnl < 0`.
- `compute_composite_score()` : neutral dilution, soft ceiling, convergence boost durci.
- Tests : 1460 passing (était 1426), tsc clean.

## [1.9.8] - 2026-04-10

### Added
- **Market Structure Service** — Évaluation de la qualité de marché avant ouverture de position
  - `MarketStructureService.assess_quality()` : calcul de price_position, range_width_atr, volume_ratio, micro_trend_score, vwap_distance, quality_score (0-100)
  - `is_no_trade_zone()` : détection des marchés sans edge (tight range + low volume + no trend)
  - `is_long_quality_sufficient()` : filtrage spécifique des longs médiocres (milieu de range, pas de micro-tendance)
  
- **Nouveaux signal interpreters (price/volume/structure)**
  - `interpret_price_position()` : position du prix dans le range récent (haut/bas/milieu → edge/bruit)
  - `interpret_range_quality()` : qualité du range (tight range + low volume = frein fort sur le score)
  - Série de candles propagée depuis SignalService → DecisionService → PaperTradingService

- **No-trade zone pour le scalping** — Le moteur refuse de trader quand le marché est bruité
  - Gate `_check_market_quality()` dans `_tick_single_slot()` avant ouverture
  - Configurable via profil : `min_market_quality`, `min_volume_ratio`, `long_quality_filter`
  - Scalping preset : qualité min 35/100, volume min 0.7x SMA20, filtre long activé

- **Learning Layer v3 — Rejection du bruit**
  - Suggestion 13 : détection pattern stale-négatif dominant (> 30% des trades)
  - Suggestion 14 : détection longs scalping à score homogène avec WR < 40%
  - Nouveaux safety bounds : `min_market_quality`, `min_volume_ratio`

- **55 nouveaux tests** : MarketStructureService, interpret_price_position, interpret_range_quality, score decompression, market quality gating, profile params, learning suggestions, non-régression

### Changed
- **Score composite décompressé** — Les scores cessent de saturer à 70-72
  - Poids Bollinger réduit en tendance : 0.6 → 0.4 (ne discrimine pas en marché haussier)
  - Poids StochRSI réduit en tendance : 0.7 → 0.5 (même problème)
  - Nouveaux poids pour price_position et range_quality dans les régimes trending/ranging
  - Convergence boost conditionné au volume (vol_ratio >= 0.8) et à l'absence de range quality
  - Convergence boost activé à raw_score >= 0.6 (au lieu de 0.5)
  - Compression renforcée pour signaux divisés : 0.75 → 0.65
  - Compression si range_quality présent et score > 0.5 : × 0.75

- **Profil scalping recalibré** — Description et paramètres mis à jour

### Fixed
- Score homogène 70-72 sur tous les ticks du run nocturne → Le score varie enfin selon la qualité du marché
- Longs médiocres ouverts systématiquement → Le filtre market quality bloque les entrées sans structure
- Stale négatif comme mode d'échec dominant → Moins de trades ouverts = moins de stale négatifs

### Technical
- 1426 tests backend, tous passants ✅ (+55 nouveaux)
- `tsc --noEmit` sans erreur ✅
- Nouveau fichier : `backend/app/services/market_structure_service.py`
- Nouveau fichier : `backend/tests/test_market_structure.py`

## [1.9.7] - 2026-04-09

### Added
- **Mode autonome backend (headless)** — Le robot peut tourner sans navigateur ouvert
  - **AutonomousManager** : singleton thread-safe qui exécute des ticks automatiques côté serveur à intervalle configurable (5s–3600s)
  - **POST /paper/autonomous/start** : démarre le mode headless avec profil et intervalle configurables
  - **POST /paper/autonomous/stop** : arrête le mode headless (positions ouvertes conservées)
  - **GET /paper/autonomous/status** : retourne l'état complet (running, tick_count, trade_count, uptime, last_result)
  - **Chaîne d'exécution clarifiée** : le prix BTC est fetché directement par le backend via Binance HTTP API — aucune dépendance au frontend
  - **15 tests** : singleton, start/stop, validation intervalle, endpoints HTTP

- **Mode low-bandwidth frontend** — Réduction de la consommation réseau
  - **Toggle 🌙** dans la toolbar : coupe le WebSocket Binance et réduit tous les pollings
  - **useLivePrice({ enabled })** : le WebSocket peut être désactivé dynamiquement
  - **Pollings réduits** : alertes 60s→300s, news 300s→900s en mode low-bandwidth

- **UI headless dans PaperTradingPanel** — Contrôle du mode autonome
  - Bandeau vert "🌙 Mode Headless actif" avec tick_count, trade_count, uptime, dernière action
  - Bouton "Lancer Headless" visible quand ni auto-tick ni headless actif
  - Bouton "Arrêter Headless" dans le bandeau actif
  - Polling léger du statut headless toutes les 10s

### Technical
- 1371 tests backend, tous passants ✅ (+15 nouveaux)
- `tsc --noEmit` sans erreur ✅
- Nouveau fichier : `backend/app/services/autonomous_manager.py`
- Nouveau fichier : `backend/tests/test_autonomous.py`
- Types TS ajoutés : `AutonomousStatus`
- API client ajouté : `startAutonomous()`, `stopAutonomous()`, `getAutonomousStatus()`

## [1.9.6] - 2026-04-09

### Fixed
- **BUG CRITIQUE : Double ouverture du même slot** — Correction d'une race condition TOCTOU (Time-of-Check-Time-of-Use) qui permettait à deux requêtes `/paper/tick` concurrentes d'ouvrir chacune une position sur le même slot. Le bug se manifestait par deux trades id 237 et 238 tous deux ouverts sur le slot "scalping" simultanément.
  - **Cause racine** : `_tick_single_slot()` vérifiait le slot libre, puis `_open_position()` insérait sans revérifier. Deux requêtes concurrentes passaient la vérification avant que l'une n'ait committé.
  - **Guard applicatif** : `_open_position()` re-vérifie désormais l'absence de position ouverte sur le slot juste avant l'INSERT. Retourne `None` si le slot est occupé, avec log explicite.
  - **Verrou HTTP** : Le endpoint `POST /paper/tick` est protégé par un `threading.Lock()`. Un seul tick s'exécute à la fois. Si un tick est déjà en cours, la requête retourne un résultat neutre "hold".
  - **5 tests dédiés** : impossibilité d'ouvrir 2 positions sur le même slot, autorisation multi-slot légitime, slot libéré après fermeture, 5 appels rapides consécutifs.

### Changed
- **SL scalping encore resserré** : 0.25% → **0.20%** — Perte max réduite de $6.25 à $5.00 sur $2500. R:R théorique amélioré de 2.4:1 à **3:1**.
- **Stale exit positions en perte accéléré** : 8 min → **5 min** — Les positions à PnL négatif sortent plus vite, réduit les grosses pertes par dérive.
- **Short min score abaissé** : 30 → **25** — La 2-convergence des oscillateurs (v1.9.4) est le vrai filtre. Le min_score en complément n'a pas besoin d'être aussi haut.
- **Short exit score threshold remonté** : 25 → **30** — Les shorts ont plus de temps avant fermeture par signal contraire. En marché haussier, un score de 25 est trop facilement atteint.
- **Short min hold réduit** : 60s → **45s** — Compromis entre respiration et capture rapide du pullback.

### Technical
- 1356 tests backend, tous passants ✅ (11 nouveaux tests : 5 slot invariant, 3 stale exit v1.9.6, 3 short rebalance v1.9.6)
- `tsc --noEmit` sans erreur ✅
- Pas de changement frontend (corrections backend uniquement)

## [1.9.5] - 2026-04-09

### Added
- **StabilityAuditService** — Nouveau service de diagnostic de stabilité du moteur
  - Détection d'oscillation directionnelle (flip long↔short entre fenêtres)
  - Homogénéité des scores (écart-type, distribution)
  - R:R effectif vs théorique
  - Domination des types de sortie (destructrice vs diverse)
  - Analyse gain/perte détaillée (profit factor, top3 pertes, médianes)
  - Verdict global : UNSTABLE / IMPROVING / STABLE avec score 0-100
- **Endpoint GET /audit/stability** — Diagnostic de stabilité accessible via API
- **Stale exit asymétrique** — Positions en perte sortent après 8 min (`stale_negative_exit_minutes`), positions plates gardent 15 min
- **Momentum fade configurable** — Rétention du pic PnL configurable via `momentum_fade_retention` (0.55 au lieu du hardcodé 0.4)
- **Learning stability** — 3 nouvelles suggestions d'ajustement :
  - Déséquilibre directionnel excessif (>85% longs ou >85% shorts)
  - R:R asymétrique (pertes >> gains) → suggestion resserrement SL
  - Sortie dominante destructrice → suggestion ajustement stale
- **54 nouveaux tests** dans `test_stability.py` : params, stability audit, direction balance, score homogeneity, R:R, exit domination, oscillation, verdict, stale négatif, momentum fade, learning stability, endpoint, convergence boost, signal contraire, reversal check

### Changed
- **SL scalping resserré** : 0.35% → **0.25%** — Pertes max réduites de $8.75 à $6.25 sur $2500
- **TP scalping élargi** : 0.5% → **0.6%** — R:R théorique amélioré de 1.43:1 à **2.4:1**
- **Trailing stop activation relevée** : 0.08% → **0.15%** — Plus de micro-activations destructrices
- **Trailing stop trail resserré** : 0.12% → **0.10%** — Protège mieux les gains une fois activé
- **Momentum fade rétention** : 40% → **55%** — Les trades gardent plus de gains avant de sortir
- **Buy threshold relevé** : 20 → **25** — Filtre les longs médiocres
- **Sell threshold relevé** : 15 → **20** — Plus sélectif
- **Min score relevé** : 15 → **20** — Plancher de qualité augmenté
- **Short min score réduit** : 40 → **30** — La 2-convergence suffit comme filtre
- **Short exit threshold réduit** : 35 → **25** — Compromis entre 10 (trop bas) et 35 (trop haut)
- **Short min hold réduit** : 90s → **60s** — Pullbacks rapides à capter
- **Signal contraire longs relevé** : -10 → **-15** — Plus de tolérance au bruit
- **Convergence boost factor** : 0.4 → **0.5** — Meilleure discrimination des scores
- **Compression signaux divisés** : 0.85 → **0.75** — Setups ambigus mieux pénalisés

### Technical
- 1345 tests backend (+54), tous passing ✅
- `tsc --noEmit` sans erreur ✅
- Aucune donnée existante supprimée
- StabilityAuditService : 300 LOC
- Safety bounds ajoutés pour momentum_fade_retention, stale_negative_exit_minutes

## [1.9.4] - 2026-04-09

### Changed
- **Mean reversion beaucoup plus sélective** : Exige maintenant **2 signaux convergents** de surachat/survente au lieu de 1 seul. En marché haussier, 1 seul RSI overbought est normal et ne justifie pas un short. Réduit drastiquement la surcorrection vers le short.
- **Short exit score threshold relevé** : 20 → **35**. En marché haussier, un score de 20+ est quasi-permanent. Avec 35, il faut un vrai signal haussier fort pour tuer un short.
- **Short min score relevé** : 25 → **40**. Les shorts avec `abs(score) < 40` sont rejetés. Réduit les shorts médiocres qui se ressemblent tous.
- **Short min hold allongé** : 60s → **90s**. Plus de temps pour que le pullback se développe.
- **SL scalping resserré** : 0.4% → **0.35%**. Le ratio R/R passe de 1.25:1 à **1.43:1** (TP 0.5% / SL 0.35%). Réduit les pertes trop lourdes.
- **Tech score seuil relevé** : 90 → **95** pour le reversal signal. Un tech_score de 90 est trop fréquent pour déclencher un reversal.

### Fixed
- **Timeout `/paper/missed-opportunities`** : L'endpoint faisait ~10 000 requêtes DB individuelles → timeout 45s. Maintenant pré-charge toutes les candles en 1 requête + limite à 500 ticks analysés. Réponse quasi-instantanée.
- **Affichage durée "0.0"** : Les trades courts (<6 min) affichent maintenant la durée en minutes (`2m`, `3m`) au lieu de `0.0h`.

### Technical
- 1291 tests backend, tous passing ✅
- `tsc --noEmit` sans erreur ✅
- Aucune donnée existante supprimée

## [1.9.3] - 2026-04-09

### Added
- **Short Optimization — Réduction des trades short sans valeur économique**
  - **Short exit score threshold** (`short_exit_score_threshold=20`): Le moteur n'abat plus un short dès que le score redevient légèrement positif. Il exige un vrai retournement bullish (score ≥ 20) avant de fermer par signal contraire. Réduit la dominance de la sortie "Signal contraire : acheter".
  - **Short min score** (`short_min_score=25`): Filtre économique des shorts. Un short mean-reversion ne s'ouvre que si le score est suffisamment discriminant. Empêche les shorts à score 69-71 qui finissent en poussière.
  - **Short min hold** (`short_min_hold_seconds=60`): Durée minimale spécifique aux shorts (60s vs 30s pour les longs). Les shorts ont besoin de plus de temps pour capturer un retracement.
  - **Convergence boost**: Boost non-linéaire du score composite quand ≥75% des indicateurs convergent. Compression quand les signaux sont divisés. Casse l'homogénéité des scores autour de 69-71.
  - **Run Value Audit Service** (`RunValueAuditService`): Audit complet de la valeur économique par trade — useful/insignificant/churn, PnL buckets, signal contraire audit, short economics.
  - **Endpoint `/audit/run-value`**: Diagnostic économique du run via GET avec cost_preset paramétrable.
  - **Learning Layer v2** : 3 nouvelles suggestions automatiques pour les shorts (short_min_score, short_exit_score_threshold, short_min_hold_seconds).
  - **Dataset stats short**: `short_trades_useful`, `short_trades_insignificant`, `short_trades_churn`, `pct_short_economically_useful`.
  - **Safety bounds**: Bornes pour les 3 nouveaux paramètres (short_min_score, short_exit_score_threshold, short_min_hold_seconds).
  - **Frontend**: Type `RunValueAuditResponse` + fonction `getRunValueAudit()` dans marketApi.ts.
  - **50 nouveaux tests** : short exit threshold, short min score, short min hold, convergence boost, run value audit service, endpoint, learning suggestions short, usefulness classification, non-regression scalping preset.

### Changed
- **Signal contraire shorts**: Le seuil de sortie est passé de fixe 10 à configurable `short_exit_score_threshold` (défaut 20 pour scalping). Les shorts sous le seuil continuent de vivre.
- **Score composite**: Ajout du convergence boost et de la compression divisée. Les scores ne stagnent plus autour de 69-71 quand les indicateurs convergent fortement.
- **Mean reversion filter**: Les shorts scalping mean-reversion sont maintenant soumis à `short_min_score` avant ouverture. Les shorts à score faible sont rejetés.
- **Min hold direction-aware**: Le paper trading utilise `short_min_hold_seconds` pour les shorts au lieu du `min_hold_seconds` général.

### Technical
- 1273 tests backend (1223 existants + 50 nouveaux), tous passing ✅
- `tsc --noEmit` sans erreur ✅
- Aucune donnée existante supprimée ni format de données changé
- Rétrocompatible : les profils non-scalping ne sont pas affectés

## [1.9.2] - 2026-04-09

### Fixed
- **Full Reset incomplet** : Le full reset ne purgeait que trades, ticks et compte. Les `learning_signal`, `strategy_feedback` et `paper_run` restaient en DB avec des références orphelines. Maintenant le full reset purge 7 tables.
- **JournalPanel et DiagnosticPanel non rafraîchis après reset** : Le `tradeVersion` n'était incrémenté que sur les ticks (ouverture/fermeture), jamais sur les resets. Les panels gardaient des données stale d'un monde purgé. Corrigé : `tradeVersion` incrémenté après full reset.
- **RiskPanel non rafraîchi après reset** : Le RiskPanel ne recevait aucun signal de refresh après un full reset ou un reset daily loss. Ajout de `refreshTrigger` prop + auto-refresh.
- **kill_switch_triggered_at non nettoyé** : Le reset daily loss désactivait le kill switch mais ne remettait pas `kill_switch_triggered_at` à null. Corrigé.
- **Diagnostic "bloqué par position ouverte" persistant** : Après full reset, des ticks orphelins pouvaient polluer le diagnostic. Maintenant résolu par la purge complète des tick_activity_log.

### Added
- **Confirmation backend obligatoire** : `POST /paper/account/reset` exige désormais `confirm: "RESET"` dans le body. Refus 400 si absent ou incorrect.
- **FullResetResponse détaillé** : Le full reset retourne un objet structuré avec `purged` (compteurs par table), `reset_details` (messages lisibles), `message` (résumé), `account` (nouveau compte).
- **FullResetRequest schema** : Validation Pydantic avec `confirm` required + `initial_capital` + `max_open_duration_hours` + `max_open_positions`.
- **UX améliorée des resets** :
  - Full reset : dialog explicite listant tout ce qui sera supprimé + alert post-reset avec résumé
  - Daily loss reset : dialog explicite listant ce qui est conservé + ce qui change
- **20 nouveaux tests** : contrat métier Full Reset (7 tests : purge learning, feedback, runs, ticks, risk, compte, compteurs), contrat métier Daily Loss Reset (7 tests : zeroes counter, deactivates kill switch conditionnel, keeps manual kill switch, ne touche pas trades/learning/runs/ticks), endpoint reset (4 tests : confirm obligatoire, rejet), diagnostic post-reset (2 tests : propre après full reset)

### Changed
- **`reset_account()` retourne `tuple[PaperAccount, dict]`** : Le dictionnaire `purged` contient les compteurs de suppression par table pour traçabilité.
- **Frontend `resetPaperAccount()` envoie `confirm: "RESET"`** automatiquement + retourne `FullResetResponse`.
- **`onResetComplete` callback** ajouté au PaperTradingPanel pour propager les refreshes.

### Technical
- 1223 tests backend (1203 existants + 20 nouveaux), tous passing ✅
- `tsc --noEmit` sans erreur ✅

## [1.9.1] - 2026-04-09

### Added
- **Anti-micro-PnL — Valeur économique des trades** : Le système détecte et filtre les trades sans valeur économique.
  - **Catégories d'utilité** : Chaque trade est classifié (useful / insignificant / churn / loss_useful / loss_destructive)
  - **Coûts estimés** : LearningSignal enrichi avec `cost_estimated`, `pnl_net_estimated`, `usefulness_category`
  - **Seuil économique minimum** : `min_economic_pnl_pct=0.15%` dans le profil scalping
  - **Protection min_hold_seconds** : 30 secondes minimum avant sortie par signal contraire (empêche les fermetures-éclair)
  - **Patterns économiques** : Le learning détecte les patterns par catégorie d'utilité et par bucket de durée
  - **Suggestions anti-churn** : Suggestions automatiques quand trop de trades sont du churn (> 20%) ou insignifiants (> 30%)
  - **Suggestion min_hold** : Détection des signal exits trop rapides (< 1 min) avec PnL insuffisant
  - **Safety bounds** : `min_hold_seconds` ajouté (0–120s)
  - **40 nouveaux tests** (`test_economic_value.py`) : seuil économique, min_hold, classification, learning, suggestions

### Changed
- **Profil scalping recalibré** :
  - `profit_take_pct` : 0.3% → **0.5%** (l'ancien TP ≈ coût round-trip realistic 0.31% → aucune marge nette)
  - `loss_cut_pct` : 0.3% → **0.4%** (ratio R/R 1:1.25 après coûts)
  - `stale_exit_minutes` : 12 → **15** (laisser les trades respirer)
  - Ajout `min_hold_seconds=30` et `min_economic_pnl_pct=0.15`
- **Sortie signal contraire adoucie** :
  - "Signal affaibli" (score ≈ 0) ne ferme plus les positions → il faut un score nettement contraire (≤ -10 ou ≥ 10)
  - Les positions trop jeunes (< min_hold_seconds) sont protégées des fermetures par signal
- **Smart Cooldown anti-churn** :
  - Trade flat/scratch : multiplicateur changé de ×0.5 (réentrait trop vite) → **×1.5** (attend pour un vrai signal)
  - Un trade sans valeur ne doit plus provoquer une réentrée rapide
- **LearningDatasetStats enrichi** : `avg_cost_per_trade`, `avg_pnl_net`, `trades_useful/insignificant/churn`, `pct_economically_useful`, `min_economic_move_pct`
- **LearningSignalItem enrichi** : `cost_estimated`, `pnl_net_estimated`, `usefulness_category`

### Fixed
- **TP structurellement sous le coût** : L'ancien TP de 0.3% était quasi égal au round-trip cost realistic (0.31%), rendant chaque trade gagnant économiquement nul. Corrigé.
- **Signal contraire comme machine à tuer** : La sortie "signal contraire : acheter/vendre" fermait des trades en 5–15 secondes avec PnL quasi nul. Maintenant protégé par min_hold et seuil de score.
- **Smart cooldown encourageait le churn** : Un trade flat réduisait le cooldown (×0.5) au lieu de l'augmenter, provoquant des chaînes de micro-trades sans valeur.

### Technical
- 1203 tests backend (1163 existants + 40 nouveaux), tous passing ✅
- Frontend TypeScript clean (tsc --noEmit sans erreur) ✅
- Aucune régression, aucune donnée existante impactée

## [1.9.0] - 2026-04-09

### Added
- **PaperRun — Campagnes de validation** : Nouveau modèle `PaperRun` pour identifier et comparer des campagnes de trading.
  - `POST /learning/run/start` : Démarrer une campagne (snapshot config profil)
  - `POST /learning/run/{id}/end` : Terminer une campagne
  - `GET /learning/runs` : Lister les campagnes
  - `GET /learning/run/{id}/metrics` : Métriques complètes brut + net (coûts TradingCostModel)
  - `GET /learning/runs/compare` : Comparaison avant/après avec verdict automatique
  - Métriques par run : win rate, expectancy brut/net, profit factor brut/net, drawdown, par direction, par type de sortie, délais entre trades

- **Smart Cooldown — Cooldown intelligent contextuel** : Le cooldown n'est plus un entier fixe. Il s'adapte au contexte du dernier trade :
  - Réduit (×0.5) après sortie stale / scratch / trailing flat
  - Réduit (×0.7) si signal fort (score > 50)
  - Allongé (×1.5) après grosse perte ou SL
  - Borné entre `min_cooldown_minutes` et `max_cooldown_minutes`
  - Bornes absolues de sécurité (0.5 - 30 min)
  - Activé par défaut sur le profil scalping : `smart_cooldown_enabled=True, min=0.5, max=5.0`
  - `backend/app/services/smart_cooldown_service.py` : nouveau service

- **Cooldown Diagnostic** : Nouvelle section `cooldown` dans `GET /paper/diagnostic` :
  - Cooldown configuré actuel
  - Délai moyen / médian / min / max entre trades
  - Distribution des délais (< 2min, 2-5min, 5-15min, 15-60min, > 60min)
  - Ticks bloqués par cooldown + % du total
  - Signaux perdus pendant le cooldown (avaient un score exploitable)
  - Cooldown efficiency (ratio théorique vs réel)

- **Learning Layer — Apprentissage explicable** : Première couche d'apprentissage basée sur les données stockées en base.
  - **LearningSignal** : Échantillon d'apprentissage auto-enregistré à chaque fermeture de trade (features contextuelles + résultat)
  - **StrategyFeedback** : Ajustements de paramètres suggérés avec explicabilité, versioning, safety bounds
  - **Mode shadow** : Les suggestions ne sont PAS appliquées automatiquement (inspection + promotion manuelle)
  - **Safety bounds** : Bornes absolues sur chaque paramètre (buy_threshold, trailing, cooldown, etc.)
  - **Rollback** : Tout ajustement peut être annulé
  - Endpoints :
    - `GET /learning/stats` : Stats du dataset
    - `GET /learning/patterns` : Patterns gagnants/perdants identifiés
    - `POST /learning/analyze` : Analyse complète + suggestions
    - `GET /learning/suggestions` : Suggestions shadow
    - `POST /learning/promote/{id}` : Promouvoir une suggestion
    - `POST /learning/rollback/{id}` : Rollback
    - `GET /learning/versions` : Historique des versions
    - `GET /learning/signals` : Échantillons d'apprentissage récents

- **73 nouveaux tests** — `test_smart_cooldown.py` (smart cooldown, PaperRun, cooldown diagnostic, endpoints) + `test_learning.py` (record sample, dataset stats, patterns, suggestions, promote/rollback, safety bounds). Total : **1163 tests**.

### Changed
- **Profil scalping enrichi** : Ajout de `smart_cooldown_enabled=True`, `min_cooldown_minutes=0.5`, `max_cooldown_minutes=5.0`
- **DiagnosticResponse enrichi** : Nouvelle section `cooldown: CooldownDiagnostic`
- **_check_cooldown amélioré** : Utilise `SmartCooldownService` si `smart_cooldown_enabled` dans le profil
- **_close_position enrichi** : Enregistre automatiquement un `LearningSignal` à chaque fermeture de trade

### Technical
- Nouveaux modèles : `PaperRun`, `LearningSignal`, `StrategyFeedback`
- Nouveaux schémas : `paper_run.py`, `learning.py`, `CooldownDiagnostic`
- Nouveaux services : `smart_cooldown_service.py`, `paper_run_service.py`, `learning_service.py`
- Nouvelle route : `learning.py` (12 endpoints)
- Modèles exportés dans `models/__init__.py`

## [1.8.1] - 2026-04-09

### Added
- **ScalpingAuditService** — Service d'audit dédié au sous-système scalping. Analyse : métriques brut/net, distribution des sorties (trailing/stale/signal/momentum_fade), audit trailing stop (PnL, % near-zero), distribution scores (saturation), comparaison long/short, impact levier, durée des trades, recommandations actionables.
  - `backend/app/services/scalping_audit_service.py` : nouveau service
  - `GET /audit/scalping` : endpoint d'audit scalping dédié
- **Protection Reset UI** — Le bouton "Reset" est séparé en 2 :
  - "Reset perte jour" (safe) : remet le compteur de perte journalière à zéro, ne touche PAS aux trades
  - "Full Reset" (destructif) : nécessite de taper "RESET" en majuscules dans un prompt de confirmation
- **34 nouveaux tests** — `test_scalping_audit.py` couvrant : ScalpingAuditService (12 tests), recalibrage paramètres (9 tests), levier conservateur (4 tests), reversal amélioré (6 tests), endpoint (3 tests). Total : **1090 tests**.

### Changed
- **Scalping recalibré (v1.8.1)** — Optimisation des paramètres basée sur l'analyse de l'export réel (15 trades, PnL brut +4.87$, net -170$ après coûts) :
  - `trailing_stop_activation_pct` : 0.03% → **0.08%** (évite le bruit du marché, activation après ~$57 sur BTC $71k au lieu de $21)
  - `trailing_stop_pct` : 0.05% → **0.12%** (trail plus large, laisse respirer le trade ~$85 au lieu de $35)
  - `buy_threshold` : 10 → **20** (filtre les setups médiocres, évite la saturation de score)
  - `sell_threshold` : 8 → **15** (même logique pour les shorts)
  - `min_score` : 5 → **15** (rejette les trades à trop faible conviction)
  - `cooldown_minutes` : 1 → **2** (évite les réentrées instantanées dans le bruit)
  - `stale_exit_minutes` : 10 → **12** (les stale exits étaient nettes positives, on allonge)
  - `max_leverage` : 2.0 → **1.5** (réduction du risque tant que l'edge net n'est pas prouvé)
- **Levier scalping conservateur** — En mode scalping (max_leverage ≤ 1.5), le levier est forcé à x1.0 sauf si confidence=HIGH ET score_factor ≥ 0.7. Empêche l'amplification des pertes sur un edge faible.
- **Reversal check amélioré** — La détection de mean reversion pour le short scalping utilise désormais :
  - Les règles RSI/StochRSI satisfaites (comme avant)
  - Le score technique extrême (≥90 → overbought, ≤-90 → oversold)
  - Cela devrait activer plus de trades short en runtime

### Fixed
- **Reset button data loss** — Le bouton Reset ne supprime plus accidentellement toutes les données. Double protection : boutons séparés + confirmation typed "RESET" pour le full reset.

### Technical
- `backend/app/services/scalping_audit_service.py` : nouveau service (420 lignes)
- `backend/app/api/routes/audit.py` : ajout `GET /audit/scalping`
- `backend/app/services/trading_profile_service.py` : recalibrage preset scalping
- `backend/app/services/leverage_service.py` : règle conservative scalping
- `backend/app/services/paper_trading_service.py` : reversal check amélioré
- `frontend/src/components/PaperTradingPanel.tsx` : protection reset (2 boutons)
- `backend/tests/test_scalping_audit.py` : 34 nouveaux tests
- `backend/tests/test_diagnostic.py` : mise à jour assertions scalping

## [1.8.0] - 2026-04-08

### Added
- **TradingCostModel** — Modèle de coûts de trading avec 3 presets (optimistic, realistic, stressed). Paramètres : maker fee, taker fee, spread, slippage. Calcule les métriques brut/net (PnL, expectancy, profit factor, win rate).
  - `trading_cost_service.py` : dataclass `TradingCostModel` avec `apply_to_pnl()`, `apply_to_trades()`, presets `COST_OPTIMISTIC`, `COST_REALISTIC`, `COST_STRESSED`
  - `schemas/trading_cost.py` : `CostPresetType`, `TradingCostConfig`, `TradingCostImpact`, `CostAuditMetrics`
- **TruthAuditService** — Service d'audit de vérité des métriques de paper trading. Couvre : expectancy brute/nette, drawdown vérifié, performance par slot, performance par profil, impact trailing stop, impact levier, verdict global (DANGEROUS/FRAGILE/VIABLE/SOLID).
- **V2GateService** — Gate formelle de passage vers v2.0 avec 8 critères objectifs : nombre de trades ≥50, expectancy nette >0, drawdown <15%, win rate >40%, profit factor >1.0, audit verdict ≥VIABLE, documentation à jour, kill switch fonctionnel. Retourne READY/PARTIAL/NOT_READY.
- **Endpoints d'audit** — `GET /audit/truth` (audit complet), `GET /audit/costs` (presets disponibles), `GET /v2/readiness` (gate v2.0)
- **48 nouveaux tests** — `test_reality_gap.py` couvrant TradingCostModel (23 tests), TruthAuditService (15 tests), V2GateService (4 tests), endpoints API (6 tests). Total : **1053 tests**.

### Changed
- **Documentation honnête** — Réécriture complète de `CURRENT_STATE.md` pour refléter l'état réel du projet avec ses limites structurelles (pas de frais, pas de campagnes, pas d'audit). Le problème "backtest sans frais" reclassé de ⚠️ Low à 🔴 CRITIQUE.
- **ROADMAP nettoyée** — Suppression des sections 1-9 obsolètes (décrivaient l'état v0.6 avec "Dashboard corrupted" et "4 tests failing"). Ajout de la phase v1.8 Reality Gap Closure. Les diagnostics de maturité archivés.
- **RTM v1.8.0** — Version mise à jour, ajout FR-MSL-005 (trailing stop), FR-CST-001, FR-RUN-001, FR-AUD-001, FR-GATE-001 (planned).

### Technical
- `backend/app/services/trading_cost_service.py` : nouveau service
- `backend/app/services/truth_audit_service.py` : nouveau service
- `backend/app/services/v2_gate_service.py` : nouveau service
- `backend/app/schemas/trading_cost.py` : nouveaux schémas
- `backend/app/api/routes/audit.py` : nouvelles routes
- `backend/app/api/routes/__init__.py` : ajout `audit_router`
- `backend/app/main.py` : include `audit_router`
- `backend/app/schemas/__init__.py` : exports trading_cost
- `backend/tests/test_reality_gap.py` : 48 tests

## [1.7.2] - 2026-04-08

### Added
- **Trailing stop scalping** — Nouveau mécanisme de protection des profits pour le scalping. Dès que le PnL latent atteint +0.03%, un trailing stop s'active et ferme la position si le PnL recule de 0.05% depuis le pic. Plus réactif que le momentum fade (qui attendait un recul de 60%).
  - Nouveaux paramètres profil : `trailing_stop_pct`, `trailing_stop_activation_pct`
  - Nouveau statut de fermeture : `closed_trailing_stop` (affiché `🎯 Trail` dans l'UI)
  - Configurable par profil (actuellement activé uniquement sur scalping)

### Changed
- **Auto-refresh panels après trade** — Le Journal d'évaluation, le Diagnostic de fréquence et les Opportunités manquées se rafraîchissent automatiquement après chaque trade exécuté (ouverture ou fermeture), sans avoir à cliquer sur "Rafraîchir".
  - `usePaperTrading` expose un compteur `tradeVersion` incrémenté à chaque trade
  - `PaperTradingPanel` accepte un callback `onTradeExecuted`
  - `JournalPanel` et `DiagnosticPanel` acceptent un `refreshTrigger` prop

### Fixed
- **Bug filtre "Aujourd'hui" du Journal** — Quand on cliquait sur "Aujourd'hui" alors que le filtre était déjà sur "Aujourd'hui", les données ne se rechargeaient pas. Corrigé via un compteur `fetchCounter` qui force le re-fetch même si les dates sont identiques.

### Technical
- `usePaperTrading.ts` : ajout `tradeVersion`, détection `isTradeAction()` dans `doAutoTick`, `manualTick`, `closePosition`
- `PaperTradingPanel.tsx` : prop `onTradeExecuted`, `useEffect` sur `tradeVersion`
- `JournalPanel.tsx` : prop `refreshTrigger`, `fetchCounter` state, `handlePreset` incrémente le compteur
- `DiagnosticPanel.tsx` : prop `refreshTrigger`, `useEffect` auto-refresh
- `Dashboard.tsx` : état `tradeVersion`, callbacks entre composants
- `journal.py` : champs `trailing_stop_pct` et `trailing_stop_activation_pct` dans `TradingProfileParams`
- `trading_profile_service.py` : preset scalping configuré avec trailing stop (0.03% activation, 0.05% trail)
- `paper_trading_service.py` : logique trailing stop insérée avant momentum fade
- 1005 tests backend, tous passing ✅
- tsc --noEmit sans erreur ✅

## [1.7.1] - 2026-04-08

### Fixed
- **Per-slot cooldown** — Chaque slot a maintenant ses propres timers de cooldown indépendants (avant : cooldown global partagé entre tous les slots). Le slot scalping peut réentrer après 1 min même si le slot balanced vient de trader.
- **Per-slot daily trade counter** — Chaque slot a son propre compteur de trades journalier (avant : compteur global partagé). Le scalping peut faire 50 trades/jour sans bloquer le slot balanced.
- **Startup emoji crash on Windows** — Les `print()` de démarrage utilisaient des emojis Unicode (🚀, ✅) qui causaient un `UnicodeEncodeError` sur les consoles Windows CP1252. Remplacés par du texte ASCII.
- **Reset tick log** — Tentative de purger `tick_activity_log` au reset annulée : le diagnostic filtre déjà par `account_id`, pas besoin de purger.

### Technical
- `_check_cooldown()` : accepte paramètre optionnel `slot`, filtre par slot en mode multi
- `_check_max_trades_per_day()` : même correction slot-aware
- `main.py` : emojis remplacés par `[START]`, `[DB]`, `[OK]`, `[STOP]`
- Migration `migrate_v17.py` incluse pour colonnes PostgreSQL
- 1005 tests backend, tous passing ✅
- tsc --noEmit sans erreur ✅

## [1.7.0] - 2026-04-08

### Added
- **Multi-slot : positions parallèles** — Le bot peut maintenant gérer **plusieurs positions simultanément** (max 3 par défaut). Chaque "slot" est un profil avec ses propres paramètres (SL/TP, durée, levier).
  - En mode "Auto" : slot "balanced" (tendance 1-4h) + slot "scalping" (haute fréquence 15m) en parallèle
  - En mode "Scalping" : slot "scalping" + slot "aggressive" en parallèle
  - Allocation de capital par slot (division égale)
  - Chaque position affichée dans l'UI avec son badge de slot
- **Modèle `PaperTrade.slot`** — Nouvelle colonne pour identifier le slot d'une position
- **Modèle `PaperAccount.max_open_positions`** — Configurable (1=mono rétrocompat, >1=multi)
- **`PaperStatus.open_positions`** — Liste de toutes les positions ouvertes
- **`SlotTickResult`** — Résultat par slot dans le tick multi-slot
- **Scalping mean reversion bidirectionnel** — Le bot peut ouvrir des SHORT en tendance haussière quand les oscillateurs (RSI, StochRSI) montrent un surachat, et des LONG en tendance baissière quand survente
- **SL/TP defaults direction-aware** — Bug fix critique : les shorts recevaient des SL/TP de longs

### Changed
- `tick()` refactorisé en orchestrateur multi-slot + `_tick_single_slot()` par slot
- UI `PaperTradingPanel` : affiche toutes les positions ouvertes avec badges de slot
- `handleLaunchRobot` active automatiquement `max_open_positions=3` au lancement

### Technical
- `paper_account.py` — `max_open_positions`, `PaperTrade.slot`
- `paper_trading_service.py` — `get_open_positions()`, `get_open_position_for_slot()`, `get_enabled_slots()`, `_capital_for_slot()`, `_scalping_reversal_check()`
- `paper_trading.py` (schemas) — `SlotTickResult`, champs multi-slot
- Rétrocompatibilité totale : `max_open_positions=1` = comportement identique, 1005 tests passent

## [1.6.2] - 2026-04-08

### Fixed
- **Position blocking en scalping (95%)** — Les positions restaient ouvertes des heures au lieu de minutes. Trois correctifs combinés :
  1. **Stale exit 10 min** (était 60 min) — Si SL/TP n'est pas touché en 10 min, la position est fermée et le bot réessaie
  2. **Seuil stale adapté au profil** — Pour les profils tight (scalping), le seuil de stagnation est élargi à `profit_take_pct` (0.3%) au lieu de 0.1% fixe, sinon les positions à -0.15% n'étaient jamais considérées stagnantes
  3. **Cooldown 1 min** (était 3 min) — Réentrée quasi immédiate après fermeture
- **Auto-close sur changement de profil** — Quand on passe d'un profil à un autre (ex: conservative → scalping), les positions ouvertes sous l'ancien profil sont fermées automatiquement. Cela évite le blocage par des vieilles positions incompatibles.
- **Scalping uniquement LONG (jamais de SHORT)** — Le moteur de décision retourne toujours "acheter" en tendance haussière. Ajout du mode **mean reversion bidirectionnel** : quand les oscillateurs (RSI, StochRSI) montrent un surachat, le bot ouvre un SHORT pour capter le pullback, même en tendance haussière. Et inversement, des LONG en survente dans une tendance baissière.
- **SL/TP defaults pour SHORT incorrects** — Les fallbacks SL/TP étaient codés en dur pour LONG (`price * 0.95` / `price * 1.10`). Les positions SHORT recevaient un SL en dessous de l'entrée (au lieu d'au-dessus). Corrigé avec des defaults direction-aware.

### Technical
- `trading_profile_service.py` — Preset scalping : `stale_exit_minutes=10`, `cooldown_minutes=1`, auto-close dans `set_profile()`
- `paper_trading_service.py` — Mean reversion via `_scalping_reversal_check()`, SL/TP direction-aware, stale exit profile-aware
- Tests mis à jour (1005 tests, tous passing)

## [1.6.1] - 2026-04-08

### Fixed
- **Scalping : SL/TP trop larges** — Les positions scalping utilisaient les SL/TP du risk engine global (5% SL / 10% TP), beaucoup trop larges pour du scalping (0.3%). Maintenant, quand le profil a `loss_cut_pct ≤ 0.5%`, les SL/TP sont recalculés à partir des % du profil et les valeurs les plus serrées sont utilisées.
- **Loss cut conditionnel au score** — Le loss cut exigeait `PnL < -lc_pct ET score < lc_score`, ce qui retardait la coupe en scalping. Pour les profils tight (`loss_cut_pct ≤ 0.5%`), le loss cut est désormais **inconditionnel** dès que le seuil de perte est atteint.
- **Expiration utilisait le compte (168h) au lieu du profil (2h)** — `_check_expiration` utilisait uniquement `account.max_open_duration_hours` (168h). Il utilise désormais `min(account, profil)`, donc le scalping expire à 2h.
- **Direction SL/TP pour shorts** — Les SL/TP pour shorts sont correctement inversés (SL au-dessus, TP en dessous) dans le recalcul profil.

### Changed
- Auto-tick frontend : ajout intervalle 5s pour scalping rapide
- Intervalle auto-tick par défaut : 10s (était 60s)
- Le message de détail à l'ouverture affiche les SL/TP réellement utilisés (et non ceux du risk engine)
- **PaperTradingPanel refactorisé** — Bouton unique "🤖 Lancer le Robot" : sélection profil + activation + auto-tick en un clic
- Sélecteur de profil intégré directement dans le panel (🛡️ Prudent / ⚖️ Équilibré / 🔥 Agressif / ⚡ Scalping / 🤖 Auto)
- Intervalle auto-tick automatiquement adapté au profil (5s scalping, 10s auto, 30s agressif, 60s équilibré, 300s prudent)
- Affichage du profil actif dans le header et badge de statut robot
- Nouveaux status badges : 💤 Stagnant, 📉 Fade

### Technical
- `paper_trading_service.py` — Logique SL/TP profile-aware, loss cut inconditionnel, expiration profile-aware
- `PaperTradingPanel.tsx` — Intervalle 5s ajouté, défaut 10s

## [1.6.0] - 2026-04-08

### Added
- **Diagnostic de fréquence** — Analyse exhaustive de pourquoi le bot trade peu
  - Nouveau endpoint `GET /paper/diagnostic` avec hiérarchie des causes de non-trade
  - Classement des raisons : signal (decision_wait, score_too_low) vs risque vs structure
  - Analyse de la durée des positions (moy, médiane, distribution < 1h / 1-4h / 4-24h / > 24h)
  - Comparaison simulée des 4 profils sur les données réelles
  - Analyse du risk engine comme frein (kill switch, daily loss, levier réduit)
  - Identification automatique du goulot d'étranglement principal + recommandations
- **Opportunités manquées** — Détection ex-post des mouvements ratés
  - Nouveau endpoint `GET /paper/missed-opportunities`
  - Analyse des ticks non-trade : mouvement favorable dans les N minutes suivantes
  - Ventilation par seuil (≥ 0.1%, ≥ 0.2%, ≥ 0.3%, ≥ 0.5%)
  - Avertissement clair : ces chiffres sont ex-post et surestiment les gains réels
- **Analyse levier** — Comparaison avec/sans levier
  - Nouveau endpoint `GET /paper/leverage-analysis`
  - PnL avec levier vs PnL sans levier, bénéfice net, amplification pos/neg
- **Profil Scalping** — Haute fréquence intraday
  - Nouveau profil "scalping" : min_score=5, cooldown=3min, max_trades=50/j
  - Timeframe d'analyse 15m (au lieu de 4h) pour capter les micro-mouvements
  - Seuils de décision abaissés : BUY > +10, SELL < -8 (vs +25 / -20)
  - Sorties serrées : profit_take 0.3%, loss_cut 0.3%
  - Momentum fade : sortie si le profit latent recule de >60% depuis le pic
  - Stale exit : sortie si position stagnante depuis >60 min (PnL < 0.1%)
- **Seuils de décision personnalisables** par profil
  - `buy_threshold` et `sell_threshold` optionnels dans TradingProfileParams
  - DecisionService.analyze() et generate_recommendation() acceptent ces seuils
  - Rétrocompatible : None = seuils globaux (BUY_THRESHOLD=25, SELL_THRESHOLD=20)
- **Timeframe d'analyse par profil**
  - `analysis_timeframe` optionnel dans TradingProfileParams
  - Le paper trading utilise le timeframe du profil (scalping→15m, autres→4h)
- **Sorties rapides**
  - Momentum fade : détecte quand le profit s'essouffle et ferme avant inversion
  - Stale position : ferme les positions improductives après N minutes
  - Configurable par profil via `momentum_fade_enabled` et `stale_exit_minutes`
  - Aggressive a stale_exit_minutes=180 (3h)
- **Auto-profil amélioré** — Score ≥ 10 → scalping (nouveau tier)
- **DiagnosticPanel** — Nouveau composant frontend
  - Top raisons de non-trade avec barres visuelles
  - Comparaison des profils en table
  - Durée des positions avec alertes
  - Opportunités manquées (KPIs + seuils)
  - Analyse levier (bénéfice net, amplification)
  - Recommandations automatiques
  - Intégré dans l'onglet Trading du Dashboard
- **55 nouveaux tests backend** couvrant diagnostic, scalping, seuils, sorties rapides, endpoints

### Changed
- Auto-profil : score ≥ 10 → scalping (avant : → conservative)
- Aggressive : ajout stale_exit_minutes=180
- DecisionService : seuils BUY/SELL paramétrables (rétrocompatible)

### Technical
- Nouveau fichier `diagnostic_service.py` — DiagnosticService complet
- Nouveau fichier `schemas/diagnostic.py` — 6 schémas Pydantic
- TradingProfileType enum : ajout `scalping`
- TradingProfileParams : 5 nouveaux champs optionnels (rétrocompatible)
- paper_trading_service.py : timeframe dynamique, sorties rapides (stale + momentum fade)
- 3 nouveaux endpoints : `/paper/diagnostic`, `/paper/missed-opportunities`, `/paper/leverage-analysis`
- Frontend : DiagnosticPanel.tsx + types + API client
- **1005 tests backend**, tous passing ✅
- tsc --noEmit sans erreur ✅

## [1.5.1] - 2026-04-08

### Added
- **Mode Auto-Profil** — Sélection dynamique du profil par le moteur à chaque tick
  - Nouveau choix "🤖 Auto" dans le sélecteur de profil (bouton violet)
  - Le système choisit automatiquement Conservative/Balanced/Aggressive en fonction du signal :
    - Score ≥ 50 + confiance "high" → Aggressive (opportunité forte)
    - Score ≥ 30 + confiance ≥ "medium" → Balanced (opportunité correcte)
    - Sinon → Conservative (prudence par défaut)
  - Le profil résolu est tracé dans le tick : `profile_type = "auto→aggressive"`
  - Le levier et les seuils (min_score, cooldown, max_trades/jour) s'ajustent dynamiquement
  - 17 nouveaux tests backend (boundaries, DB, endpoints, sélection automatique)

### Technical
- `TradingProfileType` enum : ajout valeur `auto`
- `TradingProfileService.auto_select_profile()` : méthode statique de résolution
- `TradingProfileService.is_auto_mode()` : détecte le mode auto
- `PaperTradingService.tick()` : résolution auto du profil après obtention de la decision
- Frontend : bouton "🤖 Auto" violet + texte explicatif adaptatif
- 949 tests backend, tous passing ✅
- tsc --noEmit sans erreur ✅

## [1.5.0] - 2026-04-08

### Added
- **Paper Trading Evaluation Journal** — Journal d'évaluation multi-jours
  - Filtres par plage de dates avec presets (aujourd'hui, 7j, 14j, 30j, tout)
  - Vue synthétique : PnL, win rate, expectancy, profit factor, Sharpe, drawdown, verdict
  - Vue journalière : résumé par jour (trades, PnL, meilleur/pire trade, verdict)
  - Vue activité : fréquence des ticks, ratio tick→trade, répartition visuelle
  - Raisons de non-trade : agrégation + labels humains en français + barres visuelles
- **Profils de Trading** — Conservative / Balanced / Aggressive
  - Conservative : baseline existante, très sélectif, levier OFF
  - Balanced : seuils plus souples, cooldown réduit, levier auto x2 max
  - Aggressive : plus de trades, levier auto x3 max, borné par risk engine
  - Sélection de profil depuis l'UI avec paramètres affichés
- **Levier Automatique Intelligent** — Décidé par le moteur, pas l'utilisateur
  - Formule : score_factor × confiance_factor × volatilité_factor × max_leverage
  - Veto risk engine : blocked/danger → x1, caution → cap 50%, marge daily loss → réduction
  - Journalisation complète : levier recommandé, final, raisons, facteurs
- **Qualification du Style de Trading**
  - Distribution des durées (<1min, 1-5min, 5-15min, 15-60min, 1h+)
  - Qualification : scalping-like / intraday / swing_intraday
  - Statistiques : durée moyenne/médiane, exits rapides/lents
- **Modèle TickActivityLog** — Persistance de chaque tick (y compris non-trades)
  - Journalise : action, score, confiance, raison de non-trade, levier, profil
  - Table additive, rétrocompatible
- **Frontend JournalPanel** — Intégré dans l'onglet Trading
  - 5 sous-vues : Synthèse, Journalier, Activité, Non-trade, Style
  - Sélecteur de profil avec ToggleButtons
  - KPIs visuels, tables, barres de distribution
- **64 nouveaux tests** couvrant journal, profils, levier, style, endpoints, schémas

### Changed
- `paper_trading_service.py` : intégration profils, levier auto, journalisation tick
- `paper_account.py` : ajout colonne `active_profile` (default "conservative")
- `test_paper_trading.py` : score short ajusté -30→-45 pour compatibilité profil

### Technical
- Backend : `journal_service.py`, `trading_profile_service.py`, `leverage_service.py`
- Schemas : `journal.py` (TradingProfileParams, JournalResponse, LeverageRecommendation, etc.)
- Models : `tick_activity_log.py` (TickActivityLog)
- Routes : `/paper/journal`, `/paper/style`, `/paper/profile`, `/paper/profile/presets`
- Frontend : `JournalPanel.tsx`, types API étendus, marketApi étendu
- 930 tests backend (avant : 866), tous passing ✅
- `tsc --noEmit` sans erreur ✅

## [1.4.1] - 2026-04-07

### Added
- **Support complet des positions SHORT** dans le paper trading
  - Seuil SELL abaissé de -25 à -20 (asymétrique BUY=+25 / SELL=-20 pour compenser le biais haussier Bitcoin)
  - Nouveau chemin SELL par confluence : ≥3 règles bearish satisfaites + score négatif → ouvre un short
  - Constantes exportées : `BUY_THRESHOLD`, `SELL_THRESHOLD`, `SELL_CONFLUENCE_MIN`
  - Tracking `lowest_price_since_entry` pour les positions short (trailing stop symétrique)
  - Initialisation correcte des prix extrêmes : `highest_price_since_entry` (long) / `lowest_price_since_entry` (short)
  - 10 nouveaux tests : ouverture short, fermeture short par signal, tracking prix short, profit short, confluence SELL

### Changed
- **Seuils de fermeture signal-based moins agressifs** :
  - Long : ferme si score ≤ 0 (avant : ≤ 10) — ne ferme plus une position sur un signal faiblement haussier
  - Short : ferme si score ≥ 0 (avant : ≥ -10) — symétrique
  - Suppression des conditions redondantes "score devenu positif/négatif"

### Technical
- `decision_service.py` : constantes `BUY_THRESHOLD=25`, `SELL_THRESHOLD=20`, `SELL_CONFLUENCE_MIN=3`
- `paper_account.py` : ajout colonne `lowest_price_since_entry` (nullable Float)
- `paper_trading_service.py` : tracking bidirectionnel + seuils de fermeture ajustés
- `paper_trading.py` (schema) : ajout `lowest_price_since_entry` dans `PaperTradeResponse`
- `api.ts` (frontend) : ajout `lowest_price_since_entry` dans `PaperTradeItem`
- Migration PostgreSQL : `ALTER TABLE paper_trade ADD COLUMN IF NOT EXISTS lowest_price_since_entry FLOAT`
- 851 tests backend (avant : 841), tous passing ✅

## [1.4.0] - 2026-04-07

### Added
- **Paper Trading System (v1.4)** : Simulation de trading en temps réel
  - **Modèle `PaperAccount`** : Compte paper singleton (capital, PnL cumulé, win rate, drawdown, peak capital)
  - **Modèle `PaperTrade`** : Journal de trades (entry/exit prix, SL/TP, PnL, durée, direction long/short)
  - **Service `PaperTradingService`** : Moteur de paper trading complet
    - Tick engine : à chaque tick, interroge DecisionService + RiskService
    - Ouverture/fermeture automatique de positions
    - Vérification SL/TP/expiration à chaque tick
    - Signal contraire : ferme la position si score < -20
    - Trailing stop : mise à jour du highest_price_since_entry
    - Métriques : win rate, Sharpe ratio, max drawdown, profit factor, buy & hold
    - Buy & hold comparison : calcul PnL si on avait simplement acheté du BTC
  - **8 endpoints API** :
    - `GET /paper/account` — État du compte (crée par défaut si absent)
    - `POST /paper/account` — Créer/activer le compte paper
    - `POST /paper/account/reset` — Reset complet (supprime trades, remet capital)
    - `GET /paper/status` — Statut complet (compte + position + métriques + prix BTC)
    - `POST /paper/tick` — Exécuter un tick manuellement (debug/test)
    - `GET /paper/trades` — Journal des trades (filtres: status, pagination)
    - `GET /paper/metrics` — Métriques de performance + buy & hold
    - `POST /paper/close` — Fermeture manuelle de la position ouverte
  - **Scheduler intégré** : Job APScheduler toutes les 5 minutes (configurable via `SCHEDULER_INTERVAL_PAPER_MINUTES`)
- **PaperTradingPanel frontend** : Dashboard complet de paper trading
  - Grille de métriques : capital, PnL, win rate, Sharpe, drawdown, profit factor, buy & hold
  - Position ouverte : direction, prix entrée/SL/TP, PnL latent
  - Contrôles : Activer, Reset, Tick manuel, Fermer position, Actualiser
  - Journal des trades : table avec status, direction, PnL, durée, raisons
  - Dernière action : alerte contextuelle du dernier tick
- **Hook `usePaperTrading`** : Gestion d'état React (status, trades, tick, activate, reset, close)
- **Types TypeScript** : `PaperTradeItem`, `PaperAccountItem`, `PaperMetrics`, `PaperStatus`, `PaperTickResult`, `PaperTradeListResponse`
- **7 fonctions API client** : `getPaperAccount`, `createPaperAccount`, `resetPaperAccount`, `getPaperStatus`, `paperTick`, `getPaperTrades`, `getPaperMetrics`, `closePaperPosition`
- **64 tests backend** pour le paper trading (modèles, service, SL/TP, métriques, tick engine, endpoints)

### Technical
- 841 tests backend, tous passing ✅
- `tsc --noEmit` sans erreur ✅
- Nouveau modèle SQLAlchemy `PaperAccount` + `PaperTrade` (2 tables)
- Nouveau router FastAPI `/paper/*` avec 8 endpoints
- Configuration : `SCHEDULER_INTERVAL_PAPER_MINUTES` (défaut: 5)

## [1.3.0] - 2026-04-06

### Added
- **Risk Management Engine (v1.3)** : Système complet de gestion du risque
  - **Modèle `RiskConfig`** : Table SQLAlchemy singleton avec stop-loss, take-profit, position sizing, daily loss, kill switch
  - **Service `RiskService`** : Logique métier complète (évaluation trades, calcul SL/TP, suivi perte journalière, kill switch)
  - **3 types de stop-loss** : Fixe (%), Trailing (suiveur), ATR (basé sur la volatilité)
  - **Position sizing** : % max du portefeuille par position, ajustement automatique selon le risque restant
  - **Perte journalière** : Compteur avec reset automatique à minuit, déclenchement kill switch si limite atteinte
  - **Kill switch** : Arrêt d'urgence (activation/désactivation manuelle ou automatique), bloque tous les trades
  - **Ratio risque/récompense** : Calculé pour chaque trade, warning si < 1.0
  - **7 endpoints API** : GET/POST/PUT `/risk/config`, GET `/risk/status`, POST `/risk/evaluate`, POST `/risk/kill-switch/activate`, POST `/risk/kill-switch/deactivate`, POST `/risk/record-loss`
- **RiskPanel frontend** : Composant complet de gestion du risque
  - Jauge de perte journalière avec barre de progression colorée
  - Bouton Kill Switch avec animation pulse quand actif
  - Indicateurs rapides (SL, TP, Position max)
  - Formulaire de configuration éditable (type SL, %, portefeuille)
  - État en temps réel (safe/caution/danger/blocked)
- **Hook `useRisk`** : Gestion d'état React (config, status, updateConfig, toggleKillSwitch)
- **Types TypeScript** : `RiskConfigItem`, `RiskConfigCreate`, `RiskEvaluation`, `RiskStatus`, `RecordLossResponse`, `StopLossType`, `RiskLevel`
- **55 tests backend** pour le risk engine (config CRUD, évaluation trades, ATR, daily loss, kill switch, endpoints, edge cases)
- **Dashboard intégration** : RiskPanel ajouté dans la zone "Analyse du marché" en grille 3 colonnes

### Technical
- 777 tests backend, tous passing ✅
- `tsc --noEmit` sans erreur ✅
- Nouveau modèle SQLAlchemy `RiskConfig` avec 15 colonnes
- Nouveau router FastAPI `/risk/*` avec 7 endpoints

## [1.2.5] - 2026-04-06

### Added
- **Scanner de dates intéressantes** : Nouveau endpoint `GET /backtest/interesting-dates` qui scanne l'historique et identifie les dates avec des signaux techniques forts (RSI extrêmes, croisements MACD marqués, prix hors Bollinger, etc.)
  - Approche performante : calcul en une passe DataFrame sur tout l'historique
  - Score d'intérêt 0-100 basé sur la force et le nombre de signaux
  - Label court (ex: "RSI survendu + MACD ↑") et direction dominante
  - Paramètres configurables : `min_strength`, `max_results`, `step_days`
- **Chips cliquables dans la vérification** : Les dates intéressantes s'affichent comme des chips colorés (bullish ↑ vert, bearish ↓ rouge) avec tooltips détaillés. Clic → auto-remplissage de la date.
- **Walk-forward fractionnaire** : Le pas (`step_days`) est maintenant un float, permettant des pas de 0.25j (6h) en mode Scalping, 0.04j (1h) en mode Intraday
  - Le pas par défaut s'adapte automatiquement au mode (Scalping: 0.25, Intraday: 1, Swing: 30)
- **Guides visuels d'aide utilisateur** : 3 encadrés d'aide ajoutés aux sections 1, 2 et 3 du panneau de vérification
  - Section 1 : explication des modes (Scalping/Intraday/Swing) et des horizons
  - Section 2 : principe du time-travel, utilisation des dates intéressantes, conseils qualité
  - Section 3 : explication du walk-forward, valeurs de pas, mode comparaison, durée estimée
- **Légendes des métriques** : Deux légendes explicatives ajoutées (après les résultats de vérification et après le walk-forward)
  - Explication de Q (qualité), DIR (directionnel), HC (high confidence), 💰 (profitabilité)
- **10 tests backend** pour le scanner de dates intéressantes (service + endpoint)
- **Schémas Pydantic** : `InterestingSignalDetail`, `InterestingDateItem`, `InterestingDatesResponse`
- **Types TypeScript** : 3 interfaces correspondantes + barrel export

### Changed
- `WalkForwardConfig.step_days` : `int` → `float` (ge=0.01) pour supporter les pas fractionnaires
- `WalkForwardResult.step_days` : `int` → `float` pour cohérence
- Frontend : minimum du pas adapté au mode (0.01 en scalping, 0.04 en intraday, 1 en swing)
- Meilleur message d'erreur "aucune donnée" avec plage de dates en gras
- État vide redessiné avec icône et étapes numérotées

### Technical
- Tests : 681 → 722, all passing
- TypeScript : tsc --noEmit sans erreur
- Nouveau endpoint : `GET /backtest/interesting-dates`
- Nouveau service : `VerificationService.find_interesting_dates()`
- Nouveau API client : `getInterestingDates()`

## [1.2.4] - 2026-04-06

### Added
- **Sentiment historique combiné dans le walk-forward** : Le moteur de décision utilise maintenant DEUX sources de sentiment en mode historique (backtest/vérification)
  - **Fear & Greed Index** (60%) : indice agrégé du marché, disponible depuis février 2018
  - **News History** (40%) : articles individuels (RSS + CryptoCompare) stockés en base
  - Si une seule source est disponible → utilisée à 100% (fallback gracieux)
  - Si aucune source → mode dégradé 100% technique (comportement inchangé)
  - Gestion des erreurs : si une source lève une exception, l'autre est utilisée seule
- **Champ `sentiment_source` dans DecisionMeta** : Traçabilité de la source sentiment utilisée
  - `"fear_and_greed+news_history"` : les deux sources combinées
  - `"fear_and_greed_historical"` : FGI seul
  - `"news_history"` : articles seuls
  - `"live_rss"` : mode temps réel
  - `"none"` : aucune source disponible
- **Patch dual dans `_verify_technical_only`** : Le mode compare_mode neutralise maintenant les DEUX services sentiment (FGI + News History) pour isoler la technique pure
- **15 tests sentiment combiné** (`test_decision.py`) : combinaison, fallbacks, erreurs, bornes, proportionnalité, méta
- **5 tests dual patch** (`test_verification.py`) : patch FGI, patch News, restauration, exception, compare_mode

### Changed
- `DecisionService._get_historical_sentiment()` : Réécrit pour combiner FGI + News History avec pondération configurable
- `DecisionService.__init__()` : Injecte maintenant `NewsHistoryService` en plus de `SentimentHistoryService`
- `VerificationService._verify_technical_only()` : Patche les deux services sentiment au lieu d'un seul
- Docstring de `verification_service.py` : Mise à jour (suppression note "sentiment non disponible")

### Technical
- Constantes `FNG_HIST_WEIGHT = 0.60` et `NEWS_HIST_WEIGHT = 0.40` dans decision_service.py
- Tests backend : 661 → **681 tests** (tous passing)
- Frontend tsc --noEmit sans erreur

## [1.2.3b] - 2026-04-05

### Fixed
- **VerificationPanel timeframe switch** : Corrigé la race condition qui faisait tourner les barres de chargement indéfiniment lors du switch entre 4h et 1d
  - Les résultats stales (vérification, walk-forward, chargement) sont maintenant nettoyés lors du changement de timeframe
  - Anti-race via `requestIdRef` : les réponses API obsolètes sont ignorées si le timeframe a changé entre-temps
  - Le `useEffect` ne dépend plus de callbacks instables (boucle d'effets éliminée)
  - Le sentiment range est chargé une seule fois au mount (indépendant du timeframe)
- **Scheduler News job mock** : Corrigé le test `test_job_success_updates_state` qui échouait car `persist_cryptocompare_recent()` n'était pas mocké (le job appelle maintenant RSS + CryptoCompare)

### Added
- **Scheduler News RSS automatique** : Nouveau job `fetch_news_job` qui persiste automatiquement les news RSS en base toutes les 10 minutes
  - Nouveau champ config `SCHEDULER_INTERVAL_NEWS_MINUTES` (défaut : 10 minutes)
  - Le job appelle `NewsHistoryService.persist_current_news()` + `persist_cryptocompare_recent()` (dédoublonnage par URL)
  - Toujours activé quand `SCHEDULER_ENABLED=true` (indépendant du mode dual/legacy candles)
  - Status exposé dans `GET /scheduler/status` sous `jobs.news`
  - Trigger manuel via `POST /scheduler/trigger/news`
  - **11 tests** (`test_scheduler_news.py`) : config, state, exécution success/error, registration dans start_scheduler
- **CryptoCompare Service** : Client API CryptoCompare News (free tier, historique depuis 2015)
  - `CryptoCompareService` : fetch de pages paginées, parsing en `NewsItem`, gestion clé API optionnelle
  - Intégration avec `NewsHistoryService` : `load_cryptocompare_history()` (chargement profond avec delta loading) + `persist_cryptocompare_recent()` (enrichissement continu)
  - Endpoint `POST /news/history/load-cryptocompare` : chargement historique avec `start_year` et `max_pages` configurables
  - **30 nouveaux tests** (`test_cryptocompare.py`) :
    - Parsing (7) : article valide, sans titre/URL, description tronquée, body vide, source manquante, timestamp invalide
    - Fetch page (5) : succès, page vide, erreur HTTP, paramètre lTs, clé API
    - Multi-pages (3) : page unique, pagination, arrêt page vide
    - Load history (5) : insertion, idempotence, arrêt start_year, arrêt fin pagination, delta mode
    - Persist recent (3) : succès, dédoublonnage, vide
    - Config (4) : défaut, clé API, pas d'auth sans clé, timeout custom
    - Endpoint (3) : succès, paramètres, structure réponse

### Technical
- Tests backend : 631 → **661 tests** (tous passing)
- Frontend tsc --noEmit sans erreur

## [1.2.3a] - 2026-04-05

### Added
- **Modèle NewsHistory** : Nouvelle table `news_history` pour stocker les articles de news crypto en base de données
  - Colonnes : title, url, source, description, published_at, sentiment, impact, sentiment_score, keywords
  - Index unique sur URL pour dédoublonnage idempotent
  - Index sur (source, published_at) pour les requêtes par date
- **Service NewsHistoryService** : Persistance et requête des news historiques
  - `persist_current_news()` : Collecte les news RSS et les stocke en base (dédoublonnage par URL)
  - `get_daily_sentiment()` : Score de sentiment agrégé par jour (-100/+100), pondéré par impact
  - `get_articles_at_date()` : Récupère les articles autour d'une date
  - `get_range()` / `get_coverage()` : Métriques sur le corpus en base
  - Scoring par article : positive×high=+75, negative×medium=-50, etc.
- **4 nouveaux endpoints API** :
  - `POST /news/history/persist` : Trigger manuel de la persistance RSS → DB
  - `GET /news/history/range` : Plage de dates disponible
  - `GET /news/history/coverage` : Couverture globale (toutes sources)
  - `GET /news/history/at-date` : Sentiment à une date donnée
- **33 nouveaux tests** (`test_news_history.py`) :
  - Modèle (4) : création, repr, multi-sources, URL nullable
  - Scoring (9) : positive/negative/neutral × high/medium/low, invalid
  - Service persist (3) : persist, idempotence, empty
  - Service query (7) : daily sentiment (positive, negative, none, mixed), articles, tolerance
  - Service range (4) : empty, with data, by source, coverage
  - Endpoints (6) : persist, range empty/with data, coverage, at-date empty/with data

### Technical
- 620 tests backend passing (587 → 620, +33 tests)
- Nouveau fichier : `backend/app/models/news_history.py`
- Nouveau fichier : `backend/app/services/news_history_service.py`
- Nouveau fichier : `backend/tests/test_news_history.py`
- Routes news étendues avec 4 endpoints `/news/history/*`

## [1.2.2] - 2026-04-05

### Added
- **Intégrité des données historiques** : Nouveau endpoint `GET /backtest/history/integrity` qui analyse la complétude des candles en base
  - Détection automatique des gaps (jours manquants), regroupement en plages consécutives
  - Grade de qualité : EXCELLENT (≥99%), GOOD (≥95%), WARNING (≥85%), CRITICAL (<85%)
  - Statistiques : total, attendues, manquantes, complétude %, détail textuel
- **Mode comparaison walk-forward** : Nouveau paramètre `compare_mode` pour l'analyse walk-forward
  - Exécute le walk-forward en double : technique seul vs technique + sentiment (Fear & Greed)
  - Calcul des deltas : Δ accuracy, Δ qualité, verdict automatique
  - Quantifie l'apport réel du sentiment sur la précision du modèle
- **Schémas Pydantic** : `WalkForwardComparison`, `WalkForwardSummaryStats`, `HistoryIntegrityGap`, `HistoryIntegrityResponse`
- **22 nouveaux tests** :
  - `TestHistoryIntegrity` (6) : no data, complete, with gaps, critical, min/max, timeframes
  - `TestIntegrityEndpoint` (2) : endpoint avec/sans données
  - `TestWalkForwardCompare` (4) : sans compare, avec compare, accuracy by horizon, endpoint
  - `TestNewSchemas` (10) : schema models, timeframe mapping, gap grouping
- **Frontend — Intégrité UI** : Affichage du grade qualité, complétude %, gaps détectés dans le VerificationPanel
- **Frontend — Compare mode UI** : Checkbox pour activer le mode comparaison, affichage side-by-side des résultats (technique seul vs technique + sentiment), delta chips, verdict

### Changed
- **VerificationPanel** : Nouvelle section intégrité après chargement, checkbox compare mode dans le walk-forward, affichage résultats de comparaison
- **Walk-forward endpoint** : Description mise à jour pour documenter le `compare_mode`

### Technical
- 587 tests backend passing (565 → 587, +22 tests)
- Frontend tsc --noEmit sans erreur
- Aucune régression sur les 565 tests existants

## [1.2.1] - 2026-04-05

### Added
- **Sentiment Historique — Fear & Greed Index** : Le moteur de décision utilise désormais le sentiment réel lors des backtests historiques
  - Nouveau modèle `SentimentHistory` (table SQL avec date, source, score brut 0-100, score normalisé -100/+100)
  - Client API Alternative.me (gratuit, ~2900 points depuis février 2018)
  - Chargement idempotent : relancer ne crée pas de doublons, met à jour les valeurs modifiées
  - Normalisation Fear & Greed : 0 (peur extrême) → -100, 50 (neutre) → 0, 100 (avidité) → +100
- **Intégration DecisionService ← Sentiment Historique** : En mode backtest (end_ts fourni), le moteur cherche le Fear & Greed Index en base au lieu du RSS temps réel
  - Mode complet : 70% technique + 30% sentiment historique (au lieu de 100% technique)
  - Fallback gracieux : si pas de sentiment à cette date → mode dégradé 100% technique
  - Le mode temps réel (pas de end_ts) continue d'utiliser le RSS comme avant
- **4 nouveaux endpoints API** :
  - `POST /sentiment/history/load` — Charger le Fear & Greed Index (~2900 jours en une requête)
  - `GET /sentiment/history/range` — Plage de dates disponible
  - `GET /sentiment/history/coverage` — Couverture globale (toutes sources)
  - `GET /sentiment/history/at-date` — Sentiment à une date donnée
- **42 nouveaux tests** : Modèle (4), normalisation (6), requête par date (6), plage/couverture (5), chargement mock (7), intégration DecisionService (3), endpoints (7), schemas (4)
- **Frontend — Types synchronisés v1.2** : `HorizonOutcome` (+quality_score, directional_match), `HorizonAccuracy` (+5 métriques), `WalkForwardResult` (+overall_quality_score)
- **Frontend — Types sentiment** : `SentimentLoadConfig`, `SentimentLoadResponse`, `SentimentRangeResponse`, `SentimentAtDateResponse`, `SentimentCoverageResponse`
- **Frontend — API sentiment** : `loadSentimentHistory()`, `getSentimentRange()`, `getSentimentCoverage()`, `getSentimentAtDate()`
- **VerificationPanel amélioré** : Bouton "Charger Fear & Greed", affichage qualité score, directional match, métriques walk-forward v1.2

### Changed
- **DecisionService** : La méthode `analyze()` détecte automatiquement si `end_ts` est fourni pour router entre sentiment live (RSS) et historique (Fear & Greed en base)
- **VerificationPanel** : Message d'info dynamique selon que le sentiment historique est chargé ou non

### Technical
- 565 tests backend passing (523 → 565, +42 tests)
- Frontend tsc --noEmit sans erreur
- Aucune régression sur les 523 tests existants

## [1.2.0] - 2026-04-05

### Added
- **ADX(14) — Average Directional Index** : Nouveau filtre de tendance dans le moteur de signaux
  - ADX ≥ 25 = tendance forte (confirme les signaux), ADX < 20 = range (atténue les signaux)
  - DI+/DI- pour la direction de la tendance
  - Réduit les faux signaux dans les marchés latéraux (cause majeure des "incorrect")
- **Volume SMA(20)** : Confirmation des mouvements par le volume
  - Volume > 1.5x SMA → boost de confiance, Volume < 0.5x SMA → méfiance
  - Le volume ne donne pas de direction mais module le score composite
- **`interpret_adx()`** : Interpréteur ADX avec 4 niveaux (très fort, fort, faible, neutre)
- **`interpret_volume_trend()`** : Interpréteur volume avec ratio vs SMA
- **Seuils adaptatifs de volatilité** : Les seuils hausse/baisse/stable sont calculés à partir de la volatilité récente (écart-type des rendements quotidiens) au lieu de seuils fixes
  - `_compute_recent_volatility()` : Calcule la volatilité sur 30 jours glissants
  - `_get_adaptive_thresholds()` : Seuils = volatilité × √(horizon) × facteur
- **Score de qualité 0-100** : Chaque prédiction reçoit un score de qualité proportionnel
  - Alignement directionnel (0-50 pts), proportionnalité score/mouvement (0-30 pts), confiance (0-20 pts)
  - Remplace l'évaluation binaire correct/incorrect par une mesure continue
- **Directional accuracy** : Métrique "le signe du score correspond-il à la direction réelle ?"
- **Métriques walk-forward avancées** :
  - `directional_accuracy_pct` : % de match directionnel
  - `avg_quality_score` : Score qualité moyen par horizon
  - `high_confidence_accuracy_pct` : Précision des signaux forts (|score| > 25)
  - `profitable_direction_pct` : % de signaux profitables si suivis
  - `overall_quality_score` : Score qualité global du walk-forward
- **28 nouveaux tests** : ADX (7), Volume (6), MACD relatif (4), directional match (4), quality score (3), seuils adaptatifs (3), composite v1.2 (1)

### Changed
- **MACD — Seuils en % du prix** : Corrige un biais majeur où le MACD était toujours "fort" aux prix élevés ($100k) et "faible" aux prix bas ($3k). Les seuils sont maintenant 0.1%, 0.3%, 0.8%, 1.5% du prix au lieu de 10, 50, 200, 500 absolus
- **Score composite v1.2** : L'ADX module la confiance globale (×1.3 si ADX≥40, ×0.7 si ADX<20), le volume module le score (±10-15%)
- **Confiance HIGH** requiert désormais ADX ≥ 25 en plus du consensus unanime — plus conservateur mais plus fiable
- **`indicator_service.py`** : Calcule ADX(14), DI+, DI-, Volume SMA(20) en plus des indicateurs existants
- **`HorizonOutcome`** : Nouveaux champs `quality_score` (0-100), `directional_match` (bool)
- **`HorizonAccuracy`** : 5 nouvelles métriques avancées
- **`WalkForwardResult`** : Nouveau champ `overall_quality_score`

### Technical
- 523 tests backend passing (495 → 523, +28 tests)
- Frontend tsc --noEmit sans erreur
- Aucune régression sur les 495 tests existants

## [1.1.2] - 2026-04-05

### Fixed
- **Logique de vérification corrigée** : La fonction `_is_prediction_correct` marquait faussement toutes les prédictions comme INCORRECT
  - Le score directionnel est maintenant pris en compte (pas seulement l'action)
  - Les seuils s'adaptent à l'horizon temporel (7j, 30j, 90j) — BTC est volatile
  - "Attendre" signifie "pas assez de signal" et non "stabilité attendue"
  - Un score de -4 avec "attendre" + baisse réelle → désormais ✅ CORRECT (penchant validé)
  - Un score neutre + mouvement normal pour BTC (~20% en 7j, ~35% en 30j, ~50% en 90j) → ✅ CORRECT

### Added
- `_is_hold_correct()` : Sous-méthode dédiée à l'évaluation nuancée de "attendre"
- `_get_hold_tolerance()` : Marge d'erreur par horizon pour penchant directionnel
- `_get_neutral_threshold()` : Seuil adapté à la volatilité BTC par horizon
- **14 nouveaux tests** : Cas réels du screenshot 2020-01-01, penchants directionnels, seuils par horizon
- Affichage du penchant directionnel dans le détail des verdicts ("penchant haussier/baissier")

### Changed
- `_is_prediction_correct()` accepte désormais `predicted_score` et `horizon_days`
- "Acheter" est correct si pas de baisse franche (>2%), plus tolérant pour les mouvements stables
- "Vendre" est correct si pas de hausse franche (>2%)

### Technical
- 495 tests backend passing (481 → 495, +14 tests)
- Frontend tsc --noEmit sans erreur
- Aucune régression

## [1.1.1] - 2026-04-04

### Added
- **Vérification Historique v1.1.1** : Système de time-travel backtest permettant de vérifier les prédictions du modèle sur l'historique profond
- `verification_service.py` : Service de vérification avec verify_at_date() + walk_forward()
- `history_loader_service.py` : Chargement historique profond Binance 2017→maintenant avec pagination et upsert idempotent
- `verification.py` schemas : HistoryLoadConfig, HistoryLoadResponse, HistoryRangeResponse, VerificationRequest, VerificationResult, HorizonOutcome, WalkForwardConfig, WalkForwardResult, HorizonAccuracy
- `POST /backtest/history/load` : Charger l'historique BTC depuis Binance (2017→now)
- `GET /backtest/history/range` : Plage de dates disponible en base
- `POST /backtest/verify` : Vérification ponctuelle à une date (time-travel)
- `POST /backtest/walk-forward` : Analyse walk-forward complète avec précision par horizon
- **Comparaison prédiction/réalité** : Compare la recommandation du modèle avec la variation réelle à 7j, 30j, 90j
- **Walk-forward analysis** : Test automatique sur des dizaines de dates espacées régulièrement
- **Précision par horizon** : Taux de prédictions correctes par horizon (7j, 30j, 90j)
- `VerificationPanel.tsx` : UI pour charger historique, choisir une date, voir résultats ✅/❌, lancer walk-forward
- **33 nouveaux tests backend** : range, verify, walk-forward, correctness (7 cas), schemas (6), endpoints (5), mock loader

### Changed
- Dashboard intègre le VerificationPanel dans la grille
- `schemas/__init__.py` : export des schémas verification
- `routes/__init__.py` : export du router verification
- `main.py` : inclusion du router verification
- `marketApi.ts` : ajout des fonctions API verification
- `types/api.ts` + `types/index.ts` : types Verification

### Technical
- 481 tests backend passing (448 → 481, +33)
- Frontend tsc --noEmit sans erreur
- Mode 100% technique en historique (sentiment non disponible, documenté)
- Limitation connue : le sentiment historique sera ajouté en v1.2.5

## [1.1.0] - 2026-04-03

### Added
- **Backtesting Engine v1.1**: Moteur de replay historique validant empiriquement les decisions du moteur v1.0
- `backtest_service.py` : Replay candle par candle avec recalcul indicateurs/signaux/decision a chaque pas
- `backtest.py` schemas : BacktestConfig, BacktestTradeItem, BacktestMetrics, EquityPoint, BacktestMeta, BacktestResponse, TradeDirection
- `POST /backtest/run` : Endpoint lançant un backtest complet avec parametres configurables
- `backtest.py` route : Endpoint avec gestion d'erreurs (422/500)
- **Simulation de positions** : Achat quand action=acheter, vente quand action=vendre, un seul trade a la fois
- **Metriques completes** : Win rate, Sharpe ratio, max drawdown, profit factor, PnL net/%, avg trade duration
- **Buy & Hold benchmark** : Comparaison automatique avec strategie passive
- **Equity curve** : Capital + drawdown a chaque pas de temps
- **Journal de trades** : Liste detaillee (entree, sortie, PnL, duree, raison)
- **Warning suroptimisation** : Alerte si <10 trades ou Sharpe >3.0
- **Cloture automatique** : Position ouverte en fin de backtest fermee automatiquement
- **Warmup indicateurs** : Skip des premieres candles (min 5, max 30) pour convergence
- `BacktestPanel.tsx` : UI premium avec config (jours, capital), metriques visuelles, journal collapsible
- `useBacktest.ts` : Hook React avec launch/reset/loading/error
- Types TypeScript : TradeDirection, BacktestConfig, BacktestTradeItem, BacktestMetrics, EquityPoint, BacktestMeta, BacktestResponse
- **31 nouveaux tests backend** : schemas (6), metriques (9), integration DB (6), endpoints HTTP (5), edge cases (5)

### Changed
- Dashboard integre le BacktestPanel dans la grille "Analyse du marche"
- `marketApi.ts` : ajout de `runBacktest()`
- `schemas/__init__.py` : export des schemas backtest
- `routes/__init__.py` : export du router backtest
- `main.py` : inclusion du router backtest
- `types/api.ts` + `types/index.ts` : barrel exports des types Backtest

### Technical
- 448 tests backend passing (417 -> 448, +31)
- Frontend tsc --noEmit sans erreur
- Aucune nouvelle dependance npm/pip
- Pas de slippage ni frais simules (resultats optimistes, documente)
- Un seul trade a la fois (pas de positions multiples)


