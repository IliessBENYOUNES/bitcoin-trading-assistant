# Changelog

All notable changes to this project will be documented in this file.

## [2.0.28] - 2026-04-13

### Added
- **REFONTE PROTECTIONS AGGRESSIVE** — L'analyse du run v2.0.27 (58 trades) révèle que le slot aggressive opérait sans SAS, micro SL ni smart cooldown. Le trade #1108 a perdu 100% d'un pic de 0.705%, le trade #1102 a perdu -$6.60 sur un trailing tardif. Ajout de 3 protections :
  - **SAS d'entrée** (10s observation, 5s positif requis) — filtre les mauvaises entrées aggressive
  - **Micro SL à 0.15%** (-$3.75 max) — coupe les retournements post-entrée au lieu du SL swing -1.0% (-$25)
  - **Smart cooldown** (min 1 min, max 5 min) — adaptatif selon le résultat du trade précédent

### Changed
- **Aggressive trailing recalibré** : activation 0.15%→0.25% (laisse les swings se développer), drop ratio 0.30→0.20 (protège 80% du gain au lieu de 70%)
- **Aggressive gain erosion assoupli** : 0.50→0.70 (les swings oscillent naturellement, besoin de plus de respiration)
- **Aggressive cooldown réduit** : 15→5 min (permet 3× plus d'opportunités intraday)
- **Scalping cooldown optimisé** : `cooldown_minutes` 1.0→0.5 (30s), `min_cooldown` 0.5→0.25 (15s), `max_cooldown` 3.0→2.0 (2 min) — le micro SL à 0.05% casse les boucles churn, plus besoin du cooldown de 1 min
- **Scalping gain erosion assoupli** : 0.30→0.40 — donne plus de marge aux petits gains pour se développer vers le trailing
- **Gain erosion seuil min global relevé** : 0.01%→0.02% ($0.50) — les peaks < $0.50 sont du bruit de tick qui polluait le journal avec des exits à +$0.12-$0.18

### Technical
- Total tests backend : **1808** (assertions mises à jour, 0 test ajouté/supprimé)
- Tests mis à jour : test_smart_cooldown.py (cooldown), test_pivot_v200.py (gain erosion + aggressive), test_scalping_audit.py, test_diagnostic.py, test_runtime_truth.py, test_entry_sas.py (aggressive SAS), test_micro_stop_loss.py (aggressive micro SL)
- Frontend : `tsc --noEmit` sans erreur (aucun changement frontend)

## [2.0.27] - 2026-04-13

### Added
- **MINI CHART BTC 1M** — Nouveau graphique compact en chandeliers 1 minute sur l'onglet Trading. Affiche les 60 dernières bougies (1h de données) avec focus automatique sur les 15 dernières minutes. Données depuis Binance REST API (polling 30s), mise à jour en temps réel via le WebSocket live price existant. Désactivé en mode low-bandwidth et hors de l'onglet Trading.
- Nouveau hook `useMiniCandles.ts` — Fetch les klines 1m Binance directement (pas de stockage DB, données éphémères).
- Nouveau composant `MiniChart.tsx` — Version allégée du `CandlestickChart` : 250px de haut, pas de volume, header minimal avec prix + variation, focus auto 15 bougies.

### Fixed
- **TREND ALIGNMENT SYMÉTRIQUE** — Le filtre v2.0.26 ne bloquait que les SHORTs en marché bullish mais laissait passer les LONGs en marché bearish. Ajout du filtre miroir : les LONGs via tick_override sont maintenant bloqués quand le score technique est fortement bearish (score < -threshold). Une bougie verte 30s en tendance baissière est un faux signal → BTC redescend → le long ferme en perte.

### Changed
- Le trend alignment filter est désormais bidirectionnel : bloque SHORT quand score > +50, bloque LONG quand score < -50.
- 5 nouveaux tests pour le côté LONG (bloqué bearish, autorisé mild bearish, boundary -50, -51, long bullish OK).
- Test `test_long_not_affected_by_filter` renommé en `test_long_not_blocked_when_score_bullish` (le LONG est toujours autorisé en marché bullish, mais bloqué en bearish).

### Technical
- Total tests backend : **1808** (existants + 5 trend alignment long)
- Le filtre symétrique réutilise le même paramètre `trend_alignment_score_threshold` (seuil 50 en valeur absolue).
- Frontend : `tsc --noEmit` sans erreur, nouveau composant + hook ajoutés.

## [2.0.26] - 2026-04-13

### Added
- **TREND ALIGNMENT FILTER** — Nouveau gate d'entrée qui bloque les SHORTs via tick_override quand le score technique est fortement bullish (score > threshold). L'analyse de 92 trades (v2.0.25) montre que les shorts scalping perdent -$8.93 (47% WR) quand le score est à +64/+65 et BTC monte globalement. Le tick_override ouvre un short sur bougie rouge 30s, mais le marché bullish fait remonter le prix → le short est fermé en perte par "signal contraire" 36-72s plus tard.
- Nouveau paramètre `trend_alignment_score_threshold` sur `TradingProfileParams` (None = désactivé, 50 = bloque shorts quand score > 50).
- Gate inséré entre le momentum stability check et le scalping reversal check dans `_tick_single_slot`.
- 2 nouveaux labels dans `REASON_LABELS` : `trend_alignment_blocked`, `momentum_unstable`.
- 8 tests dédiés dans `TestTrendAlignmentFilter` : paramètres profils, intégration SHORT bloqué/autorisé, LONG non affecté, mean_reversion non affecté, boundaries exactes.

### Changed
- Profil scalping : `trend_alignment_score_threshold=50` (bloque shorts override quand score > 50)
- Les autres profils (conservative, balanced, aggressive) : `trend_alignment_score_threshold=None` (filtre inactif)

### Technical
- Total tests backend : **1804** (1796 existants + 8 trend alignment filter)
- Le filtre ne s'applique qu'aux shorts tick_override (`tm_override_active=True` et `action="vendre"`). Les shorts mean_reversion et les LONGs ne sont pas affectés.
- Impact estimé : élimination des shorts perdants en marché bullish, gain net estimé +$8.93 sur 92 trades

## [2.0.25] - 2026-04-13

### Fixed
- **MICRO STOP LOSS RECALIBRÉ 0.01% → 0.05%** — L'analyse de 345 trades montre que le micro SL à 0.01% tuait 130 trades (37.7%) avec un taux de perte de 100%, totalisant -$59.44. À lui seul, il transformait un système rentable (+$54) en système perdant (-$5.55). Le seuil est relevé à 0.05% (-$1.25 sur $2500) : le trade a 1-2 ticks pour respirer, tout en restant 4× plus serré que le SL classique (-0.20% = -$5).
- **COOLDOWN ANTI-CHURN 10s → 1min** — L'analyse montre 345 trades en 12h (29/h) avec un gap médian de 64 sec entre re-entries sur le MÊME signal. Le bot créait des boucles micro SL → re-entry → micro SL destructrices. Cooldown de base relevé à 1 min, min_cooldown à 0.5 min, max_cooldown à 3 min.
- **SL/TP EXÉCUTÉS AU PRIX DE L'ORDRE** — Avant, quand le SL/TP était franchi entre deux ticks (5 sec), la position était fermée au prix COURANT (qui pouvait être bien pire). Le trade #629 a perdu -$21.76 (-0.87%) alors que le SL était à -0.20%. Désormais, le SL/TP simule une exécution stop-limit : le prix de sortie est le prix de l'ordre, pas le prix de marché. La perte max par SL est bornée à loss_cut_pct.

### Changed
- `micro_stop_loss_pct` : 0.01 → 0.05 (profil scalping uniquement)
- `cooldown_minutes` : 0.17 → 1.0 (profil scalping)
- `min_cooldown_minutes` : 0.17 → 0.5 (profil scalping)
- `max_cooldown_minutes` : 1.0 → 3.0 (profil scalping)
- `_tick_single_slot` : SL/TP utilise `stop_loss_price`/`take_profit_price` comme exit price au lieu de `current_price`

### Technical
- Total tests backend : **1796** (tous passing, 18 tests mis à jour pour refléter les nouvelles valeurs)
- Analyse basée sur 345 trades réels du run du 12-13 avril 2026 (account 49)
- Profit factor estimé après corrections : ~1.5-2.0 (vs 0.96 avant)

## [2.0.24] - 2026-04-13

### Changed
- **SUPPRESSION LIMITE 30 TRADES/JOUR** — `max_trades_per_day` passé de 30 à 999 (illimité). La limite bloquait le robot en production après quelques heures, sans aucune justification de sécurité (le SAS + micro SL protègent en amont et en aval).
- **COOLDOWN ULTRA-COURT (10 sec)** — `cooldown_minutes` 1→0.17 (~10s), `min_cooldown_minutes` 0.5→0.17 (~10s), `max_cooldown_minutes` 5→1 (1 min max). Le diagnostic de fréquence identifiait le cooldown comme goulot d'étranglement principal.
- **SMART COOLDOWN ALLÉGÉ** — Multiplicateur stale 2.0→1.3, stale négatif 3.0→1.5, plancher stale négatif 2.0→0.5 (30 sec). Les anciennes pénalités anti-churn étaient calibrées AVANT le SAS (v2.0.22) et le micro SL (v2.0.23) — maintenant que ces protections existent, le cooldown peut être minimal.
- Schéma `cooldown_minutes` changé de `int` à `float` pour supporter les fractions de minute.

### Technical
- Total tests backend : **1796** (aucun nouveau test, 7 fichiers de tests mis à jour pour refléter les nouvelles valeurs)
- Justification : le SAS filtre les mauvaises entrées (10-15s observation virtuelle), le micro SL coupe à -0.01% instantanément. Le cooldown long comme substitut de protection n'a plus de raison d'être. Il suffit d'un tampon de 10s pour éviter les boucles open/close/reopen sur le même tick.

## [2.0.23] - 2026-04-13

### Added
- **MICRO STOP LOSS — SORTIE IMMÉDIATE EN PERTE** — Nouveau garde-fou ultra-serré qui ferme immédiatement une position dès que le PnL latent dépasse un seuil négatif configurable (-0.01% par défaut = -$0.25 sur $2500). Contrairement au loss_cut_pct classique (-0.20%, vérifié avec le score), le micro SL est INCONDITIONNEL et ultra-rapide. Philosophie : perdre $0.25 plutôt que risquer -$21 sur un retournement.
- Nouveau paramètre `micro_stop_loss_pct` sur `TradingProfileParams` (None = désactivé, 0.01 = sortie à -0.01%).
- Micro SL activé sur profil scalping (0.01%). Balanced, aggressive et conservative : désactivé (None).
- Priorité de sortie mise à jour : SL/TP > Expiration > **Micro SL** > Trailing Stop > Breakeven > Stale > Momentum fade.
- 18 tests dédiés (`test_micro_stop_loss.py`) : paramètres profils, calcul PnL, intégration _tick_single_slot, profil désactivé, non-régression trailing stop, edge cases.

### Changed
- `_tick_single_slot` : nouveau check micro SL ajouté juste après la mise à jour highest/lowest price, AVANT le trailing stop. C'est le premier check de sortie après SL/TP/expiration.
- Test `test_stale_still_works_for_never_profitable` adapté : avec le micro SL, une position en perte de -0.04% est coupée par le micro SL (-0.01%) AVANT le stale exit (comportement correct).
- Test `test_exit_priority_order` mis à jour pour vérifier que `closed_micro_sl` apparaît AVANT `closed_trailing_stop` dans le code source.

### Technical
- Total tests backend : **1796** (1778 existants + 18 micro stop loss)
- Le micro SL complète le SAS (v2.0.22) : le SAS filtre les mauvaises entrées en amont, le micro SL coupe les pertes en aval → double protection.

## [2.0.22] - 2026-04-13

### Added
- **SAS D'ENTRÉE SÉCURISÉ (ENTRY AIRLOCK)** — Nouveau mécanisme de validation pré-entrée. Quand tous les gates passent, au lieu d'ouvrir immédiatement, le système crée une entrée VIRTUELLE et observe le PnL pendant ~10-15 secondes. Si le PnL virtuel reste négatif → l'entrée est annulée (jamais de trade perdant dès le départ). Si le PnL virtuel devient positif et y reste ≥10s → l'entrée réelle est confirmée au prix courant. Résout le problème catastrophique du trade #620 (-$15.27 en 36s).
- **RANGE CAUTION** — Le SAS est plus strict aux extrémités de range. LONG en haut de range (>70%) ou SHORT en bas de range (<30%) → rejet immédiat dès le premier tick négatif. Élimine les positions structurellement dangereuses (achat au plafond, vente au plancher).
- Nouveau service `EntrySasService` (in-memory, pattern identique à `TickMomentumService`). Méthodes : `create_pending()`, `evaluate()`, `cancel()`, `clear()`.
- 4 nouveaux paramètres sur `TradingProfileParams` : `entry_sas_enabled`, `entry_sas_duration_seconds`, `entry_sas_min_positive_seconds`, `entry_sas_range_caution`.
- SAS activé sur profil scalping (15s max, 10s positif requis, range caution ON).
- Cleanup global `EntrySasService.clear()` dans conftest.py (isolation inter-tests).

### Changed
- `_tick_single_slot` : avant d'évaluer une nouvelle entrée, vérifie si un SAS est en attente. Si oui, évalue le PnL virtuel avant d'ouvrir. Après les gates, crée un SAS au lieu d'ouvrir directement (quand entry_sas_enabled=True).
- `reset_account()` : nettoie les SAS pending en mémoire via `EntrySasService.clear()`.
- Test `test_override_long_bypasses_structural_proofs` adapté pour accepter `sas_pending` comme preuve du bypass.

### Technical
- Ajouté : `backend/app/services/entry_sas_service.py` — Service SAS complet (SasPendingEntry, SasVerdict, EntrySasService)
- Modifié : `backend/app/schemas/journal.py` — 4 nouveaux champs TradingProfileParams
- Modifié : `backend/app/services/trading_profile_service.py` — SAS activé sur preset scalping
- Modifié : `backend/app/services/paper_trading_service.py` — ~100 lignes : SAS check + SAS creation
- Modifié : `backend/tests/conftest.py` — Fixture globale autouse _clean_sas_state
- Ajouté : `backend/tests/test_entry_sas.py` — 39 tests (création, évaluation, range caution, PnL, tracking, profils, scénarios réels)
- Tests : 1778 (+39)

## [2.0.21] - 2026-04-13

### Added
- **MOMENTUM STABILITY CHECK** — Nouveau gate d'entrée `check_momentum_stability()` dans `TickMomentumService`. Compare la direction du prix sur 2 fenêtres temporelles : longue (~30s, tendance globale) et courte (~10s, micro-tendance immédiate). Si la fenêtre longue dit "up" mais la courte dit "down", ça signifie que la bougie est en fin de vie et va probablement changer de couleur → l'entrée est bloquée avec raison `momentum_unstable`. Élimine les entrées juste avant un retournement de bougie (pastille qui change de couleur immédiatement après l'entrée).
- **JOURNAL FILTERS (frontend)** — Barre de filtres complète sur le journal des trades dans PaperTradingPanel : direction (Long/Short), résultat (Gagnant/Perdant), cohérence bougie entrée→sortie (Même couleur / Changée), slot (Scalping/Aggressive), type de sortie (TP/SL/Trail/etc.). Stats dynamiques affichées sous les filtres (nombre, wins, losses, win rate, PnL). Bouton reset. Permet d'observer instantanément les patterns de trades gagnants vs perdants.

### Changed
- `_tick_single_slot` : le momentum stability check est exécuté APRÈS la détection de direction override et AVANT l'ouverture de position. Bloque les entrées en fin de bougie.
- `PaperTradingPanel.tsx` : le journal utilise `filteredTrades` au lieu de `trades` directement. Les filtres sont appliqués côté client avec `useMemo`.

### Technical
- Ajouté : `TickMomentumService.check_momentum_stability()` — compare fenêtre courte vs longue + ratio de ticks
- Modifié : `paper_trading_service.py` — 20 lignes : momentum stability check après override direction
- Modifié : `PaperTradingPanel.tsx` — ~150 lignes : filtres état + UI + filteredTrades + stats
- Ajouté : 7 tests dans `TestMomentumStabilityV2021` (stable long, unstable long receding, stable short, unstable short rebounding, insufficient data, tick ratio, integration)
- Tests : 1739 (+7)

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
- Modifié : `frontend/src/types/api.ts` — reversal_delay_seconds sur PaperTradeItem + PaperTradeExportItem
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
- Tests : 1732 (+2)

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
- **Frontend — Intégrité UI** : Affichage du grade qualité, complétude %, gaps détectés dans le VerificationPanel
- **Frontend — Compare mode UI** : Checkbox pour activer le mode comparaison, affichage side-by-side des résultats (technique seul vs technique + sentiment), delta chips, verdict

### Changed
- **DecisionService** : La méthode `analyze()` détecte automatiquement si `end_ts` est fourni pour router entre sentiment live (RSS) et historique (Fear & Greed en base)
- **VerificationPanel** : Message d'info dynamique selon que le sentiment historique est chargé ou non

### Technical
- 587 tests backend passing (565 → 587, +22 tests)
- Frontend tsc --noEmit sans erreur
- Mode 100% technique en historique (sentiment non disponible, documenté)
- Limitation connue : le sentiment historique sera ajouté en v1.2.5

## [1.2.1] - 2026-04-05

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
- **33 nouveaux tests backend** : range, verify, walk-forward, correctness (7 cas), schemas (6), endpoints (5), edge cases (5)

### Changed
- Dashboard intègre le VerificationPanel dans la grille
- `marketApi.ts` : ajout de `runBacktest()`
- `schemas/__init__.py` : export des schemas backtest
- `routes/__init__.py` : export du router backtest
- `main.py` : inclusion du router backtest
- `types/api.ts` + `types/index.ts` : barrel exports des types Backtest

### Technical
- 481 tests backend passing (448 → 481, +33)
- Frontend tsc --noEmit sans erreur
- Mode 100% technique en historique (sentiment non disponible, documenté)
- Limitation connue : le sentiment historique sera ajouté en v1.2.5

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
- **33 nouveaux tests backend** : range, verify, walk-forward, correctness (7 cas), schemas (6), endpoints (5), edge cases (5)

### Changed
- Dashboard intègre le VerificationPanel dans la grille
- `marketApi.ts` : ajout de `runBacktest()`
- `schemas/__init__.py` : export des schemas backtest
- `routes/__init__.py` : export du router backtest
- `main.py` : inclusion du router backtest
- `types/api.ts` + `types/index.ts` : barrel exports des types Backtest

### Technical
- 481 tests backend passing (448 → 481, +33)
- Frontend tsc --noEmit sans erreur
- Mode 100% technique en historique (sentiment non disponible, documenté)
- Limitation connue : le sentiment historique sera ajouté en v1.2.5

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
- **33 nouveaux tests backend** : range, verify, walk-forward, correctness (7 cas), schemas (6), endpoints (5), edge cases (5)

### Changed
- Dashboard intègre le VerificationPanel dans la grille
- `marketApi.ts` : ajout de `runBacktest()`
- `schemas/__init__.py` : export des schemas backtest
- `routes/__init__.py` : export du router backtest
- `main.py` : inclusion du router backtest
- `types/api.ts` + `types/index.ts` : barrel exports des types Backtest

### Technical
- 481 tests backend passing (448 → 481, +33)
- Frontend tsc --noEmit sans erreur
- Mode 100% technique en historique (sentiment non disponible, documenté)
- Limitation connue : le sentiment historique sera ajouté en v1.2.5

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
- **33 nouveaux tests backend** : range, verify, walk-forward, correctness (7 cas), schemas (6), endpoints (5), edge cases (5)

### Changed
- Dashboard intègre le VerificationPanel dans la grille
- `marketApi.ts` : ajout de `runBacktest()`
- `schemas/__init__.py` : export des schemas backtest
- `routes/__init__.py` : export du router backtest
- `main.py` : inclusion du router backtest
- `types/api.ts` + `types/index.ts` : barrel exports des types Backtest

### Technical
- 481 tests backend passing (448 → 481, +33)
- Frontend tsc --noEmit sans erreur
- Mode 100% technique en historique (sentiment non disponible, documenté)
- Limitation connue : le sentiment historique sera ajouté en v1.2.5

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
- **33 nouveaux tests backend** : range, verify, walk-forward, correctness (7 cas), schemas (6), endpoints (5), edge cases (5)

### Changed
- Dashboard intègre le VerificationPanel dans la grille
- `marketApi.ts` : ajout de `runBacktest()`
- `schemas/__init__.py` : export des schemas backtest
- `routes/__init__.py` : export du router backtest
- `main.py` : inclusion du router backtest
- `types/api.ts` + `types/index.ts` : barrel exports des types Backtest

### Technical
- 481 tests backend passing (448 → 481, +33)
- Frontend tsc --noEmit sans erreur
- Mode 100% technique en historique (sentiment non disponible, documenté)
- Limitation connue : le sentiment historique sera ajouté en v1.2.5
