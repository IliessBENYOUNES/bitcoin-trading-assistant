"""
ExperimentalPaperTradingService — Moteur expérimental multi-strategy.

Encapsule le PaperTradingService existant et ajoute :
- Mode experimental activable via flag runtime
- Multi-strategy engine (5 stratégies orchestrées)
- Market context engine (détection range/trend/breakout)
- Risk layer global (anti-collision, exposition)
- Tracking enrichi (strategy_type, market_context, market_zone)

Le moteur standard reste 100% intact.
En mode "experimental", le tick est intercepté et redirigé vers
le multi-strategy engine.

EXPÉRIMENTAL — branche experiment/v2-fees-and-1m uniquement.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paper_account import PaperAccount, PaperTrade
from app.services.paper_trading_service import PaperTradingService
from app.services.multi_strategy_engine import MultiStrategyEngine, OrchestratorResult
from app.services.multi_strategy_risk import MultiStrategyRiskLayer
from app.services.market_context_engine import MarketContextEngine, MarketContext
from app.services.decision_service import DecisionService
from app.services.risk_service import RiskService
from app.services.trading_cost_service import get_cost_model
from app.schemas.paper_trading import PaperTickResult, SlotTickResult, PaperTradeResponse

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Engine mode : global runtime flag
# ─────────────────────────────────────────────────────────────────────────────

_engine_mode: str = "standard"  # "standard" | "experimental"


def get_engine_mode() -> str:
    """Retourne le mode moteur actuel."""
    return _engine_mode


def set_engine_mode(mode: str) -> str:
    """Change le mode moteur. Retourne le nouveau mode."""
    global _engine_mode
    if mode not in ("standard", "experimental"):
        raise ValueError(f"Mode invalide : {mode}. Valeurs : standard, experimental")
    _engine_mode = mode
    logger.info(f"🔧 Engine mode changé → {mode}")
    return _engine_mode


class ExperimentalPaperTradingService:
    """
    Service expérimental qui encapsule le PaperTradingService standard.

    En mode standard : délègue tout au service existant (zéro impact).
    En mode experimental : intercepte tick() pour utiliser le multi-strategy engine.
    """

    def __init__(self, db: Session):
        self.db = db
        self._standard = PaperTradingService(db)
        self._orchestrator = MultiStrategyEngine()
        self._risk_layer = MultiStrategyRiskLayer(
            max_total_exposure_pct=80.0,
            max_single_position_pct=35.0,
            max_simultaneous_positions=3,
            max_same_direction=2,
            min_entry_interval_seconds=15.0,
            max_drawdown_kill_pct=5.0,
        )

    @property
    def standard(self) -> PaperTradingService:
        """Accès au service standard (pour les méthodes non overridées)."""
        return self._standard

    def tick(self) -> PaperTickResult:
        """
        Point d'entrée principal.

        En mode standard : délègue au moteur existant.
        En mode experimental : utilise le multi-strategy engine.
        """
        if get_engine_mode() == "standard":
            return self._standard.tick()
        return self._experimental_tick()

    # ─────────────────────────────────────────────────────────────────────
    # Méthodes déléguées au standard (pas de changement)
    # ─────────────────────────────────────────────────────────────────────

    def get_or_create_account(self, **kwargs) -> PaperAccount:
        return self._standard.get_or_create_account(**kwargs)

    def get_open_positions(self) -> list[PaperTrade]:
        return self._standard.get_open_positions()

    def get_trades(self, **kwargs):
        return self._standard.get_trades(**kwargs)

    def get_metrics(self):
        return self._standard.get_metrics()

    def export_trades(self):
        return self._standard.export_trades()

    def close_position_manual(self, reason: str = "Fermeture manuelle"):
        return self._standard.close_position_manual(reason)

    # ─────────────────────────────────────────────────────────────────────
    # Tick expérimental multi-strategy
    # ─────────────────────────────────────────────────────────────────────

    def _experimental_tick(self) -> PaperTickResult:
        """
        Tick multi-strategy expérimental.

        Flow :
        1. Vérifier compte actif
        2. Récupérer prix courant
        3. Gérer les positions ouvertes (SL/TP/trailing via standard)
        4. Analyser le marché (DecisionService + MarketContextEngine)
        5. Orchestrer les stratégies (MultiStrategyEngine)
        6. Appliquer le risk layer
        7. Ouvrir les positions approuvées
        """
        now = datetime.now(timezone.utc)
        account = self._standard.get_or_create_account()

        if not account.is_active:
            return PaperTickResult(
                action_taken="inactive",
                detail="Compte paper inactif",
                current_price=0,
                timestamp=now.isoformat(),
            )

        # Prix courant
        current_price = self._standard._get_current_price()
        if not current_price:
            return PaperTickResult(
                action_taken="error",
                detail="Prix BTC indisponible",
                current_price=0,
                timestamp=now.isoformat(),
            )

        # ── PHASE 1 : Gérer les positions ouvertes ──────────────────
        open_positions = self._standard.get_open_positions()
        slot_results = []

        for trade in open_positions:
            exit_result = self._manage_open_position(trade, current_price, now)
            if exit_result:
                slot_results.append(exit_result)

        # Si une position a été fermée, retourner le résultat
        if slot_results:
            closed_results = [r for r in slot_results if "closed" in r.action_taken]
            if closed_results:
                primary = closed_results[0]
                return PaperTickResult(
                    action_taken=primary.action_taken,
                    detail=primary.detail,
                    position_closed=primary.position_closed,
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    slot_results=slot_results,
                )

        # ── PHASE 2 : Analyse de marché ─────────────────────────────
        # Fallback automatique : 5m → 30m → 4h selon les données disponibles
        decision_service = DecisionService(self.db)
        series = []
        decision = {}
        for tf, days in [("5m", 2), ("30m", 2), ("4h", 7)]:
            decision = decision_service.analyze(
                symbol="BTC/USD",
                timeframe=tf,
                history_days=days,
            )
            series = decision.get("_series", [])
            if len(series) >= 10:
                logger.info(f"[MULTI] Contexte marché via {tf} ({len(series)} candles)")
                break
        else:
            logger.warning(f"[MULTI] Données insuffisantes sur tous les timeframes (dernière série: {len(series)} candles)")

        # ── PHASE 3 : Orchestrer les stratégies ─────────────────────
        open_pos_dicts = [
            {
                "strategy_type": t.strategy_type or t.profile_type or "",
                "direction": t.direction,
                "position_size_usd": t.position_size_usd,
                "leverage": t.leverage or 1.0,
                "entry_price": t.entry_price,
            }
            for t in self._standard.get_open_positions()
        ]

        orch_result = self._orchestrator.evaluate_tick(
            series=series,
            decision=decision,
            current_price=current_price,
            open_positions=open_pos_dicts,
            max_simultaneous=account.max_open_positions or 3,
        )

        if not orch_result.approved_signals:
            # Labels lisibles pour l'UI
            regime_labels = {
                "range": "Range (latéral)",
                "trend": "Trend",
                "breakout": "Breakout",
                "unknown": "Analyse...",
            }
            zone_labels = {"low": "bas", "mid": "milieu", "high": "haut"}
            regime_label = regime_labels.get(orch_result.context.regime, orch_result.context.regime)
            zone_label = zone_labels.get(orch_result.context.zone, orch_result.context.zone)
            trend_info = ""
            if orch_result.context.trend_direction != "neutral":
                trend_info = f" {'↗' if orch_result.context.trend_direction == 'bullish' else '↘'}"

            detail = (
                f"Multi-strategy: {regime_label}{trend_info} · Zone {zone_label} | "
                f"Éligibles: {orch_result.eligible_strategies} | "
                f"Signaux: {len(orch_result.signals)} | "
            )
            if orch_result.rejected_reasons:
                detail += f"Rejetés: {'; '.join(orch_result.rejected_reasons[:2])}"
            else:
                detail += "Aucun signal assez fort"

            return PaperTickResult(
                action_taken="hold",
                detail=detail,
                current_price=current_price,
                timestamp=now.isoformat(),
                profile_type=f"experimental_{orch_result.context.regime}",
            )

        # ── PHASE 4 : Ouvrir les positions approuvées ────────────────
        opened_trades = []
        for signal in orch_result.approved_signals:
            params = orch_result.params_map.get(signal.strategy_type)
            if not params:
                continue

            # Risk layer check
            risk_check = self._risk_layer.check_signal(
                signal=signal,
                position_size_usd=params.position_size_usd,
                capital=account.current_capital,
                open_positions=open_pos_dicts,
                drawdown_pct=account.max_drawdown_pct,
                now=now,
            )

            if not risk_check.approved:
                logger.info(f"❌ Risk layer rejected {signal.strategy_type}: {risk_check.reason}")
                continue

            # Calculer SL/TP
            if signal.direction == "long":
                sl = current_price * (1 - params.stop_loss_pct / 100)
                tp = current_price * (1 + params.take_profit_pct / 100)
            else:
                sl = current_price * (1 + params.stop_loss_pct / 100)
                tp = current_price * (1 - params.take_profit_pct / 100)

            # Ouvrir la position via le moteur standard
            trade = self._standard._open_position(
                account=account,
                price=current_price,
                sl=sl,
                tp=tp,
                size_usd=params.position_size_usd,
                reason=signal.reason,
                score=signal.strength,
                direction=signal.direction,
                now=now,
                leverage=params.leverage,
                leverage_reason=f"multi_strategy_{signal.strategy_type}",
                profile_type=signal.strategy_type,
                slot=signal.strategy_type,  # Utiliser strategy_type comme slot
                entry_candle_direction=self._get_candle_direction(series),
            )

            if trade:
                # Enrichir avec les champs multi-strategy
                trade.strategy_type = signal.strategy_type
                trade.market_context = orch_result.context.regime
                trade.market_zone = orch_result.context.zone
                self.db.commit()

                opened_trades.append(trade)

                # Mettre à jour open_pos_dicts pour les prochains signaux
                open_pos_dicts.append({
                    "strategy_type": signal.strategy_type,
                    "direction": signal.direction,
                    "position_size_usd": params.position_size_usd,
                    "leverage": params.leverage,
                    "entry_price": current_price,
                })

        # Enregistrer le cooldown APRÈS la boucle (pas entre chaque signal du même tick)
        if opened_trades:
            self._risk_layer.record_entry(now)

        if opened_trades:
            trade = opened_trades[0]
            action = f"opened_{trade.direction}"
            strategies_opened = [t.strategy_type or "?" for t in opened_trades]
            detail = (
                f"Multi-strategy: {' + '.join(strategies_opened)} | "
                f"{orch_result.context.regime}/{orch_result.context.zone} | "
                f"{len(opened_trades)} position(s) ouverte(s)"
            )
            return PaperTickResult(
                action_taken=action,
                detail=detail,
                position_opened=PaperTradeResponse.model_validate(trade),
                current_price=current_price,
                timestamp=now.isoformat(),
                profile_type=f"experimental_{trade.strategy_type}",
                decision_score=trade.decision_score,
                slot_results=[
                    SlotTickResult(
                        slot=t.strategy_type or "unknown",
                        action_taken=f"opened_{t.direction}",
                        detail=f"{t.entry_reason[:100]}",
                        profile_type=t.strategy_type or "unknown",
                        position_opened=PaperTradeResponse.model_validate(t),
                    )
                    for t in opened_trades
                ],
            )

        return PaperTickResult(
            action_taken="hold",
            detail=f"Multi-strategy: signaux approuvés mais ouverture échouée",
            current_price=current_price,
            timestamp=now.isoformat(),
        )

    def _manage_open_position(
        self,
        trade: PaperTrade,
        current_price: float,
        now: datetime,
    ) -> Optional[SlotTickResult]:
        """
        Gère une position ouverte : SL, TP, trailing, micro SL, stale.

        Délègue la majorité au moteur standard via ses méthodes internes.
        """
        from app.services.strategies.base import StrategyParams

        strategy_type = trade.strategy_type or trade.profile_type or "scalping"
        strategy = self._orchestrator.strategies.get(strategy_type)

        # Calculer PnL latent
        if trade.direction == "long":
            unrealized_pct = (current_price - trade.entry_price) / trade.entry_price * 100
        else:
            unrealized_pct = (trade.entry_price - current_price) / trade.entry_price * 100

        # Vérifier SL/TP standard
        sl_tp_status = self._standard._check_sl_tp(trade, current_price)
        if sl_tp_status:
            closed = self._standard._close_position(trade, current_price, sl_tp_status, sl_tp_status)
            return SlotTickResult(
                slot=strategy_type,
                action_taken=sl_tp_status,
                detail=f"SL/TP atteint : {sl_tp_status}",
                profile_type=strategy_type,
                position_closed=PaperTradeResponse.model_validate(closed),
            )

        # Micro stop loss
        params = strategy.get_params(
            MarketContext(), trade.direction,
        ) if strategy else StrategyParams()

        if unrealized_pct <= -params.micro_sl_pct:
            reason = (
                f"Micro stop loss : PnL latent {unrealized_pct:.3f}% "
                f"(≤ -{params.micro_sl_pct}%) → sortie immédiate"
            )
            closed = self._standard._close_position(
                trade, current_price, reason, "closed_micro_sl",
            )
            return SlotTickResult(
                slot=strategy_type,
                action_taken="closed_micro_sl",
                detail=reason,
                profile_type=strategy_type,
                position_closed=PaperTradeResponse.model_validate(closed),
            )

        # Trailing stop
        peak_pct = 0.0
        if trade.direction == "long" and trade.highest_price_since_entry:
            peak_pct = (trade.highest_price_since_entry - trade.entry_price) / trade.entry_price * 100
            # Update highest
            if current_price > trade.highest_price_since_entry:
                trade.highest_price_since_entry = current_price
                self.db.commit()
        elif trade.direction == "short" and trade.lowest_price_since_entry:
            peak_pct = (trade.entry_price - trade.lowest_price_since_entry) / trade.entry_price * 100
            if current_price < trade.lowest_price_since_entry:
                trade.lowest_price_since_entry = current_price
                self.db.commit()

        if peak_pct >= params.trailing_activation_pct and unrealized_pct > 0:
            trailing_threshold = peak_pct * (1 - params.trailing_drop_ratio)
            if unrealized_pct <= trailing_threshold:
                reason = (
                    f"Trailing stop : pic {peak_pct:.3f}%, actuel {unrealized_pct:.3f}%, "
                    f"seuil {trailing_threshold:.3f}%"
                )
                closed = self._standard._close_position(
                    trade, current_price, reason, "closed_trailing_stop",
                )
                return SlotTickResult(
                    slot=strategy_type,
                    action_taken="closed_trailing_stop",
                    detail=reason,
                    profile_type=strategy_type,
                    position_closed=PaperTradeResponse.model_validate(closed),
                )

        # Stale exit (position en perte trop longtemps)
        duration_seconds = (now - trade.entry_ts.replace(tzinfo=timezone.utc)).total_seconds() \
            if trade.entry_ts else 0

        if duration_seconds > params.stale_negative_seconds and unrealized_pct < 0:
            reason = (
                f"Stale exit : position en perte depuis {duration_seconds:.0f}s, "
                f"PnL latent {unrealized_pct:.3f}%"
            )
            closed = self._standard._close_position(
                trade, current_price, reason, "closed_stale",
            )
            return SlotTickResult(
                slot=strategy_type,
                action_taken="closed_stale",
                detail=reason,
                profile_type=strategy_type,
                position_closed=PaperTradeResponse.model_validate(closed),
            )

        # Max hold time
        if duration_seconds > params.max_hold_seconds:
            reason = f"Durée max atteinte : {duration_seconds:.0f}s > {params.max_hold_seconds}s"
            closed = self._standard._close_position(
                trade, current_price, reason, "closed_expired",
            )
            return SlotTickResult(
                slot=strategy_type,
                action_taken="closed_expired",
                detail=reason,
                profile_type=strategy_type,
                position_closed=PaperTradeResponse.model_validate(closed),
            )

        # Sortie stratégique (ex: mean_reversion target atteint)
        if strategy:
            series = []  # Pas de série pour les exits rapides
            try:
                series = DecisionService(self.db).analyze(
                    timeframe="5m", history_days=1,
                ).get("_series", [])
            except Exception:
                pass

            context = MarketContextEngine.analyze(series) if series else MarketContext()
            exit_signal = strategy.evaluate_exit(
                context, trade, current_price, unrealized_pct,
            )
            if exit_signal.should_exit:
                closed = self._standard._close_position(
                    trade, current_price, exit_signal.reason, "closed_signal",
                )
                return SlotTickResult(
                    slot=strategy_type,
                    action_taken="closed_signal",
                    detail=exit_signal.reason,
                    profile_type=strategy_type,
                    position_closed=PaperTradeResponse.model_validate(closed),
                )

        return None  # Hold

    @staticmethod
    def _get_candle_direction(series: list[dict]) -> Optional[str]:
        """Extrait la direction de la dernière candle."""
        if not series:
            return None
        latest = series[-1]
        close = latest.get("close", 0)
        open_price = latest.get("open", 0)
        if close > open_price:
            return "green"
        elif close < open_price:
            return "red"
        return "green"
