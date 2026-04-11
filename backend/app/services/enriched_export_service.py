"""
EnrichedExportService — Export enrichi tick-par-tick avec corrélation BTC.

Assemble minute par minute :
- Prix BTC (via TickActivityLog.btc_price)
- Décisions moteur (action, score, confidence, raison de non-trade)
- Positions ouvertes/fermées (via PaperTrade)
- PnL latent / réalisé
- Analyse des gates de blocage (ventilation des refus par gate)
- Détection des tendances ratées (BTC bouge, moteur bloqué)

v2.0.4
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.tick_activity_log import TickActivityLog
from app.models.paper_account import PaperAccount, PaperTrade
from app.schemas.enriched_export import (
    EnrichedTickRow,
    GateBlockDistribution,
    MissedTrendAnalysis,
    EnrichedExportSummary,
    EnrichedExportResponse,
)

logger = logging.getLogger(__name__)

# Seuil minimum de mouvement BTC pour qualifier une "tendance ratée"
DEFAULT_MISSED_TREND_THRESHOLD_PCT = 0.15
# Nombre minimum de ticks consécutifs "hold" pour qualifier une tendance ratée
MIN_CONSECUTIVE_HOLD_FOR_TREND = 3


class EnrichedExportService:
    """
    Service d'export enrichi : chaque tick avec contexte complet.

    Usage :
        service = EnrichedExportService(db)
        result = service.build_export(profile_type="scalping")
    """

    def __init__(self, db: Session):
        self.db = db

    def build_export(
        self,
        profile_type: Optional[str] = None,
        limit: int = 5000,
        missed_threshold_pct: float = DEFAULT_MISSED_TREND_THRESHOLD_PCT,
    ) -> EnrichedExportResponse:
        """
        Construit l'export enrichi complet.

        Args:
            profile_type: Filtrer par profil (None = tous)
            limit: Nombre max de ticks à retourner
            missed_threshold_pct: Seuil pour qualifier une tendance ratée
        """
        account = self.db.query(PaperAccount).first()
        if account is None:
            return EnrichedExportResponse()

        # Charger les ticks
        query = (
            self.db.query(TickActivityLog)
            .filter(TickActivityLog.account_id == account.id)
        )
        if profile_type:
            query = query.filter(TickActivityLog.profile_type == profile_type)

        ticks = (
            query.order_by(TickActivityLog.timestamp.asc())
            .limit(limit)
            .all()
        )

        if not ticks:
            return EnrichedExportResponse()

        # Charger les trades fermés pour enrichissement
        trades = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.account_id == account.id)
            .order_by(PaperTrade.entry_ts.asc())
            .all()
        )

        # Index trades par ID pour enrichissement rapide
        trades_by_id = {t.id: t for t in trades}

        # Index trades par timestamp d'entrée et de sortie
        entry_events = {}  # ts → trade
        exit_events = {}   # ts → trade
        for t in trades:
            if t.entry_ts:
                entry_events[t.id] = t
            if t.exit_ts and t.status != "open":
                exit_events[t.id] = t

        # Construire les lignes enrichies
        rows = []
        prev_price = None

        for tick in ticks:
            btc_var = None
            if tick.btc_price and prev_price and prev_price > 0:
                btc_var = round(
                    (tick.btc_price - prev_price) / prev_price * 100, 4
                )

            # Déterminer si ce tick est un événement d'entrée ou de sortie
            is_entry = tick.action_taken in (
                "opened_long", "opened_short",
            )
            is_exit = tick.action_taken in (
                "closed_tp", "closed_sl", "closed_signal",
                "closed_expired", "closed_manual", "closed_stale",
                "closed_trailing_stop", "closed_momentum_fade",
            )

            # Enrichir avec les données du trade associé
            trade_data = {}
            if tick.trade_id and tick.trade_id in trades_by_id:
                t = trades_by_id[tick.trade_id]
                trade_data = {
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price if is_exit else None,
                    "exit_type": t.status if is_exit else None,
                    "trade_pnl": t.pnl if is_exit else None,
                    "trade_pnl_pct": t.pnl_pct if is_exit else None,
                    "trade_direction": t.direction,
                }

            row = EnrichedTickRow(
                timestamp=tick.timestamp,
                btc_price=tick.btc_price,
                btc_variation_pct=btc_var,
                slot=None,  # Pas de colonne slot sur TickActivityLog
                profile_type=tick.profile_type,
                decision_action=tick.decision_action,
                decision_score=tick.decision_score,
                decision_confidence=tick.decision_confidence,
                action_taken=tick.action_taken,
                reason_no_trade=tick.reason_no_trade,
                reason_detail=tick.reason_detail,
                rejection_category=tick.rejection_category,
                had_open_position=bool(tick.had_open_position),
                unrealized_pnl=tick.unrealized_pnl,
                is_entry=is_entry,
                is_exit=is_exit,
                market_quality_score=tick.market_quality_score,
                micro_trend_score=tick.micro_trend_score,
                volume_ratio=tick.volume_ratio,
                **trade_data,
            )
            rows.append(row)
            prev_price = tick.btc_price

        # Construire le résumé
        summary = self._build_summary(
            ticks, rows, missed_threshold_pct
        )

        return EnrichedExportResponse(
            ticks=rows,
            summary=summary,
        )

    def _build_summary(
        self,
        ticks: list[TickActivityLog],
        rows: list[EnrichedTickRow],
        missed_threshold_pct: float,
    ) -> EnrichedExportSummary:
        """Construit le résumé de l'export enrichi."""
        total_entries = sum(1 for r in rows if r.is_entry)
        total_exits = sum(1 for r in rows if r.is_exit)
        total_holds = sum(
            1 for r in rows
            if r.action_taken == "hold" and r.reason_no_trade
        )

        # Gate blocking distribution
        gate_dist = self._compute_gate_distribution(ticks, rows)

        # Dominant gate
        dominant_gate = None
        dominant_gate_pct = None
        if gate_dist:
            top = max(gate_dist, key=lambda g: g.block_count)
            dominant_gate = top.gate_name
            dominant_gate_pct = top.block_pct

        # Missed trends
        missed_trends = self._detect_missed_trends(
            rows, missed_threshold_pct
        )
        total_missed = sum(abs(m.move_pct) for m in missed_trends)

        # Période et mouvement BTC total
        period_start = rows[0].timestamp if rows else None
        period_end = rows[-1].timestamp if rows else None
        btc_total = None
        if rows and rows[0].btc_price and rows[-1].btc_price:
            btc_total = round(
                (rows[-1].btc_price - rows[0].btc_price)
                / rows[0].btc_price * 100,
                4,
            )

        return EnrichedExportSummary(
            total_ticks=len(rows),
            total_entries=total_entries,
            total_exits=total_exits,
            total_holds=total_holds,
            gate_distribution=gate_dist,
            dominant_gate=dominant_gate,
            dominant_gate_pct=dominant_gate_pct,
            missed_trends=missed_trends,
            total_missed_move_pct=round(total_missed, 4),
            period_start=period_start,
            period_end=period_end,
            btc_move_total_pct=btc_total,
        )

    def _compute_gate_distribution(
        self,
        ticks: list[TickActivityLog],
        rows: list[EnrichedTickRow],
    ) -> list[GateBlockDistribution]:
        """Calcule la ventilation des refus par gate."""
        # Compter par raison de non-trade
        reason_counts: dict[str, list[TickActivityLog]] = defaultdict(list)
        for tick in ticks:
            if tick.reason_no_trade:
                reason_counts[tick.reason_no_trade].append(tick)

        total_blocked = sum(len(v) for v in reason_counts.values())
        if total_blocked == 0:
            return []

        dist = []
        for reason, blocked_ticks in reason_counts.items():
            count = len(blocked_ticks)
            avg_score = None
            scores = [
                t.decision_score for t in blocked_ticks
                if t.decision_score is not None
            ]
            if scores:
                avg_score = round(sum(scores) / len(scores), 1)

            # Compter les mouvements favorables ratés après chaque bloc
            # On regarde si le BTC a bougé > missed_threshold dans les ticks suivants
            favorable_count = 0
            favorable_moves = []
            for i, tick in enumerate(blocked_ticks):
                # Chercher le tick suivant pour mesurer le mouvement
                tick_idx = next(
                    (j for j, r in enumerate(rows)
                     if r.timestamp == tick.timestamp),
                    None,
                )
                if tick_idx is not None and tick_idx + 3 < len(rows):
                    future = rows[tick_idx + 3]
                    if tick.btc_price and future.btc_price and tick.btc_price > 0:
                        move = (future.btc_price - tick.btc_price) / tick.btc_price * 100
                        if move > 0.15:  # mouvement haussier raté
                            favorable_count += 1
                            favorable_moves.append(move)

            favorable_avg = (
                round(sum(favorable_moves) / len(favorable_moves), 4)
                if favorable_moves else None
            )

            dist.append(GateBlockDistribution(
                gate_name=reason,
                block_count=count,
                block_pct=round(count / total_blocked * 100, 1),
                avg_score_when_blocked=avg_score,
                favorable_moves_missed=favorable_count,
                favorable_move_avg_pct=favorable_avg,
            ))

        return sorted(dist, key=lambda g: g.block_count, reverse=True)

    def _detect_missed_trends(
        self,
        rows: list[EnrichedTickRow],
        threshold_pct: float,
    ) -> list[MissedTrendAnalysis]:
        """
        Détecte les tendances BTC significatives pendant lesquelles le moteur
        était bloqué (aucun trade ouvert, action=hold).

        Algorithme :
        1. Identifier les séquences de ticks "hold" consécutifs sans position ouverte
        2. Calculer le mouvement BTC total de chaque séquence
        3. Garder celles dont le mouvement abs > threshold_pct
        """
        missed = []
        i = 0
        while i < len(rows):
            # Chercher le début d'une séquence de "hold" sans position
            if (
                rows[i].action_taken == "hold"
                and not rows[i].had_open_position
                and rows[i].reason_no_trade
            ):
                # Début de séquence
                seq_start = i
                reasons_in_seq: dict[str, int] = defaultdict(int)
                scores_in_seq = []

                while (
                    i < len(rows)
                    and rows[i].action_taken == "hold"
                    and not rows[i].had_open_position
                ):
                    if rows[i].reason_no_trade:
                        reasons_in_seq[rows[i].reason_no_trade] += 1
                    if rows[i].decision_score is not None:
                        scores_in_seq.append(rows[i].decision_score)
                    i += 1

                seq_end = i - 1
                seq_len = seq_end - seq_start + 1

                if seq_len < MIN_CONSECUTIVE_HOLD_FOR_TREND:
                    continue

                # Calculer le mouvement BTC
                start_price = rows[seq_start].btc_price
                end_price = rows[seq_end].btc_price
                if not start_price or not end_price or start_price <= 0:
                    continue

                move_pct = (end_price - start_price) / start_price * 100

                if abs(move_pct) >= threshold_pct:
                    # Gate dominant dans cette séquence
                    dominant = (
                        max(reasons_in_seq, key=reasons_in_seq.get)
                        if reasons_in_seq else None
                    )
                    avg_score = (
                        round(sum(scores_in_seq) / len(scores_in_seq), 1)
                        if scores_in_seq else None
                    )

                    dur_min = 0.0
                    if rows[seq_end].timestamp and rows[seq_start].timestamp:
                        dur_min = (
                            rows[seq_end].timestamp - rows[seq_start].timestamp
                        ).total_seconds() / 60

                    missed.append(MissedTrendAnalysis(
                        start_ts=rows[seq_start].timestamp,
                        end_ts=rows[seq_end].timestamp,
                        start_price=start_price,
                        end_price=end_price,
                        move_pct=round(move_pct, 4),
                        direction="up" if move_pct > 0 else "down",
                        duration_minutes=round(dur_min, 1),
                        dominant_blocking_gate=dominant,
                        ticks_during_trend=seq_len,
                        avg_score_during_trend=avg_score,
                    ))
            else:
                i += 1

        return missed

