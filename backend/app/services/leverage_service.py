"""
Service de Levier Automatique Intelligent — Paper Trading.

Calcule le levier optimal à appliquer sur une position paper trading
en fonction de la force du signal, du contexte de risque, et du profil actif.

Principes :
- Le levier n'est PAS un bouton manuel ; il est DÉCIDÉ par le moteur.
- Le risk engine a un VETO absolu : il peut réduire ou annuler le levier.
- Chaque décision est loggée avec sa raison.
- Le profil conservative force toujours levier = 1.0.

Formule :
    leverage = 1.0 + (score_factor × confidence_factor × volatility_factor) × (max_leverage - 1.0)
    Puis clamp à [1.0, max_leverage], puis veto risk engine.
"""

import logging
from typing import Optional

from app.schemas.journal import (
    TradingProfileParams,
    LeverageRecommendation,
)

logger = logging.getLogger(__name__)


class LeverageService:
    """
    Service de calcul de levier automatique.

    Usage :
        service = LeverageService()
        rec = service.compute_leverage(
            score=55, confidence="high",
            profile_params=params, risk_level="safe",
            daily_loss_remaining=250, daily_loss_limit=300,
        )
        # rec.final → levier à appliquer
    """

    @staticmethod
    def compute_leverage(
        score: float,
        confidence: str,
        profile_params: TradingProfileParams,
        risk_level: str = "safe",
        daily_loss_remaining: float = 1000.0,
        daily_loss_limit: float = 1000.0,
        current_volatility_pct: Optional[float] = None,
    ) -> LeverageRecommendation:
        """
        Calcule le levier automatique recommandé puis final (après veto risk).

        Args:
            score: Score composite du moteur de décision (0-100 en absolu)
            confidence: Niveau de confiance ("low", "medium", "high")
            profile_params: Paramètres du profil actif
            risk_level: Niveau de risque ("safe", "caution", "danger", "blocked")
            daily_loss_remaining: Montant restant avant daily loss limit (USD)
            daily_loss_limit: Limite daily loss totale (USD)
            current_volatility_pct: Volatilité récente en % (si disponible)

        Returns:
            LeverageRecommendation avec recommandé, final, raisons
        """
        reasons = []
        factors = {}

        max_leverage = profile_params.max_leverage

        # ─── Règle 1 : Profil sans levier → toujours x1 ───
        if not profile_params.leverage_enabled or max_leverage <= 1.0:
            reasons.append("Levier désactivé pour ce profil")
            return LeverageRecommendation(
                recommended=1.0,
                final=1.0,
                max_allowed=1.0,
                risk_adjusted=False,
                reasons=reasons,
                factors={"profile_leverage_disabled": True},
            )

        # ─── Règle 2 : Risk engine non "safe" → réduire ou bloquer ───
        if risk_level == "blocked":
            reasons.append("Risk engine : kill switch actif → levier x1")
            return LeverageRecommendation(
                recommended=1.0, final=1.0, max_allowed=max_leverage,
                risk_adjusted=True, reasons=reasons,
                factors={"risk_veto": "blocked"},
            )

        if risk_level == "danger":
            reasons.append("Risk engine : danger → levier x1")
            return LeverageRecommendation(
                recommended=1.0, final=1.0, max_allowed=max_leverage,
                risk_adjusted=True, reasons=reasons,
                factors={"risk_veto": "danger"},
            )

        # ─── Facteur 1 : Score (0-1) ───
        abs_score = abs(score)
        if abs_score >= 60:
            score_factor = 1.0
        elif abs_score >= 40:
            score_factor = 0.7
        elif abs_score >= 25:
            score_factor = 0.4
        else:
            score_factor = 0.1
        factors["score_factor"] = round(score_factor, 2)

        # ─── Facteur 2 : Confiance (0-1) ───
        conf_map = {"high": 1.0, "medium": 0.6, "low": 0.2}
        confidence_factor = conf_map.get(confidence, 0.2)
        factors["confidence_factor"] = confidence_factor

        # ─── Facteur 3 : Volatilité inverse (0.5-1.0) ───
        # Plus la volatilité est haute, moins on lève
        if current_volatility_pct is not None and current_volatility_pct > 0:
            if current_volatility_pct > 5.0:
                vol_factor = 0.3  # Très volatile → réduire fortement
            elif current_volatility_pct > 3.0:
                vol_factor = 0.5
            elif current_volatility_pct > 1.5:
                vol_factor = 0.7
            else:
                vol_factor = 1.0
        else:
            vol_factor = 0.7  # Pas de données vol → conservateur
        factors["volatility_factor"] = round(vol_factor, 2)

        # ─── Calcul du levier recommandé ───
        combined = score_factor * confidence_factor * vol_factor

        # [v1.8.1] En mode scalping (max_leverage ≤ 1.5), être plus conservateur
        # Le levier ne se justifie que si le signal est fort ET la confiance est haute
        # Sinon, forcer x1.0 pour ne pas amplifier les pertes sur un edge faible
        is_scalping_mode = max_leverage <= 1.5
        if is_scalping_mode and (confidence_factor < 0.8 or score_factor < 0.7):
            reasons.append(
                f"Score={abs_score:.0f} → {score_factor:.1f}, "
                f"Confiance={confidence} → {confidence_factor:.1f}, "
                f"Vol → {vol_factor:.1f}; Scalping conservateur → x1.0"
            )
            return LeverageRecommendation(
                recommended=1.0,
                final=1.0,
                max_allowed=max_leverage,
                risk_adjusted=True,
                reasons=reasons,
                factors={**factors, "scalping_conservative": True},
            )

        recommended = 1.0 + combined * (max_leverage - 1.0)
        # Arrondir au 0.5 le plus proche, minimum 1.0
        recommended = max(1.0, round(recommended * 2) / 2)
        recommended = min(recommended, max_leverage)
        factors["combined_factor"] = round(combined, 3)

        reasons.append(
            f"Score={abs_score:.0f} → {score_factor:.1f}, "
            f"Confiance={confidence} → {confidence_factor:.1f}, "
            f"Vol → {vol_factor:.1f}"
        )

        # ─── Veto risk engine : caution → cap à 50% du max ───
        risk_adjusted = False
        final = recommended
        if risk_level == "caution":
            cap = 1.0 + (max_leverage - 1.0) * 0.5
            if final > cap:
                final = max(1.0, round(cap * 2) / 2)
                risk_adjusted = True
                reasons.append(f"Risk caution → levier cappé à x{final:.1f}")

        # ─── Veto risk engine : marge daily loss insuffisante ───
        if daily_loss_limit > 0:
            remaining_ratio = daily_loss_remaining / daily_loss_limit
            if remaining_ratio < 0.3:
                final = 1.0
                risk_adjusted = True
                reasons.append(
                    f"Marge daily loss faible ({remaining_ratio:.0%}) → levier forcé x1"
                )
            elif remaining_ratio < 0.5 and final > 2.0:
                final = min(final, 2.0)
                risk_adjusted = True
                reasons.append(
                    f"Marge daily loss modérée ({remaining_ratio:.0%}) → levier cappé x{final:.1f}"
                )

        # Arrondir au 0.5
        final = max(1.0, round(final * 2) / 2)
        final = min(final, max_leverage)

        reasons.append(f"Levier final : x{final:.1f}")

        return LeverageRecommendation(
            recommended=round(recommended, 1),
            final=round(final, 1),
            max_allowed=max_leverage,
            risk_adjusted=risk_adjusted,
            reasons=reasons,
            factors=factors,
        )

