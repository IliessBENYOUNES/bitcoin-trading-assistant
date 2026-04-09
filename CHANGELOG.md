# Changelog

All notable changes to this project will be documented in this file.

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
  - Formule : score_factor × confidence_factor × volatility_factor × max_leverage
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
- Frontend : `tsc --noEmit` sans erreur

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
- Frontend : `tsc --noEmit` sans erreur

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
  - `GET /news/history/range` : Plage de dates et nombre d'articles en base
  - `GET /news/history/coverage` : Couverture par source
  - `GET /news/history/at-date` : Articles + sentiment agrégé à une date donnée
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

## [1.0.0] - 2026-04-02

### Added
- **Decision Engine v1.0**: Moteur de décision combinant analyse technique (70%) et sentiment des news (30%) en recommandations explicables
- `decision_service.py` : Moteur de règles avec 8 règles combinées (RSI overbought/oversold, MACD cross, SMA trend, sentiment convergence)
- `decision.py` schemas : Scenario, RuleResult, Recommendation, DecisionMeta, DecisionResponse, ActionType
- `GET /market/decision` : Endpoint retournant scénarios multi-outcome + recommandation + règles évaluées
- **3 scénarios** (Hausse / Stable / Baisse) avec probabilités normalisées (somme = 1.0)
- **Recommandation explicable** : Acheter / Vendre / Attendre avec confiance (high/medium/low) et raisons en français
- **Mode dégradé** : Fonctionne sans sentiment (100% technique si RSS échoue), indiqué dans `meta.sentiment_available`
- `DecisionPanel.tsx` : Composant premium avec jauge score combiné, barres scénarios, card recommandation, règles collapsibles
- `useDecision.ts` : Hook React avec fetch + refresh automatique
- Types TypeScript : ActionType, Scenario, RuleResult, DecisionRecommendation, DecisionMeta, DecisionResponse
- **75 nouveaux tests backend** : règles individuelles (18), scénarios mathématiques (14+9), recommandation (7), intégration DB (5), endpoint HTTP (5), propriétés paramétrées (17)

### Changed
- Dashboard intègre le DecisionPanel en première position de la grille "Analyse du marché"
- Bouton "Actualiser" rafraîchit aussi la décision
- Fetch API déclenche un refresh de la décision après le fetch
- `marketApi.ts` : ajout de `getDecision()`
- `schemas/__init__.py` : export des schémas decision
- `routes/__init__.py` : export du router decision
- `main.py` : inclusion du router decision
- `types/api.ts` + `types/index.ts` : barrel exports des types Decision

### Technical
- 417 tests backend passing (342 → 417, +75)
- Frontend tsc --noEmit sans erreur
- Aucune nouvelle dépendance npm/pip
- Score combiné = technique × 0.70 + sentiment × 0.30 (borné -100/+100)
- 8 règles évaluées : RSI overbought, RSI oversold, MACD bullish cross, MACD bearish cross, SMA trend up, SMA trend down, sentiment convergence bullish, sentiment convergence bearish

## [0.9.6] - 2026-04-02

### Added
- **14 timeframes Binance**: Support complet de tous les intervalles Binance natifs (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w)
- **Prix BTC temps réel via WebSocket**: `useLivePrice` hook connecté à `wss://stream.binance.com:9443/ws/btcusdt@ticker` (~1 update/seconde)
- **PriceTicker enrichi**: Variation 24h (%), High/Low 24h, Volume 24h en BTC, indicateur de connexion WebSocket, flash vert/rouge sur changement de prix
- **15 options de durée**: Durées fractionnelles (1h30, 3h, 6h, 12h) en plus des durées en jours (1j→1an)
- **44 nouveaux tests**: 66 combinaisons paramétrées (6 TF × 11 durées), tests intervalles 5m/15m

