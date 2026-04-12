"""
Service Journal d'Évaluation Paper Trading.

Responsabilités :
1. Enregistrer chaque tick (log_tick)
2. Fournir des agrégations par période (période, jour, heure)
3. Analyser les raisons de non-trade
4. Qualifier le style de trading (distribution durées)
5. Fournir des statistiques d'activité/fréquence
"""

import logging
import math
from datetime import datetime, timezone, date, timedelta
from typing import Optional
from collections import Counter

from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from app.models.tick_activity_log import TickActivityLog
from app.models.paper_account import PaperAccount, PaperTrade
from app.schemas.journal import (
    JournalPeriodSummary,
    JournalDaySummary,
    JournalActivityStats,
    NonTradeReasonItem,
    JournalNonTradeReasons,
    JournalResponse,
    DurationBucket,
    TradingStyleResult,
)

logger = logging.getLogger(__name__)

# Labels humains pour les raisons de non-trade
REASON_LABELS = {
    "score_too_low": "Score trop faible",
    "confidence_too_low": "Confiance trop faible",
    "scenario_weak": "Scénario insuffisamment dominant",
    "sentiment_contradictory": "Sentiment contradictoire",
    "adx_too_low": "ADX trop faible (range)",
    "volume_insufficient": "Volume insuffisant",
    "position_already_open": "Position déjà ouverte",
    "risk_blocked": "Risk engine bloque",
    "daily_loss_protection": "Protection perte journalière",
    "kill_switch_active": "Kill switch actif",
    "cooldown_active": "Cooldown entre trades",
    "max_trades_reached": "Max trades/jour atteint",
    "decision_wait": "Décision = attendre",
    "no_decision_available": "Moteur indisponible",
    "inactive": "Paper trading inactif",
    "no_price": "Prix indisponible",
    "economic_viability_low": "Non-viable économiquement (coûts > capture)",
    "structural_proof_insufficient": "Preuve structurelle insuffisante",
    "micro_trend_insufficient": "Micro-tendance insuffisante pour long",
    "bearish_veto": "Veto bearish : marché en baisse → LONG bloqué",
    "closed_gain_erosion": "Gain erosion : gain érodé au-delà du seuil",
    "tick_momentum_mismatch": "Tick momentum : direction du prix ne confirme pas l'entrée",
    "tick_momentum_no_direction": "Tick momentum : bougie neutre, pas de direction claire",
    "tick_momentum_override": "Tick momentum : direction overridée par la bougie",
    "other": "Autre",
}


