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
        cooldown_minutes=15,
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
        # [v1.9.9] Quality gate minimum pour le slot aggressive.
        min_market_quality=25,
        min_volume_ratio=0.5,
        # [v2.0.0] Pas de gate économique sur aggressive : ses trades ont un
        # TP à 1.0% et une durée longue — le coût RT est négligeable.
        economic_gate_enabled=False,
        # [v2.0.0] Momentum fade normal sur aggressive (trades longue durée, pas de poussière)
        momentum_fade_mode="enabled",
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
        max_trades_per_day=30,  # [v2.0.0] 50→30 : moins de trades, meilleurs trades
        # [v2.0.11] Cooldown 2→1 min : le bearish_veto (v2.0.10) bloque les entrées
        # anti-tendance en amont, rendant le cooldown long redondant pour l'anti-churn.
        # 1 min permet de ne pas rater le prochain signal après un renversement de tendance.
        cooldown_minutes=1,
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
        analysis_timeframe="15m",
        buy_threshold=30,   # [v2.0.3] 25→30 : exiger un signal directionnel plus fort
        sell_threshold=20,
        # [v2.0.0] Momentum fade = RESTRICTED : principal destructeur de valeur identifié.
        # Le momentum fade sortait à +$1.59 avg quand le coût RT est $7.75.
        # En mode restricted, il ne se déclenche que si le pic >= 0.35% ($8.75 sur $2500).
        # En dessous de ce seuil, on laisse le trailing stop gérer la sortie.
        momentum_fade_enabled=True,
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
        trailing_stop_activation_pct=0.04,  # [v2.0.9] 0.02→0.04 : ~$1 de gain min
        trailing_stop_pct=0.06,  # fallback absolu (utilisé si drop_ratio est None)
        trailing_stop_drop_ratio=0.15,  # [v2.0.9] 15% : garde 85% du gain, réaliste pour 5sec ticks
        # [v2.0.12] GAIN EROSION STOP — Protection des petits gains (sous le seuil trailing).
        # Le trailing ne s'active qu'à 0.04% (~$1). Les gains entre $0 et $1 ne sont pas
        # protégés : ils fondent jusqu'au stale négatif (2 min) qui ferme en perte.
        # Avec gain_erosion_ratio=0.30, on sort dès que le gain a perdu 30% de son pic.
        # Peak +$0.60 → exit si gain < $0.42 (érosion > 30%). Sauve $0.42 au lieu de -$1.20.
        # S'active uniquement si peak ≥ 0.01% (~$0.25) pour éviter le bruit.
        gain_erosion_ratio=0.30,
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
        smart_cooldown_enabled=True,
        min_cooldown_minutes=0.5,
        # [v2.0.11] max_cooldown 10→5 min : en scalping, 10 min = éternité.
        # Le bearish_veto protège contre le rechurn, pas besoin de bloquer 10 min.
        max_cooldown_minutes=5.0,
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

