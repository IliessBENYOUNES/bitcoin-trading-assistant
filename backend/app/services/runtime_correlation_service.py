"""
RuntimeCorrelationService — Corrélation trades vs mouvement BTC réel.

Analyse chaque trade fermé en corrélation avec les bougies BTC pour :
1. Identifier l'efficacité de capture (% du mouvement BTC capté)
2. Détecter les mouvements BTC ratés (aucun trade ouvert)
3. Identifier les sorties stale prématurées (BTC favorable après exit)
4. Calculer le contexte d'entrée (BTC montait/descendait/flat)

v2.0.2
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.paper_account import PaperAccount, PaperTrade
from app.models.candle import Candle
from app.schemas.runtime_correlation import (
    BtcContext,
    TradeCorrelation,
    MissedMovement,
    CorrelationSummary,
    RuntimeCorrelationResponse,
)

logger = logging.getLogger(__name__)

# Seuil de mouvement significatif pour les "missed movements"
DEFAULT_MISSED_THRESHOLD_PCT = 0.15


class RuntimeCorrelationService:
    """
    Service de corrélation runtime : trades vs prix BTC réel.

    Usage :
        service = RuntimeCorrelationService(db)
        result = service.build_correlation()
    """

    def __init__(self, db: Session):
        self.db = db

    def build_correlation(
        self,
        symbol: str = "BTC/USD",
        missed_threshold_pct: float = DEFAULT_MISSED_THRESHOLD_PCT,
    ) -> RuntimeCorrelationResponse:
        """
        Construit l'analyse de corrélation complète.

        Charge tous les trades fermés et les bougies BTC correspondantes,
        puis corrèle chaque trade avec le mouvement de marché.
        """
        account = self.db.query(PaperAccount).first()
        if account is None:
            return RuntimeCorrelationResponse()

        closed_trades = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.account_id == account.id, PaperTrade.status != "open")
            .order_by(PaperTrade.entry_ts.asc())
            .all()
        )

        if not closed_trades:
            return RuntimeCorrelationResponse()

        # Déterminer la plage temporelle des trades
        first_ts = closed_trades[0].entry_ts
        last_ts = closed_trades[-1].exit_ts or closed_trades[-1].entry_ts
        # Élargir la fenêtre de ±4h pour le contexte
        window_start = first_ts - timedelta(hours=4)
        window_end = last_ts + timedelta(hours=4)

        # Charger les bougies en batch (performance)
        candles, tf_used = self._load_candles_batch(symbol, window_start, window_end)

        if not candles:
            # Pas de bougies : on peut quand même retourner les trades sans contexte BTC
            trades_out = [self._trade_to_correlation(t, [], tf_used) for t in closed_trades]
            return RuntimeCorrelationResponse(
                trades=trades_out,
                summary=CorrelationSummary(
                    total_trades=len(closed_trades),
                    candle_timeframe_used=tf_used,
                ),
            )

        # Construire les corrélations par trade
        trade_correlations = []
        for t in closed_trades:
            tc = self._trade_to_correlation(t, candles, tf_used)
            trade_correlations.append(tc)

        # Détecter les mouvements ratés
        missed = self._detect_missed_movements(
            closed_trades, candles, missed_threshold_pct
        )

        # Construire le résumé
        summary = self._build_summary(
            trade_correlations, candles, missed, tf_used
        )

        return RuntimeCorrelationResponse(
            trades=trade_correlations,
            missed_movements=missed,
            summary=summary,
        )

    # ================================================================
    # CHARGEMENT DES BOUGIES
    # ================================================================

    def _load_candles_batch(
        self, symbol: str, start: datetime, end: datetime
    ) -> tuple[list[Candle], Optional[str]]:
        """
        Charge les bougies en batch. Essaie 1h d'abord, puis 4h en fallback.

        Retourne (candles, timeframe_used).
        """
        for tf in ("1h", "4h"):
            candles = (
                self.db.query(Candle)
                .filter(
                    Candle.symbol == symbol,
                    Candle.timeframe == tf,
                    Candle.timestamp >= start,
                    Candle.timestamp <= end,
                )
                .order_by(Candle.timestamp.asc())
                .all()
            )
            if candles:
                logger.info(
                    f"Loaded {len(candles)} candles ({tf}) for correlation "
                    f"[{start} → {end}]"
                )
                return candles, tf

        return [], None

    # ================================================================
    # CORRÉLATION PAR TRADE
    # ================================================================

    def _trade_to_correlation(
        self, trade: PaperTrade, candles: list[Candle], tf_used: Optional[str]
    ) -> TradeCorrelation:
        """Construit la corrélation pour un trade donné."""
        entry_ts = trade.entry_ts
        exit_ts = trade.exit_ts or entry_ts
        dur_min = (trade.duration_hours or 0) * 60

        btc_ctx = BtcContext(
            price_at_entry=trade.entry_price,
            price_at_exit=trade.exit_price,
        )

        capture_eff = None
        verdict = ""

        if candles:
            # Trouver la bougie couvrant l'entrée
            entry_candle = self._find_nearest_candle(candles, entry_ts)
            if entry_candle:
                candle_move = (
                    (entry_candle.close_price - entry_candle.open_price)
                    / entry_candle.open_price * 100
                )
                if candle_move > 0.02:
                    btc_ctx.trend_at_entry = "up"
                elif candle_move < -0.02:
                    btc_ctx.trend_at_entry = "down"
                else:
                    btc_ctx.trend_at_entry = "flat"

            # BTC move pendant le trade
            if trade.entry_price and trade.exit_price:
                btc_move = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
                btc_ctx.btc_move_during_pct = round(btc_move, 4)

                # Capture efficiency
                if abs(btc_move) > 0.001:
                    trade_pnl_pct = trade.pnl_pct or 0
                    # Pour un long: capture = pnl_pct / btc_move (quand btc_move > 0)
                    # Pour un short: capture = pnl_pct / (-btc_move) (quand btc_move < 0)
                    if trade.direction == "long" and btc_move > 0:
                        capture_eff = min(100, abs(trade_pnl_pct / btc_move * 100))
                    elif trade.direction == "short" and btc_move < 0:
                        capture_eff = min(100, abs(trade_pnl_pct / btc_move * 100))
                    else:
                        # Le trade était dans le mauvais sens ou pas de gain
                        capture_eff = 0.0

            # BTC move après la sortie (1 bougie suivante)
            exit_candle = self._find_next_candle(candles, exit_ts)
            if exit_candle:
                after_move = (
                    (exit_candle.close_price - exit_candle.open_price)
                    / exit_candle.open_price * 100
                )
                btc_ctx.btc_move_after_exit_pct = round(after_move, 4)
                btc_ctx.price_after_exit = exit_candle.close_price

                # Détection de mouvement favorable manqué après stale exit
                if trade.status == "closed_stale":
                    is_favorable = (
                        (trade.direction == "long" and after_move > 0.1)
                        or (trade.direction == "short" and after_move < -0.1)
                    )
                    if is_favorable:
                        btc_ctx.missed_favorable_move = True
                        btc_ctx.missed_move_pct = round(abs(after_move), 4)

        # Verdict par trade
        if trade.status == "closed_stale" and btc_ctx.missed_favorable_move:
            verdict = f"🔴 Stale prématuré : BTC +{btc_ctx.missed_move_pct:.2f}% favorable après sortie"
        elif trade.status == "closed_trailing_stop" and (trade.pnl or 0) > 0:
            verdict = "🟢 Trailing stop capture un vrai mouvement"
        elif trade.status == "closed_stale" and (trade.pnl or 0) > 0:
            verdict = "🟡 Stale positif mais le trailing n'a pas eu le temps de s'activer"
        elif trade.status == "closed_stale" and (trade.pnl or 0) < 0:
            verdict = "🔴 Stale négatif : entrée sans impulsion suffisante"
        elif trade.status == "closed_sl":
            verdict = "🔴 Stop loss atteint"
        else:
            verdict = "—"

        return TradeCorrelation(
            trade_id=trade.id,
            slot=trade.slot,
            direction=trade.direction,
            status=trade.status,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            entry_ts=trade.entry_ts,
            exit_ts=trade.exit_ts,
            duration_minutes=round(dur_min, 1) if dur_min else None,
            decision_score=trade.decision_score,
            pnl=trade.pnl,
            pnl_pct=trade.pnl_pct,
            leverage=getattr(trade, "leverage", 1.0) or 1.0,
            btc_context=btc_ctx,
            capture_efficiency_pct=round(capture_eff, 1) if capture_eff is not None else None,
            verdict=verdict,
        )

    # ================================================================
    # DÉTECTION DES MOUVEMENTS RATÉS
    # ================================================================

    def _detect_missed_movements(
        self,
        trades: list[PaperTrade],
        candles: list[Candle],
        threshold_pct: float,
    ) -> list[MissedMovement]:
        """
        Détecte les mouvements BTC significatifs pendant les gaps entre trades.

        Un gap = période sans position ouverte entre deux trades consécutifs.
        """
        missed = []

        for i in range(len(trades) - 1):
            t_current = trades[i]
            t_next = trades[i + 1]

            current_exit = t_current.exit_ts
            next_entry = t_next.entry_ts

            if current_exit is None or next_entry is None:
                continue

            # Temps entre les trades
            gap = (next_entry - current_exit).total_seconds() / 60
            if gap < 1:
                continue  # pas de gap significatif

            # Bougies dans le gap
            gap_candles = [
                c for c in candles
                if c.timestamp >= current_exit and c.timestamp <= next_entry
            ]

            if not gap_candles:
                continue

            # Calculer le mouvement total dans le gap
            gap_open = gap_candles[0].open_price
            gap_close = gap_candles[-1].close_price
            gap_move_pct = (gap_close - gap_open) / gap_open * 100

            if abs(gap_move_pct) >= threshold_pct:
                missed.append(MissedMovement(
                    start_ts=current_exit,
                    end_ts=next_entry,
                    start_price=gap_open,
                    end_price=gap_close,
                    move_pct=round(gap_move_pct, 4),
                    direction="up" if gap_move_pct > 0 else "down",
                    duration_minutes=round(gap, 1),
                    nearest_trade_before_id=t_current.id,
                    nearest_trade_after_id=t_next.id,
                    gap_minutes=round(gap, 1),
                ))

        return missed

    # ================================================================
    # RÉSUMÉ
    # ================================================================

    def _build_summary(
        self,
        trades: list[TradeCorrelation],
        candles: list[Candle],
        missed: list[MissedMovement],
        tf_used: Optional[str],
    ) -> CorrelationSummary:
        """Construit le résumé de corrélation."""
        # Mouvement total disponible (somme des abs des mouvements par bougie)
        total_available = 0.0
        for c in candles:
            if c.open_price > 0:
                move = abs(c.close_price - c.open_price) / c.open_price * 100
                total_available += move

        # Mouvement capturé par les trades
        total_captured = 0.0
        for t in trades:
            if t.pnl_pct is not None:
                total_captured += abs(t.pnl_pct)

        capture_ratio = (
            round(total_captured / total_available * 100, 1)
            if total_available > 0 else 0
        )

        # Stale exits prématurés
        premature_stale = [
            t for t in trades
            if t.btc_context.missed_favorable_move
        ]
        premature_count = len(premature_stale)
        premature_avg_missed = (
            round(
                sum(t.btc_context.missed_move_pct or 0 for t in premature_stale)
                / premature_count,
                4,
            )
            if premature_count > 0
            else 0
        )

        # Entrées par contexte
        up_entries = sum(1 for t in trades if t.btc_context.trend_at_entry == "up")
        down_entries = sum(1 for t in trades if t.btc_context.trend_at_entry == "down")
        flat_entries = sum(1 for t in trades if t.btc_context.trend_at_entry == "flat")

        # Missed movements
        missed_total_pct = round(sum(abs(m.move_pct) for m in missed), 4)

        # Verdicts
        stale_verdict = self._stale_verdict(trades, premature_count)
        capture_verdict = self._capture_verdict(capture_ratio, total_available)
        timing_verdict = self._timing_verdict(up_entries, down_entries, flat_entries)

        return CorrelationSummary(
            total_trades=len(trades),
            total_candles_analyzed=len(candles),
            candle_timeframe_used=tf_used,
            total_btc_movement_available_pct=round(total_available, 4),
            total_btc_movement_captured_pct=round(total_captured, 4),
            capture_ratio_pct=capture_ratio,
            missed_movements_count=len(missed),
            missed_movements_total_pct=missed_total_pct,
            premature_stale_count=premature_count,
            premature_stale_avg_missed_pct=premature_avg_missed,
            entries_during_uptrend=up_entries,
            entries_during_downtrend=down_entries,
            entries_during_flat=flat_entries,
            stale_verdict=stale_verdict,
            capture_verdict=capture_verdict,
            timing_verdict=timing_verdict,
        )

    # ================================================================
    # VERDICTS
    # ================================================================

    @staticmethod
    def _stale_verdict(trades: list[TradeCorrelation], premature_count: int) -> str:
        stale_trades = [t for t in trades if t.status == "closed_stale"]
        stale_pct = len(stale_trades) / len(trades) * 100 if trades else 0
        if stale_pct > 80:
            return (
                f"🔴 STALE DOMINANT : {stale_pct:.0f}% des trades. "
                f"{premature_count} sorties prématurées (BTC favorable après exit). "
                f"Le moteur entre trop souvent et sort trop vite."
            )
        elif stale_pct > 50:
            return (
                f"🟡 Stale fréquent ({stale_pct:.0f}%). "
                f"{premature_count} sorties prématurées."
            )
        else:
            return f"🟢 Stale maîtrisé ({stale_pct:.0f}%)."

    @staticmethod
    def _capture_verdict(ratio: float, available: float) -> str:
        if ratio > 30:
            return f"🟢 Bonne capture ({ratio:.0f}% du mouvement BTC disponible)."
        elif ratio > 10:
            return (
                f"🟡 Capture modeste ({ratio:.0f}%). "
                f"Le moteur laisse échapper beaucoup de mouvement."
            )
        else:
            return (
                f"🔴 Capture très faible ({ratio:.0f}%). "
                f"Le moteur ne monétise presque pas le mouvement BTC disponible."
            )

    @staticmethod
    def _timing_verdict(up: int, down: int, flat: int) -> str:
        total = up + down + flat
        if total == 0:
            return "Pas de données de contexte d'entrée."
        up_pct = up / total * 100
        down_pct = down / total * 100
        if up_pct > 60:
            return (
                f"🟢 {up_pct:.0f}% des entrées pendant une hausse BTC. "
                f"Bon timing d'entrée."
            )
        elif down_pct > 60:
            return (
                f"🔴 {down_pct:.0f}% des entrées pendant une baisse BTC. "
                f"Le moteur entre à contre-tendance."
            )
        else:
            return f"🟡 Entrées mixtes ({up_pct:.0f}% hausse / {down_pct:.0f}% baisse)."

    # ================================================================
    # HELPERS
    # ================================================================

    @staticmethod
    def _find_nearest_candle(
        candles: list[Candle], ts: datetime
    ) -> Optional[Candle]:
        """Trouve la bougie la plus proche AVANT ou AU timestamp donné."""
        result = None
        for c in candles:
            if c.timestamp <= ts:
                result = c
            else:
                break
        return result

    @staticmethod
    def _find_next_candle(
        candles: list[Candle], ts: datetime
    ) -> Optional[Candle]:
        """Trouve la première bougie APRÈS le timestamp donné."""
        for c in candles:
            if c.timestamp > ts:
                return c
        return None