class JournalService:
    """Service d'évaluation / journal du paper trading."""

    def __init__(self, db: Session):
        self.db = db

    # ================================================================
    # ENREGISTREMENT
    # ================================================================

    def log_tick(
        self,
        account_id: int,
        action_taken: str,
        btc_price: Optional[float] = None,
        decision_score: Optional[float] = None,
        decision_action: Optional[str] = None,
        decision_confidence: Optional[str] = None,
        reason_no_trade: Optional[str] = None,
        reason_detail: Optional[str] = None,
        profile_type: str = "conservative",
        leverage_recommended: Optional[float] = None,
        leverage_final: Optional[float] = None,
        leverage_reason: Optional[str] = None,
        had_open_position: bool = False,
        unrealized_pnl: Optional[float] = None,
        trade_id: Optional[int] = None,
        # [v1.9.9] Quality gate trace — audit runtime
        market_quality_score: Optional[int] = None,
        volume_ratio: Optional[float] = None,
        price_position_pct: Optional[float] = None,
        range_width_atr: Optional[float] = None,
        micro_trend_score: Optional[int] = None,
        vwap_distance_pct: Optional[float] = None,
        quality_gate_passed: Optional[bool] = None,
        quality_gate_reason: Optional[str] = None,
        # [v2.0.0] Economic viability gate trace
        estimated_round_trip_cost: Optional[float] = None,
        min_capture_required_pct: Optional[float] = None,
        economic_gate_passed: Optional[bool] = None,
        rejection_category: Optional[str] = None,
    ) -> TickActivityLog:
        """Enregistre un tick dans le journal d'activité."""
        entry = TickActivityLog(
            account_id=account_id,
            timestamp=datetime.now(timezone.utc),
            btc_price=btc_price,
            action_taken=action_taken,
            decision_score=decision_score,
            decision_action=decision_action,
            decision_confidence=decision_confidence,
            reason_no_trade=reason_no_trade,
            reason_detail=reason_detail,
            profile_type=profile_type,
            leverage_recommended=leverage_recommended,
            leverage_final=leverage_final,
            leverage_reason=leverage_reason,
            had_open_position=1 if had_open_position else 0,
            unrealized_pnl=unrealized_pnl,
            trade_id=trade_id,
            # Quality gate trace
            market_quality_score=market_quality_score,
            volume_ratio=volume_ratio,
            price_position_pct=price_position_pct,
            range_width_atr=range_width_atr,
            micro_trend_score=micro_trend_score,
            vwap_distance_pct=vwap_distance_pct,
            quality_gate_passed=1 if quality_gate_passed else (0 if quality_gate_passed is not None else None),
            quality_gate_reason=quality_gate_reason,
            # Economic viability trace
            estimated_round_trip_cost=estimated_round_trip_cost,
            min_capture_required_pct=min_capture_required_pct,
            economic_gate_passed=1 if economic_gate_passed else (0 if economic_gate_passed is not None else None),
            rejection_category=rejection_category,
        )
        self.db.add(entry)
        self.db.commit()
        return entry

    # ================================================================
    # JOURNAL COMPLET
    # ================================================================

    def get_journal(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        profile_filter: Optional[str] = None,
    ) -> JournalResponse:
        """Retourne le journal complet pour une plage de dates."""
        account = self.db.query(PaperAccount).first()
        if account is None:
            empty_period = JournalPeriodSummary(
                date_from=date_from or "N/A",
                date_to=date_to or "N/A",
            )
            return JournalResponse(
                period=empty_period,
                activity=JournalActivityStats(),
                non_trade_reasons=JournalNonTradeReasons(),
            )

        # Parse dates
        dt_from, dt_to = self._parse_date_range(date_from, date_to)
        profile = profile_filter or (
            account.active_profile if hasattr(account, "active_profile") and account.active_profile
            else "conservative"
        )

        period = self._compute_period_summary(account.id, dt_from, dt_to)
        daily = self._compute_daily_summaries(account.id, dt_from, dt_to)
        activity = self._compute_activity_stats(account.id, dt_from, dt_to)
        non_trade = self._compute_non_trade_reasons(account.id, dt_from, dt_to)

        return JournalResponse(
            period=period,
            daily=daily,
            activity=activity,
            non_trade_reasons=non_trade,
            profile_type=profile,
        )

    # ================================================================
    # SYNTHÈSE DE PÉRIODE
    # ================================================================

    def _compute_period_summary(
        self, account_id: int, dt_from: datetime, dt_to: datetime,
    ) -> JournalPeriodSummary:
        """Calcule les métriques synthétiques de la période."""
        # Ticks dans la période
        total_ticks = (
            self.db.query(func.count(TickActivityLog.id))
            .filter(
                TickActivityLog.account_id == account_id,
                TickActivityLog.timestamp >= dt_from,
                TickActivityLog.timestamp <= dt_to,
            )
            .scalar() or 0
        )

        # Trades fermés dans la période
        closed_trades = (
            self.db.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account_id,
                PaperTrade.status != "open",
                PaperTrade.exit_ts >= dt_from,
                PaperTrade.exit_ts <= dt_to,
            )
            .order_by(PaperTrade.exit_ts.asc())
            .all()
        )

        total_trades = len(closed_trades)
        days_span = max(1, (dt_to - dt_from).days)
        hours_span = max(1, (dt_to - dt_from).total_seconds() / 3600)

        if total_trades == 0:
            return JournalPeriodSummary(
                date_from=dt_from.strftime("%Y-%m-%d"),
                date_to=dt_to.strftime("%Y-%m-%d"),
                total_ticks=total_ticks,
                verdict="N/A — Aucun trade sur la période",
            )

        pnls = [t.pnl for t in closed_trades if t.pnl is not None]
        wins = [p for p in pnls if p >= 0]
        losses = [p for p in pnls if p < 0]

        net_pnl = sum(pnls)
        win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)
        expectancy = net_pnl / total_trades if total_trades > 0 else 0

        # Séries gagnantes/perdantes
        best_streak, worst_streak = self._calc_streaks(pnls)

        # Durées
        durations = [t.duration_hours for t in closed_trades if t.duration_hours is not None]
        avg_dur = sum(durations) / len(durations) if durations else 0

        # Sharpe simplifié
        pnl_pcts = [t.pnl_pct for t in closed_trades if t.pnl_pct is not None]
        sharpe = self._calc_sharpe(pnl_pcts)

        # PnL %
        account = self.db.query(PaperAccount).get(account_id)
        initial = account.initial_capital if account and account.initial_capital > 0 else 10000
        pnl_pct = net_pnl / initial * 100

        # Verdict
        verdict = self._compute_verdict(win_rate, profit_factor, net_pnl, total_trades)

        return JournalPeriodSummary(
            date_from=dt_from.strftime("%Y-%m-%d"),
            date_to=dt_to.strftime("%Y-%m-%d"),
            total_ticks=total_ticks,
            total_trades=total_trades,
            trades_per_day=round(total_trades / days_span, 2),
            trades_per_hour_avg=round(total_trades / hours_span, 4),
            win_rate=round(win_rate, 2),
            pnl_realized=round(net_pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            expectancy=round(expectancy, 2),
            profit_factor=round(min(profit_factor, 999), 2),
            sharpe=sharpe,
            max_drawdown_pct=round(account.max_drawdown_pct, 2) if account else 0,
            best_streak=best_streak,
            worst_streak=worst_streak,
            avg_position_duration_hours=round(avg_dur, 2),
            verdict=verdict,
        )

    # ================================================================
    # AGRÉGATION JOURNALIÈRE
    # ================================================================

    def _compute_daily_summaries(
        self, account_id: int, dt_from: datetime, dt_to: datetime,
    ) -> list[JournalDaySummary]:
        """Calcule les résumés jour par jour."""
        # Récupérer tous les trades fermés
        closed_trades = (
            self.db.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account_id,
                PaperTrade.status != "open",
                PaperTrade.exit_ts >= dt_from,
                PaperTrade.exit_ts <= dt_to,
            )
            .all()
        )

        # Ticks par jour
        tick_counts = {}
        ticks = (
            self.db.query(TickActivityLog)
            .filter(
                TickActivityLog.account_id == account_id,
                TickActivityLog.timestamp >= dt_from,
                TickActivityLog.timestamp <= dt_to,
            )
            .all()
        )
        for t in ticks:
            day = t.timestamp.strftime("%Y-%m-%d") if t.timestamp else "unknown"
            tick_counts[day] = tick_counts.get(day, 0) + 1

        # Grouper les trades par jour de sortie
        trades_by_day: dict[str, list] = {}
        for t in closed_trades:
            if t.exit_ts:
                day = t.exit_ts.strftime("%Y-%m-%d")
                trades_by_day.setdefault(day, []).append(t)

        all_days = sorted(set(list(tick_counts.keys()) + list(trades_by_day.keys())))
        summaries = []

        for day in all_days:
            day_trades = trades_by_day.get(day, [])
            pnls = [t.pnl for t in day_trades if t.pnl is not None]
            n = len(day_trades)
            wins = len([p for p in pnls if p >= 0])
            net = sum(pnls)
            durations = [t.duration_hours for t in day_trades if t.duration_hours is not None]

            account = self.db.query(PaperAccount).get(account_id)
            initial = account.initial_capital if account and account.initial_capital > 0 else 10000

            summaries.append(JournalDaySummary(
                date=day,
                total_ticks=tick_counts.get(day, 0),
                total_trades=n,
                pnl_realized=round(net, 2),
                pnl_pct=round(net / initial * 100, 2) if initial > 0 else 0,
                win_rate=round(wins / n * 100, 2) if n > 0 else 0,
                best_trade_pnl=round(max(pnls), 2) if pnls else 0,
                worst_trade_pnl=round(min(pnls), 2) if pnls else 0,
                avg_position_duration_hours=round(sum(durations) / len(durations), 2) if durations else 0,
                verdict=self._day_verdict(round(wins / n * 100, 2) if n > 0 else 0, net, n),
            ))

        return summaries

    # ================================================================
    # STATISTIQUES D'ACTIVITÉ
    # ================================================================

    def _compute_activity_stats(
        self, account_id: int, dt_from: datetime, dt_to: datetime,
    ) -> JournalActivityStats:
        """Calcule les stats d'activité et fréquence."""
        ticks = (
            self.db.query(TickActivityLog)
            .filter(
                TickActivityLog.account_id == account_id,
                TickActivityLog.timestamp >= dt_from,
                TickActivityLog.timestamp <= dt_to,
            )
            .all()
        )

        total = len(ticks)
        if total == 0:
            return JournalActivityStats()

        counters = Counter(t.action_taken for t in ticks)
        opened = sum(v for k, v in counters.items() if k.startswith("opened_"))
        closed = sum(v for k, v in counters.items() if k.startswith("closed_"))
        signal_ticks = sum(1 for t in ticks if t.decision_score is not None and abs(t.decision_score) > 0)

        return JournalActivityStats(
            total_ticks=total,
            ticks_with_signal=signal_ticks,
            ticks_opened=opened,
            ticks_closed=closed,
            ticks_hold=counters.get("hold", 0),
            ticks_blocked_risk=counters.get("blocked", 0),
            ticks_ignored_signal=sum(1 for t in ticks if t.reason_no_trade in (
                "score_too_low", "confidence_too_low", "scenario_weak", "decision_wait"
            )),
            ticks_position_held=sum(1 for t in ticks if t.had_open_position and t.action_taken == "hold"),
            ticks_exit_tp=counters.get("closed_tp", 0),
            ticks_exit_sl=counters.get("closed_sl", 0),
            ticks_exit_signal=counters.get("closed_signal", 0),
            ticks_exit_expired=counters.get("closed_expired", 0),
            tick_to_trade_ratio=round(opened / total * 100, 2) if total > 0 else 0,
        )

    # ================================================================
    # RAISONS DE NON-TRADE
    # ================================================================

    def _compute_non_trade_reasons(
        self, account_id: int, dt_from: datetime, dt_to: datetime,
    ) -> JournalNonTradeReasons:
        """Agrège les raisons de non-trade."""
        ticks = (
            self.db.query(TickActivityLog)
            .filter(
                TickActivityLog.account_id == account_id,
                TickActivityLog.timestamp >= dt_from,
                TickActivityLog.timestamp <= dt_to,
                TickActivityLog.reason_no_trade.isnot(None),
            )
            .all()
        )

        total = len(ticks)
        if total == 0:
            return JournalNonTradeReasons()

        counter = Counter(t.reason_no_trade for t in ticks)
        items = []
        for reason, count in counter.most_common():
            items.append(NonTradeReasonItem(
                reason=reason,
                label=REASON_LABELS.get(reason, reason),
                count=count,
                pct=round(count / total * 100, 1),
            ))

        return JournalNonTradeReasons(
            total_non_trade_ticks=total,
            reasons=items,
        )

    # ================================================================
    # QUALIFICATION DU STYLE DE TRADING
    # ================================================================

    def get_trading_style(self, account_id: Optional[int] = None) -> TradingStyleResult:
        """Qualifie le style de trading selon les durées de position."""
        if account_id is None:
            account = self.db.query(PaperAccount).first()
            if account is None:
                return TradingStyleResult()
            account_id = account.id

        closed_trades = (
            self.db.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account_id,
                PaperTrade.status != "open",
                PaperTrade.duration_hours.isnot(None),
            )
            .all()
        )

        if not closed_trades:
            return TradingStyleResult()

        durations_min = [t.duration_hours * 60 for t in closed_trades]
        total = len(durations_min)

        # Buckets
        buckets_def = [
            ("< 1 min", 0, 1),
            ("1–5 min", 1, 5),
            ("5–15 min", 5, 15),
            ("15–60 min", 15, 60),
            ("1h+", 60, float("inf")),
        ]
        buckets = []
        for label, lo, hi in buckets_def:
            count = sum(1 for d in durations_min if lo <= d < hi)
            buckets.append(DurationBucket(
                label=label,
                count=count,
                pct=round(count / total * 100, 1) if total > 0 else 0,
            ))

        avg_dur = sum(durations_min) / total if total > 0 else 0
        sorted_d = sorted(durations_min)
        median_dur = sorted_d[total // 2] if total > 0 else 0

        # Qualification
        if median_dur < 5:
            style = "scalping-like"
        elif median_dur < 60:
            style = "intraday"
        else:
            style = "swing_intraday"

        # Stats micro-temporelles depuis tick_activity_log
        exits_fast = sum(1 for d in durations_min if d < 5)
        exits_slow = sum(1 for d in durations_min if d >= 60)

        return TradingStyleResult(
            total_closed_trades=total,
            duration_distribution=buckets,
            dominant_style=style,
            avg_duration_minutes=round(avg_dur, 1),
            median_duration_minutes=round(median_dur, 1),
            exits_fast_count=exits_fast,
            exits_slow_count=exits_slow,
        )

    # ================================================================
    # HELPERS
    # ================================================================

    def _parse_date_range(
        self, date_from: Optional[str], date_to: Optional[str],
    ) -> tuple[datetime, datetime]:
        """Parse les dates ou utilise des defaults."""
        now = datetime.now(timezone.utc)
        if date_to:
            try:
                dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59, tzinfo=timezone.utc
                )
            except ValueError:
                dt_to = now
        else:
            dt_to = now

        if date_from:
            try:
                dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(
                    hour=0, minute=0, second=0, tzinfo=timezone.utc
                )
            except ValueError:
                dt_from = dt_to - timedelta(days=7)
        else:
            dt_from = dt_to - timedelta(days=7)

        return dt_from, dt_to

    @staticmethod
    def _calc_streaks(pnls: list[float]) -> tuple[int, int]:
        """Calcule la plus longue série gagnante et perdante."""
        best = worst = current_win = current_loss = 0
        for p in pnls:
            if p >= 0:
                current_win += 1
                current_loss = 0
                best = max(best, current_win)
            else:
                current_loss += 1
                current_win = 0
                worst = max(worst, current_loss)
        return best, worst

    @staticmethod
    def _calc_sharpe(pnl_pcts: list[float]) -> Optional[float]:
        """Sharpe ratio simplifié."""
        if len(pnl_pcts) < 2:
            return None
        mean = sum(pnl_pcts) / len(pnl_pcts)
        variance = sum((p - mean) ** 2 for p in pnl_pcts) / (len(pnl_pcts) - 1)
        std = math.sqrt(variance) if variance > 0 else 0
        if std == 0:
            return None
        sharpe = (mean / std) * math.sqrt(min(len(pnl_pcts), 250))
        return round(sharpe, 2)

    @staticmethod
    def _compute_verdict(win_rate: float, pf: float, pnl: float, trades: int) -> str:
        """Verdict synthétique."""
        if trades < 3:
            return "N/A — Pas assez de trades"
        if pnl > 0 and win_rate >= 55 and pf >= 1.5:
            return "prometteur"
        if pnl > 0 and win_rate >= 45:
            return "mitigé"
        if pnl <= 0 and win_rate >= 40:
            return "faible"
        return "critique"

    @staticmethod
    def _day_verdict(win_rate: float, pnl: float, trades: int) -> str:
        if trades == 0:
            return "inactif"
        if pnl > 0 and win_rate >= 60:
            return "bon"
        if pnl > 0:
            return "correct"
        if pnl == 0:
            return "neutre"
        return "mauvais"

