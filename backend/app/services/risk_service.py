"""
Service de gestion du risque (Risk Management Engine).

Ce service :
1. Gère la configuration de risque (CRUD singleton)
2. Évalue si un trade proposé respecte les limites
3. Calcule stop-loss, take-profit, position sizing
4. Gère le kill switch (activation/désactivation)
5. Suit la perte journalière (avec reset automatique)

Le risk engine ne prend PAS de décision de trading.
Il agit comme un filtre : il peut bloquer ou ajuster une décision
du moteur de décision si elle viole les règles de risque.

Intégration :
- Le DecisionService peut appeler evaluate_trade() pour vérifier
  qu'une recommandation respecte les limites avant de la finaliser.
"""

import logging
from datetime import datetime, timezone, date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.risk_config import RiskConfig
from app.schemas.risk import (
    RiskConfigCreate,
    RiskConfigUpdate,
    RiskConfigResponse,
    RiskEvaluation,
    RiskStatus,
    StopLossType,
)

logger = logging.getLogger(__name__)


class RiskService:
    """
    Service de gestion du risque.

    Usage :
        service = RiskService(db_session)
        config = service.get_config()
        evaluation = service.evaluate_trade("acheter", current_price=85000)
        status = service.get_status()
    """

    def __init__(self, db: Session):
        self.db = db

    # ================================================================
    # CONFIGURATION CRUD
    # ================================================================

    def get_config(self) -> RiskConfig:
        """
        Retourne la configuration de risque courante.
        Crée une config par défaut si aucune n'existe.
        """
        config = self.db.query(RiskConfig).first()
        if config is None:
            config = RiskConfig()
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
            logger.info("Configuration de risque par défaut créée")
        return config

    def create_or_update_config(self, data: RiskConfigCreate) -> RiskConfig:
        """
        Crée ou met à jour la configuration de risque (upsert).
        """
        config = self.db.query(RiskConfig).first()
        if config is None:
            config = RiskConfig(
                stop_loss_type=data.stop_loss_type.value,
                stop_loss_pct=data.stop_loss_pct,
                take_profit_pct=data.take_profit_pct,
                max_position_pct=data.max_position_pct,
                total_portfolio_value=data.total_portfolio_value,
                max_daily_loss_pct=data.max_daily_loss_pct,
            )
            self.db.add(config)
        else:
            config.stop_loss_type = data.stop_loss_type.value
            config.stop_loss_pct = data.stop_loss_pct
            config.take_profit_pct = data.take_profit_pct
            config.max_position_pct = data.max_position_pct
            config.total_portfolio_value = data.total_portfolio_value
            config.max_daily_loss_pct = data.max_daily_loss_pct
            config.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(config)
        logger.info(f"Configuration de risque mise à jour : SL={config.stop_loss_pct}%, TP={config.take_profit_pct}%")
        return config

    def update_config(self, data: RiskConfigUpdate) -> RiskConfig:
        """
        Met à jour partiellement la configuration de risque.
        """
        config = self.get_config()
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "stop_loss_type" and value is not None:
                value = value.value if hasattr(value, 'value') else value
            setattr(config, key, value)
        config.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(config)
        return config

    # ================================================================
    # DAILY LOSS TRACKING
    # ================================================================

    def _ensure_daily_reset(self, config: RiskConfig) -> None:
        """
        Vérifie si le compteur de perte journalière doit être remis à zéro.
        Reset automatique si la date a changé depuis le dernier reset.
        """
        today = date.today()
        if config.daily_loss_reset_date != today:
            config.daily_loss_current = 0.0
            config.daily_loss_reset_date = today
            self.db.commit()
            logger.info(f"Reset perte journalière (nouveau jour: {today})")

    def reset_daily_loss(self) -> RiskConfig:
        """
        Reset perte jour — Remet le compteur de perte journalière à zéro.

        Contrat métier strict :
        - Remet daily_loss_current à 0.0
        - Met à jour daily_loss_reset_date à aujourd'hui
        - Désactive le kill switch SI ET SEULEMENT SI déclenché par "Perte journalière"
        - Ne touche PAS aux trades, au capital, au learning, aux runs, ni aux logs
        """
        config = self.get_config()
        config.daily_loss_current = 0.0
        config.daily_loss_reset_date = date.today()
        # Désactiver le kill switch si déclenché par la perte journalière
        if config.kill_switch_active and config.kill_switch_reason and "Perte journalière" in config.kill_switch_reason:
            config.kill_switch_active = False
            config.kill_switch_reason = None
            config.kill_switch_triggered_at = None
        config.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(config)
        logger.info("🔄 Compteur de perte journalière remis à zéro")
        return config

    def record_loss(self, loss_usd: float) -> bool:
        """
        Enregistre une perte et vérifie si la limite journalière est atteinte.

        Args:
            loss_usd: Montant de la perte en USD (positif = perte)

        Returns:
            True si la limite est dépassée (kill switch déclenché)
        """
        config = self.get_config()
        self._ensure_daily_reset(config)

        config.daily_loss_current += abs(loss_usd)
        self.db.commit()

        daily_limit = config.total_portfolio_value * config.max_daily_loss_pct / 100
        if config.daily_loss_current >= daily_limit:
            logger.warning(
                f"⚠️ Limite de perte journalière atteinte ! "
                f"{config.daily_loss_current:.2f} USD >= {daily_limit:.2f} USD"
            )
            self.activate_kill_switch(
                reason=f"Perte journalière max atteinte ({config.daily_loss_current:.2f} USD / {daily_limit:.2f} USD)"
            )
            return True
        return False

    # ================================================================
    # KILL SWITCH
    # ================================================================

    def activate_kill_switch(self, reason: str = "Activation manuelle") -> RiskConfig:
        """Active le kill switch — bloque toutes les opérations de trading."""
        config = self.get_config()
        config.kill_switch_active = True
        config.kill_switch_triggered_at = datetime.now(timezone.utc)
        config.kill_switch_reason = reason
        config.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(config)
        logger.warning(f"🔴 KILL SWITCH ACTIVÉ : {reason}")
        return config

    def deactivate_kill_switch(self) -> RiskConfig:
        """Désactive le kill switch — autorise à nouveau les opérations."""
        config = self.get_config()
        config.kill_switch_active = False
        config.kill_switch_reason = None
        config.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(config)
        logger.info("🟢 Kill switch désactivé")
        return config

    # ================================================================
    # TRADE EVALUATION
    # ================================================================

    def evaluate_trade(
        self,
        proposed_action: str,
        current_price: float,
        atr_value: Optional[float] = None,
    ) -> RiskEvaluation:
        """
        Évalue si un trade proposé respecte les règles de risque.

        Args:
            proposed_action: Action proposée par le moteur de décision (acheter/vendre/attendre)
            current_price: Prix courant de l'actif
            atr_value: ATR (Average True Range) optionnel pour le mode ATR stop-loss

        Returns:
            RiskEvaluation avec l'action ajustée, SL/TP, taille max, raisons
        """
        config = self.get_config()
        self._ensure_daily_reset(config)

        reasons: list[str] = []
        warnings: list[str] = []
        allowed = True
        adjusted_action = proposed_action

        # --- Vérification 1 : Kill switch ---
        if config.kill_switch_active:
            allowed = False
            adjusted_action = "attendre"
            reasons.append(
                f"🔴 Kill switch actif : {config.kill_switch_reason or 'Activé manuellement'}"
            )

        # --- Vérification 2 : Perte journalière ---
        daily_limit = config.total_portfolio_value * config.max_daily_loss_pct / 100
        remaining = daily_limit - config.daily_loss_current

        if remaining <= 0 and proposed_action in ("acheter", "vendre"):
            allowed = False
            adjusted_action = "attendre"
            reasons.append(
                f"Perte journalière max atteinte ({config.daily_loss_current:.2f} USD / {daily_limit:.2f} USD)"
            )
        elif remaining < daily_limit * 0.2:
            # Avertissement si on approche de la limite (< 20% restant)
            warnings.append(
                f"⚠️ Proche de la limite de perte journalière "
                f"({config.daily_loss_current:.2f} / {daily_limit:.2f} USD, "
                f"reste {remaining:.2f} USD)"
            )

        # --- Calcul stop-loss / take-profit ---
        stop_loss_price = None
        take_profit_price = None
        risk_reward_ratio = None

        if proposed_action in ("acheter", "vendre") and current_price > 0:
            if proposed_action == "acheter":
                # Achat : SL en dessous, TP au dessus
                stop_loss_price = self._calculate_stop_loss(
                    config, current_price, direction="long", atr_value=atr_value
                )
                take_profit_price = current_price * (1 + config.take_profit_pct / 100)
            else:
                # Vente (short) : SL au dessus, TP en dessous
                stop_loss_price = self._calculate_stop_loss(
                    config, current_price, direction="short", atr_value=atr_value
                )
                take_profit_price = current_price * (1 - config.take_profit_pct / 100)

            # Ratio risque/récompense
            risk = abs(current_price - stop_loss_price) if stop_loss_price else 0
            reward = abs(take_profit_price - current_price) if take_profit_price else 0
            if risk > 0:
                risk_reward_ratio = round(reward / risk, 2)

            if risk_reward_ratio is not None and risk_reward_ratio < 1.0:
                warnings.append(
                    f"Ratio risque/récompense défavorable ({risk_reward_ratio:.2f}:1)"
                )

        # --- Calcul taille de position ---
        max_position_size_usd = config.total_portfolio_value * config.max_position_pct / 100

        # Si la taille de position dépasse le restant de perte journalière autorisée
        if remaining > 0 and max_position_size_usd > 0:
            # La perte max sur cette position (via SL) ne doit pas dépasser remaining
            if stop_loss_price and current_price > 0:
                sl_loss_pct = abs(current_price - stop_loss_price) / current_price
                potential_loss = max_position_size_usd * sl_loss_pct
                if potential_loss > remaining:
                    # Ajuster la taille de position
                    old_size = max_position_size_usd
                    if sl_loss_pct > 0:
                        max_position_size_usd = remaining / sl_loss_pct
                    warnings.append(
                        f"Position réduite de {old_size:.0f} à {max_position_size_usd:.0f} USD "
                        f"(risque journalier)"
                    )

        # --- Résumé des raisons si autorisé ---
        if allowed and proposed_action in ("acheter", "vendre"):
            reasons.append(
                f"✅ Trade autorisé — SL: {stop_loss_price:.2f}, TP: {take_profit_price:.2f}, "
                f"Position max: {max_position_size_usd:.0f} USD"
                if stop_loss_price and take_profit_price
                else "✅ Trade autorisé"
            )

        if proposed_action == "attendre":
            reasons.append("Action 'attendre' — pas de trade à évaluer")
            allowed = True

        return RiskEvaluation(
            allowed=allowed,
            original_action=proposed_action,
            adjusted_action=adjusted_action,
            stop_loss_price=round(stop_loss_price, 2) if stop_loss_price else None,
            take_profit_price=round(take_profit_price, 2) if take_profit_price else None,
            max_position_size_usd=round(max_position_size_usd, 2),
            risk_reward_ratio=risk_reward_ratio,
            reasons=reasons,
            warnings=warnings,
        )

    def _calculate_stop_loss(
        self,
        config: RiskConfig,
        current_price: float,
        direction: str,
        atr_value: Optional[float] = None,
    ) -> float:
        """
        Calcule le prix de stop-loss selon le type configuré.

        Args:
            config: Configuration de risque
            current_price: Prix courant
            direction: "long" (achat) ou "short" (vente)
            atr_value: ATR optionnel pour le mode ATR

        Returns:
            Prix de stop-loss
        """
        if config.stop_loss_type == "atr" and atr_value is not None and atr_value > 0:
            # ATR-based : stop-loss à 2× ATR du prix courant
            # Multiplicateur 2× est un standard raisonnable
            atr_multiplier = 2.0
            distance = atr_value * atr_multiplier
        else:
            # Fixed ou trailing (même calcul initial — trailing se met à jour dynamiquement)
            distance = current_price * config.stop_loss_pct / 100

        if direction == "long":
            return current_price - distance
        else:
            return current_price + distance

    # ================================================================
    # STATUS
    # ================================================================

    def get_status(self) -> RiskStatus:
        """
        Retourne l'état temps réel du risk engine.
        """
        config = self.get_config()
        self._ensure_daily_reset(config)

        daily_limit = config.total_portfolio_value * config.max_daily_loss_pct / 100
        daily_loss_pct_current = (
            (config.daily_loss_current / config.total_portfolio_value * 100)
            if config.total_portfolio_value > 0 else 0
        )
        remaining = max(0, daily_limit - config.daily_loss_current)
        max_position = config.total_portfolio_value * config.max_position_pct / 100

        # Déterminer le niveau de risque
        if config.kill_switch_active:
            risk_level = "blocked"
            detail = f"🔴 Kill switch actif — {config.kill_switch_reason or 'Activé manuellement'}"
        elif remaining <= 0:
            risk_level = "danger"
            detail = f"🔴 Limite de perte journalière atteinte ({config.daily_loss_current:.2f} / {daily_limit:.2f} USD)"
        elif daily_loss_pct_current >= config.max_daily_loss_pct * 0.7:
            risk_level = "caution"
            detail = (
                f"🟡 Proche de la limite ({config.daily_loss_current:.2f} / {daily_limit:.2f} USD, "
                f"reste {remaining:.2f} USD)"
            )
        else:
            risk_level = "safe"
            detail = f"🟢 Dans les limites ({config.daily_loss_current:.2f} / {daily_limit:.2f} USD)"

        config_response = RiskConfigResponse(
            id=config.id,
            stop_loss_type=config.stop_loss_type,
            stop_loss_pct=config.stop_loss_pct,
            take_profit_pct=config.take_profit_pct,
            max_position_pct=config.max_position_pct,
            total_portfolio_value=config.total_portfolio_value,
            max_daily_loss_pct=config.max_daily_loss_pct,
            daily_loss_current=config.daily_loss_current,
            kill_switch_active=config.kill_switch_active,
            kill_switch_triggered_at=(
                config.kill_switch_triggered_at.isoformat()
                if config.kill_switch_triggered_at else None
            ),
            kill_switch_reason=config.kill_switch_reason,
            created_at=config.created_at.isoformat() if config.created_at else None,
            updated_at=config.updated_at.isoformat() if config.updated_at else None,
        )

        return RiskStatus(
            config=config_response,
            kill_switch_active=config.kill_switch_active,
            daily_loss_current=round(config.daily_loss_current, 2),
            daily_loss_limit_usd=round(daily_limit, 2),
            daily_loss_pct=round(daily_loss_pct_current, 2),
            daily_loss_remaining_usd=round(remaining, 2),
            max_position_size_usd=round(max_position, 2),
            risk_level=risk_level,
            detail=detail,
        )