### Changed
- Endpoints `/market/indicators`, `/market/signals`, `/market/candles`, `/market/candles/gaps`, `/market/candles/fetch` acceptent maintenant les jours fractionnels (`float` au lieu de `int`)
- `align_to_bucket` étendu dans `time_buckets.py` et `resample_service.py` pour 14 timeframes (dont 3d aligné sur epoch, 1w aligné sur lundi)
- `BinanceService` supporte 14 intervalles avec mapping millisecondes complet
- Dashboard: sélecteur timeframe 14 options, sélecteur durée 15 options, fetch direct via `/market/candles/fetch`
- `DataFreshnessChip`: gestion gracieuse du status `NO_DATA` (pas de crash si freshness/completeness absents)
- `MarketGapsResponse` TypeScript: champs `freshness`, `completeness`, `stats`, `now_utc` rendus optionnels
- `useCandles`: ajout `limit=1000` par défaut pour supporter les petits timeframes
- Labels durée affichés en heures quand < 1 jour (ex: "6h" au lieu de "0.25j")

### Technical
- 342 tests backend passing (298 → 342, +44)
- Frontend tsc --noEmit sans erreur
- Aucune nouvelle dépendance npm/pip
- WebSocket Binance : reconnexion automatique avec backoff exponentiel (max 10 tentatives)

## [0.9.5] - 2026-04-02

### Added
- **Binance Service** (`binance_service.py`): Client HTTP async pour l'API publique Binance (OHLCV natif, toute granularité, pagination automatique, volume réel)
- **DataSource Router** (`data_source_router.py`): Routeur intelligent — Binance (prioritaire) avec fallback CoinGecko automatique
- **Resample 30m→4h** et **1h→4h**: Nouveaux resamplings pour chaîne complète 30m→1h→4h→1d
- **45 nouveaux tests**: BinanceService (parsing, mapping), DataSourceRouter (fallback), 24 combinaisons paramétrées, resample 30m→4h et 1h→4h
- Option **90 jours** dans le sélecteur d'historique du Dashboard

### Changed
- **Toutes les 24 combinaisons timeframe × jours débloquées** (30m+30j, 1h+14j, 4h+1j, 1d+2j, etc.)
- Endpoint `POST /market/candles/fetch` accepte désormais un paramètre `timeframe` explicite (optionnel, rétrocompatible)
- Endpoint `POST /market/candles/fetch` utilise DataSourceRouter (Binance + CoinGecko fallback)
- Scheduler `_fetch_and_store()` utilise DataSourceRouter au lieu de CoinGecko directement
- Job 30m resample maintenant aussi en 4h (chaîne complète)
- `resample_all()` orchestre la chaîne complète : 30m→1h, 30m→4h, 1h→4h, 4h→1d
- Suppression du cap frontend "30m/1h limité à 1 jour" — plus de limitation

### Technical
- 298 tests backend passing (253 → 298, +45)
- Frontend tsc --noEmit sans erreur
- Aucune nouvelle dépendance npm/pip (httpx déjà inclus)
- Source Binance : BTCUSDT (Tether) ≈ BTC/USD (<0.1% écart)

## [0.9.3] - 2026-04-02

### Changed
- **Layout intelligent responsive**: refonte complète de la disposition du Dashboard
- Chart en HERO pleine largeur (élément dominant, premier regard du trader)
- 3 colonnes sous le chart : Signaux | Alertes | News (scan horizontal rapide)
- Indicateurs détaillés en bas pleine largeur (données de référence)
- Labels de section avec icônes ("📊 Analyse du marché", "🔬 Données techniques")
- AppBar responsive : contrôles adaptés mobile (icônes seules), labels courts (30m/1h/4h/1d)
- Breakpoints MUI : xs=12, md=6, lg=4 pour les panels (empilé mobile → 2 col tablette → 3 col desktop)
- Bouton Fetch API masqué sur mobile, remplacé par icône
- Padding et spacing adaptatifs par taille d'écran

### Technical
- 253 tests backend passing
- Frontend tsc --noEmit sans erreur
- Aucune nouvelle dépendance

