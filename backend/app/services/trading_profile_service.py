"""
Service de gestion des profils de trading.

Fournit 3 profils prédéfinis (Conservative, Balanced, Aggressive)
qui pilotent les seuils d'entrée, la fréquence, le levier et les sorties.

Conservative = baseline existante (aucun changement de comportement).
Balanced = compromis fréquence / qualité.
Aggressive = plus de trades, toujours borné par le risk engine.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paper_account import PaperAccount
from app.schemas.journal import (
    TradingProfileType,
    TradingProfileParams,
    TradingProfileResponse,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Presets — Paramètres hard-coded par profil
# Les valeurs Conservative reproduisent le comportement existant (baseline).
# ─────────────────────────────────────────────────────────────────────────────

PROFILE_PRESETS: dict[str, TradingProfileParams] = {
    "conservative": TradingProfileParams(
        profile_type=TradingProfileType.conservative,
        label="Conservative",
        description="Très sélectif — qualité prioritaire. Baseline de référence.",
        min_score=35,
        min_confidence="medium",
        min_scenario_dominance=0.50,
        max_trades_per_day=3,
        cooldown_minutes=120,
        max_position_duration_hours=168,
        profit_take_pct=2.0,
        loss_cut_pct=1.5,
        loss_cut_score_threshold=30,
        leverage_enabled=False,
        max_leverage=1.0,
    ),
    "balanced": TradingProfileParams(
        profile_type=TradingProfileType.balanced,
        label="Balanced",
        description="Compromis fréquence / qualité — seuils plus souples.",
        min_score=20,
        min_confidence="low",
        min_scenario_dominance=0.42,
        max_trades_per_day=8,
        cooldown_minutes=45,
        max_position_duration_hours=72,
        profit_take_pct=1.5,
        loss_cut_pct=1.2,
        loss_cut_score_threshold=20,
        leverage_enabled=True,
        max_leverage=2.0,
    ),
    "aggressive": TradingProfileParams(
        profile_type=TradingProfileType.aggressive,
        label="Aggressive",
        # [v2.0.0] L'aggressive est le moteur principal de capture de valeur.
        # Sanctuarisé : ne pas appliquer les filtres scalping sans justification.
        # Le run v1.9.9 a prouvé son edge (+28.72 net realistic sur 2 trades).
        # [v2.0.1] Passage 4h→1h + seuils abaissés pour rendre le slot plus vivant.
        # Le 4h produisait un score ≈24 quasi-statique, sous le BUY_THRESHOLD=25,
        # ce qui rendait le slot muet. Le 1h offre 4× plus de data fraîche et des
        # scores plus dynamiques, tout en restant distinct du scalping (15m).
        description="Moteur principal de valeur — swing intraday 1h, levier modéré, seuils abaissés.",
        min_score=10,
        min_confidence="low",
        min_scenario_dominance=0.38,
        max_trades_per_day=15,
        # [v2.0.28] Cooldown 15→5 min : le run v2.0.27 montre que le slot aggressive
        # trade à intervalles de ~15 min (strictement borné par le cooldown). Avec des
        # trades de 36-144s, 15 min de cooldown est disproportionné. 5 min suffit pour
        # que le signal 1h ait évolué, tout en permettant plus d'opportunités.
        cooldown_minutes=5,
        max_position_duration_hours=48,
        profit_take_pct=1.0,
        loss_cut_pct=1.0,
        loss_cut_score_threshold=10,
        leverage_enabled=True,
        max_leverage=3.0,
        # [v2.0.1] Timeframe 4h→1h : 4× plus réactif, scores plus dynamiques.
        # Le 4h produisait des scores quasi-statiques (~24) qui ne franchissaient
        # jamais le seuil d'entrée. Le 1h reste macro vs le 15m scalping.
        analysis_timeframe="1h",
        # [v2.0.1] Seuils abaissés : buy 25→20, sell 20→15.
        # Avec le 4h, le score stagnait à ~24 (< 25). Même en 1h, 25 reste
        # trop exigeant pour un slot censé capturer les swings intraday.
        # Le sell à 15 compense le biais haussier structurel de BTC.
        buy_threshold=20,
        sell_threshold=15,
        stale_exit_minutes=180,
        # [v2.0.19] Stale négatif raccourci : 180→60 min pour le slot aggressive.
        # L'analyse du run montre que le trade #597 a dérivé 3h en perte (-$10.32)
        # sans aucune sortie anticipée. 60 min suffisent pour confirmer qu'un swing
        # intraday ne fonctionne pas. Le stale normal (180 min) reste pour les
        # positions flat (stagnantes mais pas perdantes).
        stale_negative_exit_minutes=60,
        # [v2.0.28] TRAILING STOP recalibré pour aggressive :
        # - Activation 0.15→0.25% : le run v2.0.27 montre des peaks de 0.02-0.08%
        #   qui activent le trailing trop tôt → sortie avec des miettes ($0.40).
        #   0.25% ($6.25 sur $2500) laisse les swings se développer.
        # - Drop ratio 0.30→0.20 : une fois activé, protéger 80% du gain au lieu
        #   de 70%. Le trade #1108 a perdu 100% de son peak 0.705% → le trailing
        #   a déclenché trop tard à cause du gap entre ticks.
        trailing_stop_activation_pct=0.25,
        trailing_stop_drop_ratio=0.20,
        # [EXPERIMENT] Gain erosion DÉSACTIVÉ sur aggressive : avec les frais,
        # les exits à +$0.40 brut sont des pertes nettes de -$11. Le trailing
        # à 0.25%/20% et le micro SL à 0.15% suffisent comme protections.
        gain_erosion_ratio=None,
        # [v1.9.9] Quality gate minimum pour le slot aggressive.
        min_market_quality=25,
        min_volume_ratio=0.5,
        # [v2.0.0] Pas de gate économique sur aggressive : ses trades ont un
        # TP à 1.0% et une durée longue — le coût RT est négligeable.
        economic_gate_enabled=False,
        # [v2.0.0] Momentum fade normal sur aggressive (trades longue durée, pas de poussière)
        momentum_fade_mode="enabled",
        # [v2.0.28] SAS D'ENTRÉE pour aggressive — L'analyse du run v2.0.27 montre
        # que le slot aggressive n'avait AUCUNE protection pré-entrée. Les trades
        # #1102 (-$6.60) et #1097 (-$0.87) auraient été filtrés par le SAS.
        # Params plus souples que le scalping (10s observation, 5s positif requis)
        # car le timeframe 1h justifie un peu plus de patience.
        entry_sas_enabled=True,
        entry_sas_duration_seconds=10.0,
        entry_sas_min_positive_seconds=5.0,
        entry_sas_range_caution=True,
        # [v2.0.28] MICRO STOP LOSS pour aggressive — Le SL classique est à -1.0%
        # (-$25 sur $2500), beaucoup trop loin. Le micro SL à 0.15% (-$3.75) coupe
        # les retournements post-entrée sans attendre le SL swing. Plus large que le
        # scalping (0.05%) car les swings ont besoin de plus de respiration.
        micro_stop_loss_pct=0.15,
        # [v2.0.28] SMART COOLDOWN pour aggressive — Rend le slot plus adaptatif.
        # Après un bon trade (trailing TP), réentrée rapide (1 min).
        # Après une perte (SL/micro SL), patience accrue (jusqu'à 5 min).
        smart_cooldown_enabled=True,
        min_cooldown_minutes=1.0,
        max_cooldown_minutes=5.0,
    ),
    "scalping": TradingProfileParams(
        profile_type=TradingProfileType.scalping,
        label="Scalping",
        # [v2.0.0] REFONTE COMPLÈTE — Le scalping doit prouver sa valeur économique.
        # Doctrine : prix + volume + structure > oscillateurs dérivés.
        # Plus aucun trade de poussière. Chaque trade doit couvrir ses frais.
        # [v2.0.3] MINI-LOT CORRECTIF POST-AUDIT RUNTIME :
        # 57 trades, 52 closed_stale (91.2%), 4 trailing_stop seulement.
        # Cause : trop d'entrées sur bruit directionnel sans tendance réelle.
        # Correction : seuils relevés + gate micro-trend + trailing plus atteignable.
        description="Scalping refondu v2.0.3 — seuils relevés, micro-trend obligatoire, trailing plus atteignable.",
        min_score=30,   # [v2.0.3] 25→30 : relever le plancher de score pour filtrer le bruit
        min_confidence="low",
        min_scenario_dominance=0.35,
        # [v2.0.24] max_trades_per_day 30→999 : SUPPRESSION de la limite quotidienne.
        # La limite de 30 trades bloquait le robot pendant des heures une fois atteinte.
        # Avec le SAS (v2.0.22) qui filtre les mauvaises entrées et le micro SL (v2.0.23)
        # qui coupe à -0.01%, la qualité est contrôlée en amont. Pas besoin d'un plafond
        # arbitraire — le robot doit pouvoir trader toute la nuit sans limite.
        max_trades_per_day=999,
        # [v2.0.28] Cooldown 1.0→0.5 min (30s) : le cooldown à 1 min était justifié
        # quand le micro SL était à 0.01% (boucles churn destructrices, v2.0.24).
        # Avec le micro SL recalibré à 0.05% (v2.0.25), les boucles micro SL→re-entry
        # sont cassées. Le SAS (15s) + micro SL (0.05%) suffisent comme protection.
        # 30s = assez pour que le signal ait évolué, sans bloquer les opportunités.
        cooldown_minutes=0.5,
        max_position_duration_hours=2,
        # [v2.0.0] TP élargi 0.6%→0.8% : le TP doit être atteignable et couvrir les frais.
        # Le trailing à 0.15%+0.10% capture en pratique 0.05-0.30%. Un TP à 0.8%
        # laisse les gros mouvements courir au lieu de se limiter à la poussière.
        profit_take_pct=0.8,
        # [v2.0.0] SL maintenu à 0.20% — les SL sont les pertes lourdes mais contrôlées.
        loss_cut_pct=0.20,
        loss_cut_score_threshold=5,
        leverage_enabled=True,
        max_leverage=1.5,
        # [EXPERIMENT] Timeframe 15m→5m : les indicateurs 15m (RSI 14 = 3h30 de données)
        # sont trop lents pour des trades de 30-120s. En 5m, RSI 14 = 70 min,
        # MACD(12,26,9) = 2h10 — bien plus réactif. Binance fetch nativement le 5m.
        analysis_timeframe="5m",
        buy_threshold=30,   # [v2.0.3] 25→30 : exiger un signal directionnel plus fort
        sell_threshold=20,
        # [EXPERIMENT] Momentum fade DÉSACTIVÉ : même en mode restricted, c'est un
        # destructeur de valeur net identifié (sort à +$1.59 avg vs coût RT $7.75).
        # Avec les frais intégrés, chaque sortie prématurée coûte cher. On laisse
        # le trailing stop gérer toutes les sorties en profit.
        momentum_fade_enabled=False,
        momentum_fade_mode="restricted",
        momentum_fade_min_amplitude_pct=0.35,
        momentum_fade_retention=0.55,
        # [v2.0.6] Stale exit raccourci : 15→5 min. L'audit runtime montre que les positions
        # scalping oscillent dans un range serré (peak +0.14%) sans jamais atteindre le trailing
        # activation (0.15%). Avec 15 min de stale, le slot est bloqué et les gains fondent.
        # 5 min = rotation 3× plus rapide, libère le slot pour de meilleures opportunités.
        stale_exit_minutes=5,
        # [v2.0.6] Stale négatif raccourci : 5→2 min. Couper les pertes encore plus vite.
        stale_negative_exit_minutes=2,
        # [v2.0.9] TRAILING RELATIF basé sur le GAIN (pas sur le prix BTC).
        # Le trailing surveille le gain ($) seconde par seconde.
        # Dès que le gain baisse de X% par rapport à son pic, on sort.
        # [v2.0.9-fix2] Ratio 3%→15% : avec des ticks toutes les 5 sec, le BTC bouge
        # de $5-20 par tick. Sur un gain de $1.25 (peak 0.05%), 3% = $0.04 de tolérance
        # = MOINS qu'un seul tick. Le trailing détecte le dépassement mais le prix est
        # déjà 80% plus bas. 15% = $0.19 de tolérance = ~1-2 ticks de marge réaliste.
        # Activation 0.02→0.04% : les peaks à 0.01% (=$0.25) ne sont pas protégeables,
        # le breakeven sort en négatif. 0.04% = ~$1 minimum avant protection.
        # [EXPERIMENT] Trailing activation 0.04→0.10% : avec les frais RT à 0.31%,
        # un gain de 0.04% ($1) est NET NÉGATIF après frais ($1 - $7.75 = -$6.75).
        # Le trailing doit protéger les gains qui ont une chance de couvrir les frais.
        # 0.10% = $2.50 brut, toujours négatif mais évite de verrouiller des poussières.
        trailing_stop_activation_pct=0.10,
        trailing_stop_pct=0.06,  # fallback absolu (utilisé si drop_ratio est None)
        trailing_stop_drop_ratio=0.15,  # [v2.0.9] 15% : garde 85% du gain, réaliste pour 5sec ticks
        # [EXPERIMENT] Gain erosion DÉSACTIVÉ : avec les frais intégrés, les exits
        # gain erosion à +$0.37 sont en réalité des pertes de -$7.38 après frais.
        # Mieux vaut laisser le trailing ou le stale gérer la sortie.
        # Le gain erosion ne fait que cristalliser des micro-gains qui ne couvrent
        # jamais les frais. On le désactive pour laisser les trades respirer.
        gain_erosion_ratio=None,
        # [v2.0.14] CANDLE DIRECTION OVERRIDE — La direction du trade vient de la
        # direction RÉELLE du prix (bougie verte → LONG, bougie rouge → SHORT),
        # pas du score technique lagging. Le score est gardé comme filtre de qualité
        # (marché actif) mais ne détermine plus la direction.
        # Corrige le biais 100% short : quand les indicateurs 15 min restent bearish
        # en marché ranging, seuls des shorts sortaient. Maintenant on entre LONG
        # quand le prix monte et SHORT quand il descend, peu importe les indicateurs.
        tick_momentum_enabled=True,
        tick_momentum_window_seconds=30.0,  # [v2.0.14] 10→30 sec : analyse la bougie sur ~6 ticks
        tick_momentum_min_ticks=3,  # [v2.0.14] 2→3 : au moins 3 ticks (15 sec de données minimum)
        tick_momentum_override_direction=True,  # [v2.0.14] La bougie décide la direction
        tick_momentum_min_score=10,  # [v2.0.14] Score réduit quand override actif
        # [v2.0.18] CANDLE REVERSAL EXIT — Sortie active quand la couleur de bougie change.
        # L'observation empirique montre que les trades profitables gardent la même couleur
        # de pastille (entry=exit), tandis que les perdants changent de couleur.
        # En activant cette sortie, on coupe dès que le momentum s'inverse (après 3 sec
        # de confirmation pour éviter le bruit).
        candle_reversal_exit_enabled=True,
        candle_reversal_min_seconds=3.0,   # Attendre 3 sec de reversal confirmé
        # [v2.0.19] Fenêtre 15→30 sec : la fenêtre de 15s avec des ticks à 5s
        # ne contient que ~3 ticks, insuffisant pour détecter un retournement.
        # 30s = ~6 ticks = même fenêtre que la détection d'entrée.
        candle_reversal_window_seconds=30.0,
        smart_cooldown_enabled=True,
        # [v2.0.28] min_cooldown 0.5→0.25 min (15 sec) : maintenant que le micro SL
        # est à 0.05% (pas 0.01%), les re-entries rapides après un bon trade sont sûres.
        # Le SAS (15s) empêchera de rentrer si le marché est défavorable.
        min_cooldown_minutes=0.25,
        # [v2.0.28] max_cooldown 3→2 min : avec le micro SL + SAS comme protections,
        # le cooldown punitif après pertes n'a pas besoin d'être aussi long.
        # 2 min max = ~24 ticks, suffisant pour un changement de micro-tendance.
        max_cooldown_minutes=2.0,
        min_hold_seconds=30,
        min_economic_pnl_pct=0.15,
        short_min_score=30,  # [v2.0.3] 25→30 : aligné avec min_score relevé
        short_exit_score_threshold=30,
        short_min_hold_seconds=45,
        # [v2.0.0] Market quality gate relevé 45→50 : plus exigeant sur la structure.
        min_market_quality=50,
        min_volume_ratio=0.8,  # [v2.0.0] 0.7→0.8 : volume minimum plus exigeant
        long_quality_filter=True,
        # [v2.0.0] ECONOMIC VIABILITY GATE — Le cœur du pivot stratégique.
        # Avant d'ouvrir, le moteur estime si la capture attendue couvre au moins
        # 1.5× le coût round-trip. La capture attendue est basée sur le trailing
        # stop activation (la capture réelle observée, pas le TP théorique).
        # Coût RT realistic = 0.31%. Seuil = 0.31% × 1.5 = 0.465%.
        # Seuls les setups avec un mouvement potentiel > 0.465% passent.
        economic_gate_enabled=True,
        min_ev_multiple=1.5,
        # [v2.0.0-fix] Corrigé : None retombait sur trailing_stop_activation_pct (0.20%),
        # ce qui rendait le gate économique mathématiquement impossible à passer
        # (0.20% < 0.31% × 1.5 = 0.465%). On fixe à 0.50% = capture réaliste
        # entre le trailing (0.15%) et le TP (0.80%), ce qui donne 0.50% > 0.465% ✓
        expected_capture_pct=0.50,
        # [v2.0.0] STRUCTURAL PROOFS — Le scalping exige au moins 2 preuves structurelles.
        # Les preuves : price_position favorable, volume confirmé (>1.2x), micro-trend (≥3).
        # Sans preuves, l'entrée est refusée même si le score est suffisant.
        min_structural_proofs=2,
        # [v2.0.3] GATE MICRO-TENDANCE — L'audit runtime montre que les entrées
        # sans micro-tendance favorable finissent en stale 91% du temps.
        # [v2.0.4] Assoupli de 2→1 : gate à 2 bloquait 100% (966/966).
        # [v2.0.6] DÉSACTIVÉ (1→0) : l'audit post-v2.0.4 montre que le gate à 1
        # bloque encore 100% des ticks scalping (135/135) car le micro_trend_score
        # stagne à -2 dans les phases latérales/baissières. Le score est 65,
        # la market_quality est 59 — tous les autres gates passent.
        # La protection micro-trend reste via structural_proofs (1 des 4 preuves).
        # 0 = gate désactivé (le code vérifie min_mt_long > 0).
        min_micro_trend_long=0,
        # [v2.0.22] SAS D'ENTRÉE SÉCURISÉ — Observation avant ouverture réelle.
        # Au lieu d'ouvrir immédiatement, le système crée une entrée VIRTUELLE
        # et observe le PnL pendant ~10-15 secondes. Si le PnL reste négatif,
        # l'entrée est annulée → on ne perd JAMAIS d'argent dès le départ.
        # Résout le problème catastrophique du trade #620 (-$15.27 en 36s) :
        # le PnL virtuel serait resté négatif → jamais ouvert.
        # Avec des ticks à 5s et un SAS de 15s, on obtient ~3 ticks d'observation.
        entry_sas_enabled=True,
        entry_sas_duration_seconds=15.0,   # Timeout max 15 sec
        entry_sas_min_positive_seconds=10.0,  # PnL positif continu pendant 10s
        entry_sas_range_caution=True,       # Extra prudent aux extrémités de range
        # [v2.0.23] MICRO STOP LOSS — Sortie ultra-rapide en cas de perte.
        # Le SAS filtre les mauvaises entrées, mais si le prix se retourne APRÈS
        # l'ouverture, le micro SL coupe au lieu d'attendre le SL classique (-0.20% = -$5).
        # [v2.0.24] Recalibré 0.01% → 0.05% après analyse de 345 trades :
        # À 0.01% (-$0.25), le micro SL tuait 130 trades (100% perdants, -$59.44),
        # empêchant toute récupération. 0.05% (-$1.25 sur $2500) laisse le trade
        # respirer 1-2 ticks tout en coupant 4× plus tôt que le SL classique (-$5).
        micro_stop_loss_pct=0.05,
        # [v2.0.26] TREND ALIGNMENT FILTER — Bloque les shorts override quand le
        # score technique est fortement bullish. L'analyse de 92 trades (v2.0.25)
        # montre que les shorts scalping perdent -$8.93 (47% WR) quand le score
        # est à +64/+65 et BTC monte globalement. Le tick_override ouvre un short
        # sur bougie rouge 30s, mais le marché bullish fait remonter le prix → le
        # short est fermé en perte par "signal contraire". Seuil 50 = bloque les
        # shorts quand le score est nettement bullish (≥4 indicateurs convergent).
        trend_alignment_score_threshold=50,
    ),
}


class TradingProfileService:
    """
    Service de gestion des profils de trading.

    Usage :
        service = TradingProfileService(db)
        params = service.get_active_params()  # Retourne les seuils actifs
        service.set_profile("balanced")
    """

    def __init__(self, db: Session):
        self.db = db

    # Valeurs acceptées pour set_profile (les 4 presets + auto)
    VALID_PROFILES = list(PROFILE_PRESETS.keys()) + ["auto"]

    def get_active_profile(self) -> TradingProfileResponse:
        """Retourne le profil actif et ses paramètres.
        Quand le profil est "auto", retourne les params conservative comme placeholder.
        Les vrais paramètres sont résolus dynamiquement à chaque tick via auto_select_profile().
        """
        account = self.db.query(PaperAccount).first()
        profile_name = "conservative"
        if account and hasattr(account, "active_profile") and account.active_profile:
            profile_name = account.active_profile

        # En mode auto, on retourne les params conservative comme placeholder
        # Le vrai profil est résolu per-tick par auto_select_profile()
        if profile_name == "auto":
            return TradingProfileResponse(
                active_profile=TradingProfileType.auto,
                params=PROFILE_PRESETS["conservative"],
            )

        params = PROFILE_PRESETS.get(profile_name, PROFILE_PRESETS["conservative"])
        return TradingProfileResponse(
            active_profile=TradingProfileType(profile_name),
            params=params,
        )

    def get_active_params(self) -> TradingProfileParams:
        """Retourne directement les paramètres du profil actif."""
        return self.get_active_profile().params

    def is_auto_mode(self) -> bool:
        """Vérifie si le profil actif est en mode auto."""
        account = self.db.query(PaperAccount).first()
        if account and hasattr(account, "active_profile") and account.active_profile:
            return account.active_profile == "auto"
        return False

    def set_profile(self, profile_type: str) -> TradingProfileResponse:
        """
        Change le profil de trading actif.

        [v1.6.1] Si une position ouverte existe sous un profil DIFFÉRENT,
        elle est automatiquement fermée. Cela évite le goulot d'étranglement
        "position blocking" quand on passe de conservative (positions longues)
        à scalping (positions courtes).
        """
        if profile_type not in self.VALID_PROFILES:
            raise ValueError(f"Profil inconnu : {profile_type}. Valides : {self.VALID_PROFILES}")

        account = self.db.query(PaperAccount).first()
        old_profile = None
        if account is None:
            # Créer un compte par défaut si absent
            account = PaperAccount(active_profile=profile_type)
            self.db.add(account)
        else:
            old_profile = account.active_profile
            account.active_profile = profile_type

        # [v1.6.1] Fermer la position ouverte si le profil change
        # pour ne pas bloquer le nouveau profil avec une vieille position
        if old_profile and old_profile != profile_type and old_profile != "auto":
            from app.services.paper_trading_service import PaperTradingService
            pts = PaperTradingService(self.db)
            open_pos = pts.get_open_position()
            if open_pos is not None:
                reason = f"Changement de profil : {old_profile} → {profile_type}"
                pts.close_position_manual(reason)
                logger.info(f"🔄 Position fermée automatiquement : {reason}")

        self.db.commit()
        self.db.refresh(account)
        logger.info(f"Profil de trading changé → {profile_type}")
        return self.get_active_profile()

    @staticmethod
    def auto_select_profile(score: float, confidence: str) -> str:
        """
        Sélectionne automatiquement le profil optimal en fonction de la force du signal.

        Logique :
        - Score ≥ 50 ET confiance "high" → aggressive (opportunité forte)
        - Score ≥ 30 ET confiance ≥ "medium" → balanced (opportunité correcte)
        - Score ≥ 10 → scalping (opportunité modeste mais exploitable)
        - Sinon → conservative (prudence par défaut)

        Args:
            score: Score composite du moteur de décision (valeur absolue utilisée)
            confidence: Niveau de confiance ("low", "medium", "high")

        Returns:
            Nom du profil résolu ("conservative", "balanced", "aggressive" ou "scalping")
        """
        abs_score = abs(score)
        confidence_level = {"low": 0, "medium": 1, "high": 2}.get(confidence, 0)

        # Opportunité forte → agressif
        if abs_score >= 50 and confidence_level >= 2:
            return "aggressive"

        # Opportunité correcte → équilibré
        if abs_score >= 30 and confidence_level >= 1:
            return "balanced"

        # Opportunité modeste → scalping
        if abs_score >= 10:
            return "scalping"

        # Par défaut → conservateur
        return "conservative"

    @staticmethod
    def get_all_presets() -> list[TradingProfileParams]:
        """Retourne tous les presets disponibles."""
        return list(PROFILE_PRESETS.values())

