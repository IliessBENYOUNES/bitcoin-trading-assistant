"""
Service de backtesting - rejoue le moteur de decision sur l'historique.

Ce service :
1. Charge les candles historiques depuis la base
2. Itere candle par candle en recalculant indicateurs/signaux/decision
3. Simule des positions (achat quand action=acheter, vente quand action=vendre)
4. Calcule les metriques de performance (win rate, Sharpe, drawdown, etc.)
5. Genere une equity curve et un benchmark Buy & Hold

OPTIMISATION :
- Charge toutes les candles en un seul query
- Utilise end_ts pour chaque step (reproductibilite garantie par IndicatorService)
- Ne re-fetch pas de donnees, utilise uniquement la base

LIMITATIONS :
- Pas de slippage ni frais simules (resultats optimistes)
- Un seul trade a la fois (pas de positions multiples)
"""

import logging
import time
import math
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Candle
from app.services.decision_service import DecisionService
from app.schemas.decision import ActionType
from app.schemas.backtest import (
    BacktestConfig,
    BacktestTradeItem,
    BacktestMetrics,
    EquityPoint,
    BacktestMeta,
    BacktestResponse,
    TradeDirection,
)

logger = logging.getLogger(__name__)


class BacktestService:
    """
    Service de backtesting.

    Usage :
        service = BacktestService(db_session)
        result = service.run(BacktestConfig(
            symbol="BTC/USD",
            timeframe="4h",
            start_days_ago=30,
            initial_capital=10000.0,
        ))
    """

    def __init__(self, db: Session):
        self.db = db
        self.decision_service = DecisionService(db)

    def _load_candle_timestamps(
        self,
        symbol: str,
        timeframe: str,
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[datetime]:
        """Charge les timestamps des candles dans la fenetre, tries ASC."""
        rows = (
            self.db.query(Candle.timestamp)
            .filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp >= start_ts,
                Candle.timestamp <= end_ts,
            )
            .order_by(Candle.timestamp.asc())
            .all()
        )
        return [r[0] for r in rows]

    def _get_close_price_at(
        self,
        symbol: str,
        timeframe: str,
        ts: datetime,
    ) -> Optional[float]:
        """Recupere le prix de cloture a un timestamp donne."""
        candle = (
            self.db.query(Candle.close_price)
            .filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp == ts,
            )
            .first()
        )
        return candle[0] if candle else None

    def run(self, config: BacktestConfig) -> dict:
        """
        Execute un backtest complet.

        Boucle sur les candles historiques, evalue la decision a chaque pas,
        simule les trades et calcule les metriques.
        """
        t0 = time.time()

        now = datetime.now(timezone.utc)
        end_ts = now
        start_ts = now - timedelta(days=config.start_days_ago)

        # Charger les timestamps disponibles
        timestamps = self._load_candle_timestamps(
            config.symbol, config.timeframe, start_ts, end_ts
        )

        if len(timestamps) < 2:
            return BacktestResponse(
                meta=BacktestMeta(
                    symbol=config.symbol,
                    timeframe=config.timeframe,
                    start_ts=start_ts.isoformat(),
                    end_ts=end_ts.isoformat(),
                    initial_capital=config.initial_capital,
                    candles_analyzed=len(timestamps),
                ),
                metrics=BacktestMetrics(),
                summary="Donnees insuffisantes pour lancer le backtest (minimum 2 candles).",
            ).model_dump()

        # On ne demarre les decisions qu'apres un warmup suffisant
        # pour les indicateurs (au moins 30 candles de contexte)
        warmup = min(30, len(timestamps) // 3)
        if warmup < 5:
            warmup = 5

        decision_timestamps = timestamps[warmup:]
        if len(decision_timestamps) < 2:
            return BacktestResponse(
                meta=BacktestMeta(
                    symbol=config.symbol,
                    timeframe=config.timeframe,
                    start_ts=start_ts.isoformat(),
                    end_ts=end_ts.isoformat(),
                    initial_capital=config.initial_capital,
                    candles_analyzed=len(timestamps),
                ),
                metrics=BacktestMetrics(),
                summary="Pas assez de candles apres warmup des indicateurs.",
            ).model_dump()

        # Simulation
        trades: list[BacktestTradeItem] = []
        equity_curve: list[EquityPoint] = []
        capital = config.initial_capital
        position_open = False
        entry_price = 0.0
        entry_ts_str = ""
        entry_reason = ""
        decisions_made = 0

        # Premier prix pour Buy & Hold
        first_price = self._get_close_price_at(
            config.symbol, config.timeframe, decision_timestamps[0]
        )
        last_price = first_price

        peak_capital = capital

        for ts in decision_timestamps:
            price = self._get_close_price_at(
                config.symbol, config.timeframe, ts
            )
            if price is None:
                continue

            last_price = price

            # Evaluer la decision a ce timestamp
            # On utilise end_ts pour que l'IndicatorService ne voie
            # que les donnees jusqu'a ce point (pas de look-ahead)
            try:
                decision = self.decision_service.analyze(
                    symbol=config.symbol,
                    timeframe=config.timeframe,
                    history_days=config.start_days_ago,
                    end_ts=ts,
                )
                decisions_made += 1
            except Exception as e:
                logger.debug(f"Decision echouee a {ts}: {e}")
                continue

            action = decision.get("recommendation", {}).get("action", "attendre")
            combined_score = decision.get("combined_score", 0)
            summary_text = decision.get("summary", "")

            # Logique de trading
            if not position_open and action == ActionType.BUY.value:
                # Ouvrir une position longue
                position_open = True
                entry_price = price
                entry_ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)
                entry_reason = f"Score {combined_score:+d} - {summary_text}"

            elif position_open and action == ActionType.SELL.value:
                # Fermer la position
                pnl = (price - entry_price) / entry_price * capital
                pnl_pct = (price - entry_price) / entry_price * 100
                capital += pnl

                exit_ts = ts.isoformat() if isinstance(ts, datetime) else str(ts)

                # Calculer duree
                try:
                    entry_dt = datetime.fromisoformat(entry_ts_str)
                    exit_dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
                    duration_h = (exit_dt - entry_dt).total_seconds() / 3600
                except Exception:
                    duration_h = 0.0

                trades.append(BacktestTradeItem(
                    entry_ts=entry_ts_str,
                    exit_ts=exit_ts,
                    direction=TradeDirection.BUY,
                    entry_price=round(entry_price, 2),
                    exit_price=round(price, 2),
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    reason_entry=entry_reason,
                    reason_exit=f"Score {combined_score:+d} - {summary_text}",
                    duration_hours=round(duration_h, 1),
                ))

                position_open = False

            # Equity curve
            current_capital = capital
            if position_open:
                # Position ouverte : mark-to-market
                unrealized = (price - entry_price) / entry_price * capital
                current_capital = capital + unrealized

            peak_capital = max(peak_capital, current_capital)
            dd_pct = ((peak_capital - current_capital) / peak_capital * 100) if peak_capital > 0 else 0

            equity_curve.append(EquityPoint(
                ts=ts.isoformat() if isinstance(ts, datetime) else str(ts),
                capital=round(current_capital, 2),
                drawdown_pct=round(dd_pct, 2),
            ))

        # Si position encore ouverte a la fin, la fermer
        if position_open and last_price and last_price != entry_price:
            pnl = (last_price - entry_price) / entry_price * capital
            pnl_pct = (last_price - entry_price) / entry_price * 100
            capital += pnl
            last_ts = decision_timestamps[-1]
            exit_ts_str = last_ts.isoformat() if isinstance(last_ts, datetime) else str(last_ts)
            try:
                entry_dt = datetime.fromisoformat(entry_ts_str)
                exit_dt = last_ts if isinstance(last_ts, datetime) else datetime.fromisoformat(str(last_ts))
                duration_h = (exit_dt - entry_dt).total_seconds() / 3600
            except Exception:
                duration_h = 0.0
            trades.append(BacktestTradeItem(
                entry_ts=entry_ts_str,
                exit_ts=exit_ts_str,
                direction=TradeDirection.BUY,
                entry_price=round(entry_price, 2),
                exit_price=round(last_price, 2),
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
                reason_entry=entry_reason,
                reason_exit="Cloture automatique fin de backtest",
                duration_hours=round(duration_h, 1),
            ))

        # Calculer les metriques
        metrics = self._compute_metrics(
            trades, config.initial_capital, capital, equity_curve,
            first_price, last_price,
        )

        duration_s = time.time() - t0
        actual_start = timestamps[0]
        actual_end = timestamps[-1]

        summary = self._build_summary(metrics, len(trades), duration_s)

        return BacktestResponse(
            meta=BacktestMeta(
                symbol=config.symbol,
                timeframe=config.timeframe,
                start_ts=actual_start.isoformat() if isinstance(actual_start, datetime) else str(actual_start),
                end_ts=actual_end.isoformat() if isinstance(actual_end, datetime) else str(actual_end),
                initial_capital=config.initial_capital,
                candles_analyzed=len(timestamps),
                decisions_made=decisions_made,
                duration_seconds=round(duration_s, 2),
            ),
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            summary=summary,
        ).model_dump()

    def _compute_metrics(
        self,
        trades: list[BacktestTradeItem],
        initial_capital: float,
        final_capital: float,
        equity_curve: list[EquityPoint],
        first_price: Optional[float],
        last_price: Optional[float],
    ) -> BacktestMetrics:
        """Calcule toutes les metriques de performance."""
        total = len(trades)
        if total == 0:
            bh_pct = 0.0
            if first_price and last_price and first_price > 0:
                bh_pct = (last_price - first_price) / first_price * 100
            return BacktestMetrics(
                buy_and_hold_pnl_pct=round(bh_pct, 2),
            )

        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]
        win_rate = len(winning) / total if total > 0 else 0

        net_pnl = final_capital - initial_capital
        net_pnl_pct = net_pnl / initial_capital * 100 if initial_capital > 0 else 0

        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        # Max drawdown from equity curve
        max_dd = 0.0
        if equity_curve:
            max_dd = max(p.drawdown_pct for p in equity_curve)

        avg_pnl = net_pnl / total if total > 0 else 0
        avg_duration = sum(t.duration_hours for t in trades) / total if total > 0 else 0

        # Sharpe ratio (simplifie : rendements par trade)
        sharpe = 0.0
        if total >= 2:
            returns = [t.pnl_pct for t in trades]
            mean_ret = sum(returns) / len(returns)
            variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
            std_ret = math.sqrt(variance) if variance > 0 else 0
            sharpe = mean_ret / std_ret if std_ret > 0 else 0

        # Buy & Hold benchmark
        bh_pct = 0.0
        if first_price and last_price and first_price > 0:
            bh_pct = (last_price - first_price) / first_price * 100

        # Warning suroptimisation
        overfitting = total < 10 or sharpe > 3.0

        return BacktestMetrics(
            total_trades=total,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=round(win_rate, 4),
            net_pnl=round(net_pnl, 2),
            net_pnl_pct=round(net_pnl_pct, 2),
            profit_factor=round(min(profit_factor, 999.0), 2),
            max_drawdown_pct=round(max_dd, 2),
            avg_trade_pnl=round(avg_pnl, 2),
            avg_trade_duration_hours=round(avg_duration, 1),
            sharpe_ratio=round(sharpe, 2),
            buy_and_hold_pnl_pct=round(bh_pct, 2),
            overfitting_warning=overfitting,
        )

    def _build_summary(
        self,
        metrics: BacktestMetrics,
        trade_count: int,
        duration_s: float,
    ) -> str:
        """Resume lisible du backtest."""
        if trade_count == 0:
            return "Aucun trade genere durant la periode de backtest."

        parts = []
        parts.append(f"{trade_count} trades")
        parts.append(f"PnL {metrics.net_pnl_pct:+.1f}%")
        parts.append(f"Win rate {metrics.win_rate:.0%}")
        parts.append(f"Max DD {metrics.max_drawdown_pct:.1f}%")
        parts.append(f"B&H {metrics.buy_and_hold_pnl_pct:+.1f}%")

        if metrics.overfitting_warning:
            parts.append("ATTENTION suroptimisation possible")

        return " | ".join(parts) + f" ({duration_s:.1f}s)"