## [0.9.2] - 2026-04-02

### Changed
- **Premium Dark Trading UI**: Refonte visuelle complète sans changement d'architecture
- Thème MUI riche avec couleurs crypto (BTC Orange #F7931A, vert/rouge trading)
- Glassmorphism sur toutes les Cards (backdrop-filter: blur + rgba borders)
- AppBar sticky premium avec logo Bitcoin, contrôles intégrés, gradient
- Background gradient sombre style Bloomberg/TradingView
- Jauges demi-cercle SVG pour le score composite (SignalPanel) et le sentiment (NewsPanel)
- Polices premium : Inter (UI) + JetBrains Mono (chiffres/scores)
- Custom scrollbar dark, font-smoothing, text selection BTC orange
- Hover glow sur les boutons et Cards
- Tooltips glassmorphism, Alert arrondies, Chips premium

### Technical
- Aucune nouvelle dépendance (pur CSS + MUI overrides)
- 253 tests backend passing
- Frontend tsc --noEmit sans erreur

## [0.9.1] - 2026-04-02

### Added
- **Smart Alert Presets**: 12 stratégies d'alertes éprouvées activables en 1 clic
- `AlertPresets.tsx` : composant avec 3 catégories (Accumulation, Protection, Avancées)
- Stratégies basées sur les travaux de Wilder (RSI), Appel (MACD), Elder, Brandt
- RSI Survente (< 30), RSI Capitulation (< 20), MACD Haussier, Score Convergence (> 60)
- RSI Surachat (> 70), RSI Euphorie (> 80), MACD Baissier, Score Baissier (< -60)
- DCA Intelligent (Saylor), Euphorie Maximale (> 80), Capitulation Totale (< -80), RSI Pullback (< 45)
- Bouton "Tout activer" par catégorie ou global
- Détection automatique des presets déjà actifs (pas de doublons)
- Description détaillée avec contexte historique et preuves de performance pour chaque stratégie

### Changed
- AlertPanel intègre le composant AlertPresets entre le formulaire et la liste

### Technical
- 253 tests backend passing (aucun changement backend)
- Frontend tsc --noEmit sans erreur

## [0.9.0] - 2026-04-02

### Added
- **News & Sentiment System**: Collecte de news crypto avec analyse de sentiment et score d'impact
- `news_service.py` : collecteur RSS (CoinTelegraph, CoinDesk, Bitcoin Magazine) avec cache mémoire TTL 5min
- Classifieur de sentiment keyword-based (30+ mots bullish, 30+ mots bearish)
- Score d'impact (HIGH/MEDIUM/LOW) basé sur détection de mots-clés institutionnels/réglementaires
- Score de sentiment global -100/+100 pondéré par l'impact
- `news.py` schemas : NewsItem, NewsSentimentSummary, NewsResponse, SentimentType, ImpactLevel
- `GET /news` : liste des articles récents avec sentiment, impact et mots-clés (filtrable par sentiment)
- `GET /news/sentiment` : résumé du sentiment global uniquement
- `NewsPanel.tsx` : jauge de sentiment, liste d'articles avec liens, filtres, compteurs
- `useNews.ts` : hook React avec fetch + polling automatique (5min)
- Types TypeScript : NewsItem, NewsSentimentSummary, NewsResponse, SentimentType, ImpactLevel
- 43 nouveaux tests backend (sentiment, impact, RSS parsing, résilience, endpoints)
- Parser RSS intégré (pas de dépendance externe feedparser)

### Changed
- Dashboard intègre le NewsPanel sous AlertPanel
- Bouton "Actualiser" rafraîchit aussi les news
- `marketApi.ts` : ajout de `getNews()` et `getNewsSentiment()`
- `schemas/__init__.py` : export des schémas news
- `routes/__init__.py` : export du router news
- `main.py` : inclusion du router news
- `types/api.ts` + `types/index.ts` : barrel exports des types News

### Technical
- 253 tests backend passing (210 existants + 43 nouveaux)
- Frontend tsc --noEmit sans erreur
- Aucune dépendance ajoutée (utilise httpx existant pour RSS)
- Cache mémoire évite de surcharger les sources RSS
- Résilience : timeout 10s, fallback liste vide si source échoue

## [0.8.0] - 2026-04-02

### Added
- **Alert System**: Système complet d'alertes configurables avec évaluation automatique
- Modèle Alert en base (condition_type, operator, threshold, status, recurring)
- API CRUD complète : `GET/POST/PUT/DELETE /alerts` + `POST /alerts/check` + `GET /alerts/notifications`
- `alert_service.py` : CRUD + évaluation prix, RSI, MACD hist, score composite vs seuils
- `alert.py` schemas : AlertCreate, AlertUpdate, AlertResponse, AlertNotification, AlertCheckResponse
- Conditions supportées : `price`, `rsi`, `macd_hist`, `score` avec opérateurs `above` (≥) / `below` (≤)
- Alertes one-shot ou récurrentes (se réarment après déclenchement)
- `AlertPanel.tsx` : formulaire de création, liste des alertes, notifications polling
- `useAlerts.ts` : hook React avec CRUD + check + polling automatique (60s)
- Types TypeScript : AlertItem, AlertCreate, AlertNotification, AlertCheckResponse
- 48 nouveaux tests backend (CRUD, évaluation, récurrence, endpoints)
- `CLAUDE.md` : source unique de vérité pour l'agent IA (fusionne AGENT.md)

### Changed
- Dashboard intègre l'AlertPanel entre SignalPanel et IndicatorPanel
- Bouton "Actualiser" rafraîchit aussi les alertes
- Bouton "Fetch API" déclenche un check des alertes après le fetch
- `marketApi.ts` : ajout des fonctions `getAlerts()`, `createAlert()`, `deleteAlert()`, `checkAlerts()`
- `AGENT.md` : pointe désormais vers `CLAUDE.md` comme source de vérité
- `schemas/__init__.py` : export des schémas alert
- `models/__init__.py` : export du modèle Alert
- `main.py` : inclusion du router alerts

### Technical
- 210 tests backend passing (162 existants + 48 nouveaux)
- Frontend tsc --noEmit sans erreur
- Aucune dépendance ajoutée (utilise l'existant)

## [0.7.0] - 2026-04-02

### Added
- **Signal Engine**: Moteur d'interprétation des indicateurs techniques en signaux structurés
- `GET /market/signals` endpoint retournant signaux + score composite -100/+100
- `signal_service.py` : interpréteurs RSI, MACD, SMA, Bollinger → direction + force + message
- `signal.py` schemas : SignalItem, CompositeScore, ConfidenceLevel, SignalResponse
- Score composite avec confiance (high/medium/low) et consensus (unanimous/majority/divided)
- Résumé lisible auto-généré (ex: "RSI en surachat (72), MACD croisé baissier → Score -65")
- `SignalPanel.tsx` : jauge de score, liste signaux détaillés, badges consensus/confiance
- `useSignals.ts` : hook React pour fetch des signaux
- Types TypeScript : SignalItem, CompositeScore, MarketSignalsResponse
- 52 nouveaux tests backend (interpréteurs, composite, intégration, endpoint)

### Changed
- Dashboard intègre le SignalPanel au-dessus de l'IndicatorPanel
- Bouton "Actualiser" rafraîchit aussi les signaux
- `marketApi.ts` : ajout de `getSignals()`
- `schemas/__init__.py` : export des schémas signal

### Fixed
- Nettoyage du CHANGELOG.md (suppression des commandes shell en tête de fichier)

### Technical
- 162 tests backend passing (110 existants + 52 nouveaux)
- Frontend tsc --noEmit sans erreur
- Aucune dépendance ajoutée (utilise l'existant)

## [0.6.0] - 2026-04-01

### Added
- Dual-jobs scheduler (4h + 30m) avec resample automatique
- 4 timeframes supportés : 30m, 1h, 4h, 1d
- Frontend : sélecteur timeframe + historique, cap CoinGecko
- `StatusRow`, `DataFreshnessChip`, `SchedulerChip`
- Documentation CURRENT_STATE.md et AGENT.md

### Technical
- 110 tests backend passing

## [0.5.1] - 2026-01-09

### Added
- **Scheduler resample 4h→1d**: après chaque fetch CoinGecko 4h, les candles sont automatiquement agrégés en timeframe 1d
- `/scheduler/status` expose `last_result.resample.1d` avec le nombre de candles 1d créés
- 7 nouveaux tests backend pour le resample (`test_scheduler_resample_1d.py`)
- Support `db_upsert.py` dialect-aware (SQLite + PostgreSQL)
- Support `resample_service.py` pour agrégation OHLCV

### Fixed
- Candles 1d alignés sur 00:00 UTC (l'affichage peut montrer +01:00 selon timezone locale)

### Technical
- 89 tests backend passing
- Resample idempotent (upsert, pas de duplication)
- Erreur resample isolée (ne fait pas échouer le job principal)

## [0.5.0] - 2026-01-08

### Added
- Frontend Dashboard complet avec indicateurs RSI/MACD/SMA/Bollinger
- Chips DATA: FRESH/STALE/GAPS + SCHEDULER: ON/OFF
- Graphique chandeliers Lightweight Charts
- Bouton "Récupérer données" avec guards timeframe
- ErrorBoundary pour le graphique
---

## [v0.4-scheduler] - 2026-01-08

### Added
- **APScheduler integration** for automatic candle fetching
- `GET /scheduler/status` endpoint returning enabled, running, next_run_time, last_result
- Scheduler configuration via environment variables:
  - `SCHEDULER_ENABLED` (true/false)
  - `SCHEDULER_INTERVAL_MINUTES` (default: 240 = 4h)
  - `SCHEDULER_SYMBOL` (default: BTC/USD)
  - `SCHEDULER_DAYS` (default: 7)
- Thread-safe state management for scheduler
- Proper DB session handling (create/close per job)
- 16 new scheduler tests

### Changed
- `app/config.py`: Added scheduler settings fields
- `app/main.py`: Added scheduler startup/shutdown hooks

### Fixed
- FastAPI `Query(regex=...)` deprecated warning → `Query(pattern=...)`

### Documentation
- Added `CHANGELOG.md`
- Added `docs/requirements_traceability.md` (RTM)
- Added `backend/README.md` with setup instructions

### QA Status
- Tests: 88 passing
- Scheduler: `last_result.status: "success"`
- Freshness: `FRESH` (data_lag < 4h)
- Completeness: `OK` (43/43 candles)
- Global: `OK`

---

## [v0.3-indicators] - 2026-01-07

### Added
- `GET /market/indicators` endpoint
- Technical indicators: RSI(14), MACD(12,26,9), SMA(20,50,200), Bollinger(20,2)
- Centralized time utilities in `app/utils/time_buckets.py`
- NaN → null JSON serialization (warmup periods)
- `include_candles` parameter for full OHLCV in response
- `end_ts` parameter for backtest reproducibility
- 35 indicator tests

### Changed
- Bucket alignment logic unified (0/4/8/12/16/20 UTC for 4h)

---

## [v0.2-market-live] - 2026-01-06

### Added
- `GET /market/candles` endpoint with rolling window support
- `POST /market/candles/fetch` to fetch from CoinGecko API
- `GET /market/candles/gaps` for data quality analysis
- `GET /market/price` for current price
- `GET /market/info` for market data
- Completeness vs Freshness separation in QA
- PostgreSQL storage with SQLAlchemy
- Idempotent upsert (duplicates detection)

### Infrastructure
- FastAPI + Uvicorn
- PostgreSQL + SQLAlchemy
- React + TypeScript frontend (basic dashboard)
- pytest test suite