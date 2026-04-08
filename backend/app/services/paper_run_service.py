"""
PaperRunService — Gestion des campagnes de validation paper trading.

Permet de :
- Démarrer une campagne (snapshot des paramètres)
- Arrêter une campagne
- Calculer les métriques d'un run (brut + net)
- Comparer deux runs (avant/après)

v1.9.0
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paper_run import PaperRun
from app.models.paper_account import PaperTrade, PaperAccount
from app.services.trading_profile_service import PROFILE_PRESETS
from app.schemas.paper_run import (
    PaperRunResponse,
    RunMetricsDetail,
    PaperRunMetrics,
    RunComparison,
)

logger = logging.getLogger(__name__)


class PaperRunService:
    """Service de gestion des campagnes de validation."""

    def __init__(self, db: Session):
        self.db = db

    def start_run(self, name: str, profile_type: str = "scalping") -> PaperRun:
        """Démarre une nouvelle campagne de validation."""
        # Snapshot des paramètres du profil
        params = PROFILE_PRESETS.get(profile_type)
        config_json = json.dumps(params.model_dump(), default=str) if params else "{}"

        run = PaperRun(
            name=name,
            profile_type=profile_type,
            status="running",
            config_snapshot=config_json,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        logger.info(f"📋 Run démarré : {run.name} (profil={profile_type})")
        return run

    def end_run(self, run_id: int) -> Optional[PaperRun]:
        """Termine une campagne de validation."""
        run = self.db.query(PaperRun).filter(PaperRun.id == run_id).first()
        if run is None:
            return None
        run.status = "completed"
        run.ended_at = datetime.now(timezone.utc)

        # Compter les trades dans la période du run
        account = self.db.query(PaperAccount).first()
        if account:
            trades = self._get_run_trades(run, account.id)
            run.total_trades = len(trades)

        self.db.commit()
        self.db.refresh(run)
        logger.info(f"✅ Run terminé : {run.name} ({run.total_trades} trades)")
        return run

    def get_runs(self) -> list[PaperRun]:
        """Liste toutes les campagnes."""
        return self.db.query(PaperRun).order_by(PaperRun.started_at.desc()).all()

    def get_run_metrics(self, run_id: int) -> Optional[PaperRunMetrics]:
        """Calcule les métriques d'un run."""
        run = self.db.query(PaperRun).filter(PaperRun.id == run_id).first()
        if run is None:
            return None

        account = self.db.query(PaperAccount).first()
        if account is None:
            return PaperRunMetrics(
                run=PaperRunResponse.model_validate(run),
                metrics=RunMetricsDetail(),
            )

        trades = self._get_run_trades(run, account.id)
        metrics = self._compute_metrics(trades)

        return PaperRunMetrics(
            run=PaperRunResponse.model_validate(run),
            metrics=metrics,
        )

    def compare_runs(self, before_id: int, after_id: int) -> Optional[RunComparison]:
        """Compare deux runs."""
        before_metrics = self.get_run_metrics(before_id)
        after_metrics = self.get_run_metrics(after_id)
        if before_metrics is None or after_metrics is None:
            return None

        b = before_metrics.metrics
        a = after_metrics.metrics

        delta_wr = a.win_rate - b.win_rate
        delta_exp_brut = a.expectancy_brut - b.expectancy_brut
        delta_exp_net = a.expectancy_net - b.expectancy_net
        delta_pf_net = a.profit_factor_net - b.profit_factor_net
        delta_delay = a.avg_delay_between_trades_min - b.avg_delay_between_trades_min
        delta_short = a.short_count - b.short_count

        # Verdict
        if delta_exp_net > 0.5 and delta_wr > 2:
            verdict = "amélioration_réelle"
            detail = f"Expectancy nette +{delta_exp_net:.2f}, win rate +{delta_wr:.1f}%"
        elif delta_exp_net > 0 and delta_wr > 0:
            verdict = "amélioration_cosmétique"
            detail = "Amélioration marginale — pas encore convaincante"
        elif delta_exp_net < -0.5 or delta_wr < -5:
            verdict = "régression"
            detail = f"Expectancy nette {delta_exp_net:.2f}, win rate {delta_wr:.1f}%"
        else:
            verdict = "pas_d_amélioration"
            detail = "Pas de changement significatif"

        return RunComparison(
            before=b,
            after=a,
            delta_win_rate=round(delta_wr, 2),
            delta_expectancy_brut=round(delta_exp_brut, 2),
            delta_expectancy_net=round(delta_exp_net, 2),
            delta_profit_factor_net=round(delta_pf_net, 2),
            delta_avg_delay_min=round(delta_delay, 1),
            delta_short_count=delta_short,
            verdict=verdict,
            verdict_detail=detail,
        )

    def _get_run_trades(self, run: PaperRun, account_id: int) -> list:
        """Récupère les trades fermés pendant la période du run."""
        query = (
            self.db.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account_id,
                PaperTrade.status != "open",
                PaperTrade.entry_ts >= run.started_at,
            )
        )
        if run.ended_at:
            query = query.filter(PaperTrade.exit_ts <= run.ended_at)
        # Filtrer par profil du run si possible
        if run.profile_type:
            query = query.filter(
                (PaperTrade.profile_type == run.profile_type)
                | (PaperTrade.slot == run.profile_type)
            )
        return query.order_by(PaperTrade.exit_ts.asc()).all()

    def _compute_metrics(self, trades: list) -> RunMetricsDetail:
        """Calcule les métriques brut + net d'un ensemble de trades."""
        if not trades:
            return RunMetricsDetail()

        total = len(trades)
        pnls = [t.pnl for t in trades if t.pnl is not None]
        wins = [p for p in pnls if p >= 0]
        losses = [p for p in pnls if p < 0]

        win_rate = len(wins) / total * 100 if total > 0 else 0
        pnl_brut = sum(pnls)
        avg_pnl = pnl_brut / total if total > 0 else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        pf_brut = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)

        # Expectancy brute
        expectancy_brut = avg_pnl

        # Coûts estimés (TradingCostModel)
        total_costs = 0.0
        try:
            from app.services.trading_cost_service import get_cost_model
            cost_model = get_cost_model()
            for t in trades:
                size = (t.position_size_usd or 0) * (t.leverage or 1.0)
                cost = cost_model.round_trip_cost_usd(size)
                total_costs += cost
        except Exception:
            # Si TradingCostModel pas dispo, estimer 0.1% par trade
            for t in trades:
                size = (t.position_size_usd or 0) * (t.leverage or 1.0)
                total_costs += size * 0.001

        pnl_net = pnl_brut - total_costs
        avg_pnl_net = pnl_net / total if total > 0 else 0
        expectancy_net = avg_pnl_net

        # Profit factor net
        net_wins = sum(max(0, p - total_costs / total) for p in wins) if wins else 0
        net_losses = abs(sum(min(0, p - total_costs / total) for p in losses)) if losses else 0
        pf_net = net_wins / net_losses if net_losses > 0 else (999.0 if net_wins > 0 else 0)

        # Drawdown brut (max peak-to-trough)
        max_dd = 0.0
        peak = 0.0
        cumul = 0.0
        for p in pnls:
            cumul += p
            if cumul > peak:
                peak = cumul
            dd = peak - cumul
            if dd > max_dd:
                max_dd = dd

        # Par type de sortie
        status_counts = {}
        for t in trades:
            status_counts[t.status] = status_counts.get(t.status, 0) + 1

        # Par direction
        longs = [t for t in trades if t.direction == "long"]
        shorts = [t for t in trades if t.direction == "short"]
        long_pnls = [t.pnl for t in longs if t.pnl is not None]
        short_pnls = [t.pnl for t in shorts if t.pnl is not None]

        long_wr = sum(1 for p in long_pnls if p >= 0) / len(longs) * 100 if longs else 0
        short_wr = sum(1 for p in short_pnls if p >= 0) / len(shorts) * 100 if shorts else 0

        # Timing
        durations = [t.duration_hours * 60 for t in trades if t.duration_hours is not None]
        avg_dur = sum(durations) / len(durations) if durations else 0

        # Délais entre trades
        delays = []
        sorted_trades = sorted(
            [t for t in trades if t.entry_ts and t.exit_ts],
            key=lambda t: t.entry_ts,
        )
        for i in range(1, len(sorted_trades)):
            prev_exit = sorted_trades[i - 1].exit_ts
            curr_entry = sorted_trades[i].entry_ts
            if prev_exit and curr_entry:
                from datetime import timezone as _tz
                if prev_exit.tzinfo is None:
                    prev_exit = prev_exit.replace(tzinfo=_tz.utc)
                if curr_entry.tzinfo is None:
                    curr_entry = curr_entry.replace(tzinfo=_tz.utc)
                delay = (curr_entry - prev_exit).total_seconds() / 60
                if delay >= 0:
                    delays.append(delay)

        avg_delay = sum(delays) / len(delays) if delays else 0
        sorted_delays = sorted(delays)
        median_delay = sorted_delays[len(sorted_delays) // 2] if sorted_delays else 0

        return RunMetricsDetail(
            total_trades=total,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=round(win_rate, 2),
            pnl_brut=round(pnl_brut, 2),
            avg_trade_pnl_brut=round(avg_pnl, 2),
            avg_win_brut=round(avg_win, 2),
            avg_loss_brut=round(avg_loss, 2),
            expectancy_brut=round(expectancy_brut, 2),
            profit_factor_brut=round(pf_brut, 2) if pf_brut != 999.0 else 999.0,
            max_drawdown_brut=round(max_dd, 2),
            total_costs=round(total_costs, 2),
            pnl_net=round(pnl_net, 2),
            avg_trade_pnl_net=round(avg_pnl_net, 2),
            expectancy_net=round(expectancy_net, 2),
            profit_factor_net=round(pf_net, 2) if pf_net != 999.0 else 999.0,
            trailing_stop_exits=status_counts.get("closed_trailing_stop", 0),
            stale_exits=status_counts.get("closed_stale", 0),
            momentum_fade_exits=status_counts.get("closed_momentum_fade", 0),
            signal_exits=status_counts.get("closed_signal", 0),
            tp_exits=status_counts.get("closed_tp", 0),
            sl_exits=status_counts.get("closed_sl", 0),
            long_count=len(longs),
            short_count=len(shorts),
            long_win_rate=round(long_wr, 2),
            short_win_rate=round(short_wr, 2),
            long_pnl=round(sum(long_pnls), 2),
            short_pnl=round(sum(short_pnls), 2),
            avg_duration_minutes=round(avg_dur, 1),
            avg_delay_between_trades_min=round(avg_delay, 1),
            median_delay_between_trades_min=round(median_delay, 1),
        )

