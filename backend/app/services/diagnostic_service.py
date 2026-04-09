"""
Service de Diagnostic de Fréquence — Paper Trading.

Analyse les données du journal d'activité (TickActivityLog) et des trades
pour produire un diagnostic structuré expliquant pourquoi le bot trade peu.

Missions :
1. Hiérarchie des causes de non-trade
2. Analyse de la durée des positions
3. Comparaison simulée des profils
4. Analyse du risk engine comme frein
5. Détection d'opportunités manquées
6. Analyse levier
"""

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import Counter

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.tick_activity_log import TickActivityLog
from app.models.paper_account import PaperAccount, PaperTrade
from app.models.candle import Candle
from app.services.trading_profile_service import PROFILE_PRESETS
from app.services.journal_service import REASON_LABELS
from app.schemas.diagnostic import (
    DiagnosticResponse,
    NonTradeRankedReason,
    PositionDurationStats,
    ProfileComparisonRow,
    RiskBrakeAnalysis,
    CooldownDiagnostic,
    MissedOpportunitySummary,
    MissedOpportunityItem,
    LeverageAnalysisResponse,
)

logger = logging.getLogger(__name__)

# Catégorisation des raisons de non-trade
REASON_CATEGORIES = {
    "decision_wait": "signal",
    "score_too_low": "signal",
    "confidence_too_low": "signal",
    "scenario_weak": "signal",
    "sentiment_contradictory": "signal",
    "adx_too_low": "signal",
    "volume_insufficient": "signal",
    "risk_blocked": "risk",
    "daily_loss_protection": "risk",
    "kill_switch_active": "risk",
    "position_already_open": "structural",
    "cooldown_active": "frequency",
    "max_trades_reached": "frequency",
    "no_decision_available": "structural",
    "inactive": "structural",
    "no_price": "structural",
}


class DiagnosticService:
    """Service de diagnostic de la fréquence de trading."""

    def __init__(self, db: Session):
        self.db = db

    def get_diagnostic(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> DiagnosticResponse:
        """
        Diagnostic complet : pourquoi le bot trade peu.

        Retourne les causes classées, l'analyse de durée,
        la comparaison des profils, et l'analyse du risk engine.
        """
        account = self.db.query(PaperAccount).first()
        if account is None:
            return DiagnosticResponse(
                main_bottleneck="no_account",
                bottleneck_detail="Aucun compte paper trading trouvé.",
            )

        dt_from, dt_to = self._parse_dates(date_from, date_to)

        # Garantir que le diagnostic ne regarde pas avant la création du compte
        # Sinon, après un reset, des ticks orphelins de l'ancien compte
        # (avec position_already_open) peuvent polluer les résultats.
        account_created = account.created_at
        if account_created:
            if account_created.tzinfo is None:
                from datetime import timezone as _tz
                account_created = account_created.replace(tzinfo=_tz.utc)
            if account_created > dt_from:
                dt_from = account_created

        days_span = max(1, (dt_to - dt_from).total_seconds() / 86400)

        # 1. Récupérer tous les ticks de la période
        ticks = (
            self.db.query(TickActivityLog)
            .filter(
                TickActivityLog.account_id == account.id,
                TickActivityLog.timestamp >= dt_from,
                TickActivityLog.timestamp <= dt_to,
            )
            .all()
        )
        total_ticks = len(ticks)

        # 2. Trades fermés
        closed_trades = (
            self.db.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account.id,
                PaperTrade.status != "open",
                PaperTrade.exit_ts >= dt_from,
                PaperTrade.exit_ts <= dt_to,
            )
            .all()
        )
        total_trades = len(closed_trades)

        # 3. Top raisons de non-trade
        top_reasons = self._rank_non_trade_reasons(ticks)

        # 4. Durée des positions
        pos_duration = self._analyze_position_durations(closed_trades, ticks)

        # 5. Comparaison par profil (simulée)
        profile_comparison = self._compare_profiles(ticks, closed_trades, days_span)

        # 6. Risk engine comme frein
        risk_brake = self._analyze_risk_brake(ticks)

        # 7. Cooldown diagnostic
        cooldown_diag = self._analyze_cooldown(closed_trades, ticks, account)

        # 8. Bottleneck principal
        main_bottleneck, bottleneck_detail, recommendations = self._identify_bottleneck(
            top_reasons, pos_duration, risk_brake, total_ticks, total_trades
        )

        return DiagnosticResponse(
            total_ticks=total_ticks,
            total_trades=total_trades,
            tick_to_trade_pct=round(total_trades / total_ticks * 100, 2) if total_ticks > 0 else 0,
            avg_trades_per_day=round(total_trades / days_span, 2),
            analysis_days=round(days_span, 1),
            top_non_trade_reasons=top_reasons,
            position_duration=pos_duration,
            profile_comparison=profile_comparison,
            risk_brake=risk_brake,
            cooldown=cooldown_diag,
            main_bottleneck=main_bottleneck,
            bottleneck_detail=bottleneck_detail,
            recommendations=recommendations,
        )

    def _analyze_cooldown(self, trades: list, ticks: list, account) -> CooldownDiagnostic:
        """Analyse détaillée du cooldown entre trades."""
        profile_name = getattr(account, "active_profile", "conservative")
        profile_params = PROFILE_PRESETS.get(profile_name, PROFILE_PRESETS.get("conservative"))

        cooldown_configured = getattr(profile_params, "cooldown_minutes", 0) if profile_params else 0
        smart_enabled = getattr(profile_params, "smart_cooldown_enabled", False) if profile_params else False

        # Ticks bloqués par cooldown
        cooldown_ticks = [t for t in ticks if t.reason_no_trade == "cooldown_active"]
        total_nt = len([t for t in ticks if t.reason_no_trade]) or 1

        # Signaux perdus pendant cooldown (avaient un score exploitable)
        signals_lost = sum(
            1 for t in cooldown_ticks
            if t.decision_score is not None and abs(t.decision_score) > 15
            and t.decision_action in ("acheter", "vendre")
        )

        # Calculer les délais réels entre trades (exit_ts → entry_ts suivant)
        # Trier les trades par entry_ts
        sorted_trades = sorted(
            [t for t in trades if t.entry_ts and t.exit_ts],
            key=lambda t: t.entry_ts,
        )
        delays = []
        for i in range(1, len(sorted_trades)):
            prev_exit = sorted_trades[i - 1].exit_ts
            curr_entry = sorted_trades[i].entry_ts
            if prev_exit and curr_entry:
                if prev_exit.tzinfo is None:
                    from datetime import timezone as _tz
                    prev_exit = prev_exit.replace(tzinfo=_tz.utc)
                if curr_entry.tzinfo is None:
                    from datetime import timezone as _tz
                    curr_entry = curr_entry.replace(tzinfo=_tz.utc)
                delay_min = (curr_entry - prev_exit).total_seconds() / 60
                if delay_min >= 0:
                    delays.append(delay_min)

        if not delays:
            return CooldownDiagnostic(
                cooldown_configured_min=cooldown_configured,
                smart_cooldown_enabled=smart_enabled,
                ticks_blocked_by_cooldown=len(cooldown_ticks),
                pct_blocked_by_cooldown=round(len(cooldown_ticks) / total_nt * 100, 1),
                signals_lost_during_cooldown=signals_lost,
            )

        avg_delay = sum(delays) / len(delays)
        sorted_delays = sorted(delays)
        median_delay = sorted_delays[len(sorted_delays) // 2]

        # Distribution des délais
        under_2 = sum(1 for d in delays if d < 2)
        d_2_5 = sum(1 for d in delays if 2 <= d < 5)
        d_5_15 = sum(1 for d in delays if 5 <= d < 15)
        d_15_60 = sum(1 for d in delays if 15 <= d < 60)
        over_60 = sum(1 for d in delays if d >= 60)

        efficiency = (
            f"Cooldown configuré {cooldown_configured} min, délai réel moyen {avg_delay:.1f} min. "
            f"{len(cooldown_ticks)} ticks bloqués par cooldown dont {signals_lost} avec signal exploitable."
        )

        return CooldownDiagnostic(
            cooldown_configured_min=cooldown_configured,
            smart_cooldown_enabled=smart_enabled,
            avg_delay_between_trades_min=round(avg_delay, 1),
            median_delay_between_trades_min=round(median_delay, 1),
            min_delay_min=round(min(delays), 1),
            max_delay_min=round(max(delays), 1),
            ticks_blocked_by_cooldown=len(cooldown_ticks),
            pct_blocked_by_cooldown=round(len(cooldown_ticks) / total_nt * 100, 1),
            delay_under_2min=under_2,
            delay_2_to_5min=d_2_5,
            delay_5_to_15min=d_5_15,
            delay_15_to_60min=d_15_60,
            delay_over_60min=over_60,
            signals_lost_during_cooldown=signals_lost,
            cooldown_efficiency=efficiency,
        )

    def _rank_non_trade_reasons(self, ticks: list) -> list[NonTradeRankedReason]:
        """Classe les raisons de non-trade par fréquence décroissante."""
        non_trade_ticks = [t for t in ticks if t.reason_no_trade]
        if not non_trade_ticks:
            return []

        counter = Counter(t.reason_no_trade for t in non_trade_ticks)
        total = len(non_trade_ticks)
        ranked = []
        for rank, (reason, count) in enumerate(counter.most_common(), 1):
            ranked.append(NonTradeRankedReason(
                rank=rank,
                reason=reason,
                label=REASON_LABELS.get(reason, reason),
                count=count,
                pct=round(count / total * 100, 1),
                category=REASON_CATEGORIES.get(reason, "other"),
            ))
        return ranked

    def _analyze_position_durations(self, trades: list, ticks: list) -> PositionDurationStats:
        """Analyse la distribution des durées de position."""
        if not trades:
            ticks_blocked = sum(1 for t in ticks if t.reason_no_trade == "position_already_open")
            return PositionDurationStats(
                ticks_blocked_by_open_position=ticks_blocked,
                pct_ticks_blocked_by_position=round(ticks_blocked / len(ticks) * 100, 2) if ticks else 0,
            )

        durations = [t.duration_hours for t in trades if t.duration_hours is not None]
        if not durations:
            return PositionDurationStats(total_closed=len(trades))

        total = len(durations)
        sorted_d = sorted(durations)
        median = sorted_d[total // 2]

        ticks_blocked = sum(1 for t in ticks if t.reason_no_trade == "position_already_open")

        return PositionDurationStats(
            total_closed=total,
            avg_duration_hours=round(sum(durations) / total, 2),
            median_duration_hours=round(median, 2),
            min_duration_hours=round(min(durations), 2),
            max_duration_hours=round(max(durations), 2),
            pct_under_1h=round(sum(1 for d in durations if d < 1) / total * 100, 1),
            pct_1h_to_4h=round(sum(1 for d in durations if 1 <= d < 4) / total * 100, 1),
            pct_4h_to_24h=round(sum(1 for d in durations if 4 <= d < 24) / total * 100, 1),
            pct_over_24h=round(sum(1 for d in durations if d >= 24) / total * 100, 1),
            ticks_blocked_by_open_position=ticks_blocked,
            pct_ticks_blocked_by_position=round(ticks_blocked / len(ticks) * 100, 2) if ticks else 0,
        )

    def _compare_profiles(
        self, ticks: list, trades: list, days_span: float,
    ) -> list[ProfileComparisonRow]:
        """
        Compare les profils en utilisant les données réelles + simulation.

        Pour chaque profil, on simule combien de ticks non-trade auraient
        potentiellement passé les filtres de CE profil (basé sur le score du tick).
        """
        rows = []

        # Données réelles par profil
        trades_by_profile = {}
        for t in trades:
            p = t.profile_type or "conservative"
            # Normaliser auto→xxx en prenant le profil de base
            if p.startswith("auto"):
                p = "auto"
            trades_by_profile.setdefault(p, []).append(t)

        for profile_name, params in PROFILE_PRESETS.items():
            profile_trades = trades_by_profile.get(profile_name, [])
            n_trades = len(profile_trades)
            pnls = [t.pnl for t in profile_trades if t.pnl is not None]
            wins = [p for p in pnls if p >= 0]
            net_pnl = sum(pnls)
            durations = [t.duration_hours for t in profile_trades if t.duration_hours is not None]

            # Simulation : combien de ticks score_too_low/decision_wait auraient
            # passé le filtre min_score de ce profil ?
            simulated = 0
            for t in ticks:
                if t.reason_no_trade in ("score_too_low", "decision_wait") and t.decision_score is not None:
                    if t.decision_action in ("acheter", "vendre") and abs(t.decision_score) >= params.min_score:
                        simulated += 1
                    elif t.decision_action == "attendre":
                        # Pour le profil scalping avec seuils abaissés, on estime
                        # qu'un score ≥ buy_threshold (ou ≤ -sell_threshold) aurait donné un signal
                        bt = params.buy_threshold or 25
                        st = params.sell_threshold or 20
                        if abs(t.decision_score) > bt or abs(t.decision_score) > st:
                            simulated += 1

            # Top raison de blocage pour ce profil
            blocked_ticks = [t for t in ticks if t.profile_type == profile_name and t.reason_no_trade]
            if blocked_ticks:
                top_block = Counter(t.reason_no_trade for t in blocked_ticks).most_common(1)
                top_reason = top_block[0][0] if top_block else ""
                top_pct = round(top_block[0][1] / len(blocked_ticks) * 100, 1) if top_block else 0
            else:
                top_reason = ""
                top_pct = 0

            rows.append(ProfileComparisonRow(
                profile=profile_name,
                total_trades=n_trades,
                trades_per_day=round(n_trades / days_span, 2) if days_span > 0 else 0,
                win_rate=round(len(wins) / n_trades * 100, 2) if n_trades > 0 else 0,
                net_pnl=round(net_pnl, 2),
                expectancy=round(net_pnl / n_trades, 2) if n_trades > 0 else 0,
                avg_duration_hours=round(sum(durations) / len(durations), 2) if durations else 0,
                max_drawdown_pct=0,  # Nécessiterait un calcul plus complexe
                simulated_entries=simulated,
                simulated_entries_per_day=round(simulated / days_span, 2) if days_span > 0 else 0,
                top_block_reason=REASON_LABELS.get(top_reason, top_reason),
                top_block_pct=top_pct,
            ))

        return rows

    def _analyze_risk_brake(self, ticks: list) -> RiskBrakeAnalysis:
        """Analyse l'impact du risk engine sur la fréquence."""
        total = len(ticks)
        if total == 0:
            return RiskBrakeAnalysis()

        risk_blocked = sum(1 for t in ticks if t.reason_no_trade == "risk_blocked")
        kill_switch = sum(1 for t in ticks if t.reason_no_trade == "kill_switch_active")
        daily_loss = sum(1 for t in ticks if t.reason_no_trade == "daily_loss_protection")

        leverage_reduced = sum(
            1 for t in ticks
            if t.leverage_recommended is not None and t.leverage_final is not None
            and t.leverage_final < t.leverage_recommended
        )
        leverage_forced_x1 = sum(
            1 for t in ticks
            if t.leverage_final is not None and t.leverage_final <= 1.0
            and t.leverage_recommended is not None and t.leverage_recommended > 1.0
        )

        # Catégorisation des filtres
        signal_filters = {"decision_wait", "score_too_low", "confidence_too_low",
                         "scenario_weak", "sentiment_contradictory", "adx_too_low",
                         "volume_insufficient"}
        risk_filters = {"risk_blocked", "daily_loss_protection", "kill_switch_active"}
        structural_filters = {"position_already_open", "cooldown_active", "max_trades_reached"}

        non_trade = [t for t in ticks if t.reason_no_trade]
        total_nt = len(non_trade) or 1

        signal_count = sum(1 for t in non_trade if t.reason_no_trade in signal_filters)
        risk_count = sum(1 for t in non_trade if t.reason_no_trade in risk_filters)
        struct_count = sum(1 for t in non_trade if t.reason_no_trade in structural_filters)

        return RiskBrakeAnalysis(
            total_ticks=total,
            ticks_blocked_by_risk=risk_blocked + kill_switch + daily_loss,
            pct_blocked_by_risk=round((risk_blocked + kill_switch + daily_loss) / total * 100, 2),
            ticks_kill_switch=kill_switch,
            ticks_daily_loss=daily_loss,
            ticks_leverage_reduced=leverage_reduced,
            ticks_leverage_forced_x1=leverage_forced_x1,
            pct_signal_filter=round(signal_count / total_nt * 100, 1),
            pct_risk_filter=round(risk_count / total_nt * 100, 1),
            pct_structural=round(struct_count / total_nt * 100, 1),
        )

    def _identify_bottleneck(
        self,
        reasons: list[NonTradeRankedReason],
        pos_duration: PositionDurationStats,
        risk_brake: RiskBrakeAnalysis,
        total_ticks: int,
        total_trades: int,
    ) -> tuple[str, str, list[str]]:
        """Identifie le goulot d'étranglement principal et produit des recommandations."""
        recommendations = []

        if not reasons:
            return "no_data", "Pas assez de données pour diagnostiquer.", []

        top = reasons[0]

        # Position déjà ouverte = frein structurel majeur
        # Mais seulement si c'est un vrai problème (positions trop longues),
        # pas juste un effet normal d'avoir une position ouverte pendant un moment.
        if top.reason == "position_already_open" and top.pct > 40:
            # Vérifier si les positions sont réellement trop longues
            # (moy > 2h = potentiellement un problème)
            avg_dur = pos_duration.avg_duration_hours if pos_duration.avg_duration_hours > 0 else 0
            med_dur = pos_duration.median_duration_hours if pos_duration.median_duration_hours > 0 else 0

            # Si des positions sont ouvertes en ce moment, vérifier s'il y a aussi
            # des trades fermés. Si oui, le système fonctionne, c'est normal.
            if total_trades > 0 and avg_dur < 1.0:
                # Positions courtes + trades exécutés = le système fonctionne bien
                # Le % élevé est juste parce que le bot tick très souvent
                return (
                    "normal_operation",
                    f"Le système fonctionne normalement. {total_trades} trades exécutés, "
                    f"durée moyenne {avg_dur:.1f}h. Le taux élevé de ticks avec position ouverte "
                    f"({top.pct:.0f}%) est normal avec des ticks fréquents.",
                    [
                        "C'est un comportement normal — le bot trade et garde ses positions",
                        "Augmenter l'intervalle de tick pour réduire les ticks 'en attente'",
                    ],
                )

            return (
                "position_blocking",
                f"{top.pct:.0f}% des ticks sont bloqués par une position déjà ouverte. "
                f"Les positions sont gardées trop longtemps (moy: {avg_dur:.1f}h, "
                f"med: {med_dur:.1f}h).",
                [
                    "Activer le profil Scalping pour des sorties plus rapides",
                    "Réduire la durée max de position",
                    "Activer momentum_fade pour sortir quand l'élan s'essouffle",
                    "Activer stale_exit pour sortir des positions improductives",
                ],
            )

        # Décision = attendre → seuils trop hauts
        if top.reason == "decision_wait" and top.pct > 40:
            return (
                "decision_thresholds_too_high",
                f"{top.pct:.0f}% des ticks reçoivent 'attendre' du moteur de décision. "
                f"Les seuils BUY({25})/SELL({20}) sont trop élevés pour du scalping.",
                [
                    "Passer au profil Scalping (buy_threshold=10, sell_threshold=8)",
                    "Utiliser un timeframe plus court (15m au lieu de 4h)",
                    "Le profil Aggressive (min_score=10) aide mais la décision 'attendre' est en amont",
                ],
            )

        # Score trop faible → profil trop restrictif
        if top.reason == "score_too_low" and top.pct > 30:
            return (
                "profile_too_restrictive",
                f"{top.pct:.0f}% des ticks ont un score insuffisant pour le profil actif.",
                [
                    "Passer au profil Aggressive (min_score=10) ou Scalping (min_score=5)",
                    "Vérifier que le timeframe fournit assez de signal",
                ],
            )

        # Cooldown trop long
        if top.reason == "cooldown_active" and top.pct > 20:
            return (
                "cooldown_too_long",
                f"{top.pct:.0f}% des ticks sont bloqués par le cooldown.",
                [
                    "Réduire le cooldown (Scalping = 3 min)",
                    "Passer au profil Aggressive (cooldown=15 min)",
                ],
            )

        # Risk engine bloque beaucoup
        if risk_brake.pct_blocked_by_risk > 15:
            return (
                "risk_engine_brake",
                f"Le risk engine bloque {risk_brake.pct_blocked_by_risk:.0f}% des ticks.",
                [
                    "Vérifier la config risk (SL/TP, daily loss limit)",
                    "Désactiver le kill switch si activé par erreur",
                ],
            )

        # Par défaut
        return (
            "mixed",
            f"Frein principal : {top.label} ({top.pct:.0f}%). Pas de cause unique dominante.",
            [
                "Passer au profil Scalping pour une fréquence maximale",
                "Utiliser le mode Auto pour adapter le profil à chaque tick",
            ],
        )

    # ================================================================
    # OPPORTUNITÉS MANQUÉES
    # ================================================================

    def get_missed_opportunities(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        lookforward_minutes: int = 30,
        min_move_pct: float = 0.10,
    ) -> MissedOpportunitySummary:
        """
        Analyse ex-post les ticks non-trade pour identifier les mouvements
        favorables qui se sont produits juste après.

        AVERTISSEMENT : ces chiffres sont ex-post et surestiment les gains réels.
        Un mouvement favorable après un tick non-trade n'est PAS nécessairement
        un trade qui aurait été profitable (slippage, timing, etc.).
        """
        account = self.db.query(PaperAccount).first()
        if account is None:
            return MissedOpportunitySummary()

        dt_from, dt_to = self._parse_dates(date_from, date_to)

        # Ticks non-trade avec un signal (pas inactive/no_price)
        non_trade_ticks = (
            self.db.query(TickActivityLog)
            .filter(
                TickActivityLog.account_id == account.id,
                TickActivityLog.timestamp >= dt_from,
                TickActivityLog.timestamp <= dt_to,
                TickActivityLog.reason_no_trade.isnot(None),
                TickActivityLog.btc_price.isnot(None),
                TickActivityLog.decision_action.isnot(None),
                TickActivityLog.reason_no_trade.notin_(["inactive", "no_price", "no_decision_available"]),
            )
            .order_by(TickActivityLog.timestamp.asc())
            .all()
        )

        if not non_trade_ticks:
            return MissedOpportunitySummary()

        # [v1.9.3] Optimisation performance : pré-charger toutes les candles
        # de la période en une seule requête au lieu de N×3 requêtes individuelles.
        # Avec 3500+ ticks, l'ancien code faisait ~10 000 requêtes → timeout 45s.
        total_analyzed = len(non_trade_ticks)

        # Limiter l'analyse aux 500 derniers ticks pour éviter les timeouts
        # sur les grosses périodes. On garde les plus récents (plus pertinents).
        MAX_TICKS_ANALYZED = 500
        if len(non_trade_ticks) > MAX_TICKS_ANALYZED:
            non_trade_ticks = non_trade_ticks[-MAX_TICKS_ANALYZED:]

        # Calculer la plage temporelle totale pour pré-charger les candles
        first_tick_ts = non_trade_ticks[0].timestamp
        last_tick_ts = non_trade_ticks[-1].timestamp
        if first_tick_ts.tzinfo is None:
            first_tick_ts = first_tick_ts.replace(tzinfo=timezone.utc)
        if last_tick_ts.tzinfo is None:
            last_tick_ts = last_tick_ts.replace(tzinfo=timezone.utc)

        candle_end = last_tick_ts + timedelta(minutes=lookforward_minutes + 1)
        all_candles = (
            self.db.query(Candle)
            .filter(
                Candle.symbol == "BTC/USD",
                Candle.timestamp >= first_tick_ts,
                Candle.timestamp <= candle_end,
            )
            .order_by(Candle.timestamp.asc())
            .all()
        )

        # Indexer les candles par timestamp pour recherche rapide
        candle_list = []
        for c in all_candles:
            ts = c.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            candle_list.append((ts, c.close_price))

        missed_items = []
        missed_above = {0.10: 0, 0.20: 0, 0.30: 0, 0.50: 0}
        by_reason = Counter()

        for tick in non_trade_ticks:
            tick_ts = tick.timestamp
            if tick_ts.tzinfo is None:
                tick_ts = tick_ts.replace(tzinfo=timezone.utc)

            tick_price = tick.btc_price
            if not tick_price or tick_price <= 0:
                continue

            # Déterminer la direction favorable
            favorable_direction = 1  # long par défaut
            if tick.decision_action == "vendre":
                favorable_direction = -1
            elif tick.decision_action == "attendre":
                if tick.decision_score and tick.decision_score < 0:
                    favorable_direction = -1

            # Chercher les candles dans les N minutes suivantes
            # en utilisant la liste pré-chargée au lieu de requêtes DB
            windows = [5, 15, 30]
            best_move = 0.0
            best_window = ""
            prices_after = {}

            for window_min in windows:
                if window_min > lookforward_minutes:
                    break
                end_window = tick_ts + timedelta(minutes=window_min)
                # Trouver la candle la plus récente dans [tick_ts, end_window]
                best_candle_price = None
                for c_ts, c_price in candle_list:
                    if c_ts >= tick_ts and c_ts <= end_window:
                        best_candle_price = c_price  # la dernière dans la fenêtre
                    elif c_ts > end_window:
                        break

                if best_candle_price is not None:
                    prices_after[f"{window_min}m"] = best_candle_price
                    move_pct = (best_candle_price - tick_price) / tick_price * 100 * favorable_direction
                    if move_pct > best_move:
                        best_move = move_pct
                        best_window = f"{window_min}m"

            if best_move >= min_move_pct:
                by_reason[tick.reason_no_trade] += 1
                for threshold in missed_above:
                    if best_move >= threshold:
                        missed_above[threshold] += 1

                # Garder les top exemples (limité à 20)
                if len(missed_items) < 20:
                    missed_items.append(MissedOpportunityItem(
                        tick_timestamp=tick_ts.isoformat(),
                        btc_price_at_tick=tick_price,
                        decision_action=tick.decision_action,
                        decision_score=tick.decision_score,
                        reason_no_trade=tick.reason_no_trade,
                        profile_at_tick=tick.profile_type or "unknown",
                        price_after_5m=prices_after.get("5m"),
                        price_after_15m=prices_after.get("15m"),
                        price_after_30m=prices_after.get("30m"),
                        best_move_pct=round(best_move, 3),
                        best_move_window=best_window,
                        was_exploitable=best_move >= 0.20,
                    ))

        ticks_with_favorable = missed_above.get(min_move_pct, 0)
        avg_move = 0.0
        if missed_items:
            avg_move = sum(i.best_move_pct for i in missed_items) / len(missed_items)

        # Raisons des opportunités manquées classées
        missed_reasons = []
        for rank, (reason, count) in enumerate(by_reason.most_common(), 1):
            missed_reasons.append(NonTradeRankedReason(
                rank=rank,
                reason=reason,
                label=REASON_LABELS.get(reason, reason),
                count=count,
                pct=round(count / ticks_with_favorable * 100, 1) if ticks_with_favorable > 0 else 0,
                category=REASON_CATEGORIES.get(reason, "other"),
            ))

        return MissedOpportunitySummary(
            total_non_trade_ticks_analyzed=total_analyzed,
            ticks_with_favorable_move=ticks_with_favorable,
            pct_missed=round(ticks_with_favorable / total_analyzed * 100, 2) if total_analyzed > 0 else 0,
            avg_missed_move_pct=round(avg_move, 3),
            missed_above_010_pct=missed_above.get(0.10, 0),
            missed_above_020_pct=missed_above.get(0.20, 0),
            missed_above_030_pct=missed_above.get(0.30, 0),
            missed_above_050_pct=missed_above.get(0.50, 0),
            missed_by_reason=missed_reasons,
            top_examples=sorted(missed_items, key=lambda x: x.best_move_pct, reverse=True)[:10],
        )

    # ================================================================
    # ANALYSE LEVIER
    # ================================================================

    def get_leverage_analysis(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> LeverageAnalysisResponse:
        """Compare les résultats avec et sans levier."""
        account = self.db.query(PaperAccount).first()
        if account is None:
            return LeverageAnalysisResponse()

        dt_from, dt_to = self._parse_dates(date_from, date_to)

        closed_trades = (
            self.db.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account.id,
                PaperTrade.status != "open",
                PaperTrade.exit_ts >= dt_from,
                PaperTrade.exit_ts <= dt_to,
            )
            .all()
        )

        if not closed_trades:
            return LeverageAnalysisResponse()

        leveraged = [t for t in closed_trades if t.leverage and t.leverage > 1.0]
        unleveraged = [t for t in closed_trades if not t.leverage or t.leverage <= 1.0]

        # PnL réel (avec levier)
        pnl_with = sum(t.pnl for t in closed_trades if t.pnl is not None)

        # PnL simulé sans levier : PnL / leverage pour les trades levierisés
        pnl_without = 0.0
        for t in closed_trades:
            if t.pnl is not None:
                lev = t.leverage or 1.0
                pnl_without += t.pnl / lev

        # Amplification
        amp_pos = sum(1 for t in leveraged if t.pnl and t.pnl > 0)
        amp_neg = sum(1 for t in leveraged if t.pnl and t.pnl < 0)

        # Win rates
        wr_lev = round(
            sum(1 for t in leveraged if t.pnl and t.pnl >= 0) / len(leveraged) * 100, 2
        ) if leveraged else 0

        wr_unlev = round(
            sum(1 for t in unleveraged if t.pnl and t.pnl >= 0) / len(unleveraged) * 100, 2
        ) if unleveraged else 0

        # Trades refusés/réduits par le levier (via tick_activity_log)
        ticks = (
            self.db.query(TickActivityLog)
            .filter(
                TickActivityLog.account_id == account.id,
                TickActivityLog.timestamp >= dt_from,
                TickActivityLog.timestamp <= dt_to,
            )
            .all()
        )
        refused = sum(
            1 for t in ticks
            if t.leverage_reason and "désactivé" in t.leverage_reason.lower()
        )
        reduced = sum(
            1 for t in ticks
            if t.leverage_recommended and t.leverage_final
            and t.leverage_final < t.leverage_recommended
        )

        return LeverageAnalysisResponse(
            total_leveraged_trades=len(leveraged),
            total_unleveraged_trades=len(unleveraged),
            pnl_with_leverage=round(pnl_with, 2),
            pnl_without_leverage=round(pnl_without, 2),
            leverage_benefit=round(pnl_with - pnl_without, 2),
            win_rate_leveraged=wr_lev,
            win_rate_unleveraged=wr_unlev,
            trades_amplified_positive=amp_pos,
            trades_amplified_negative=amp_neg,
            trades_refused_by_leverage=refused,
            trades_reduced_by_risk=reduced,
        )

    # ================================================================
    # HELPERS
    # ================================================================

    def _parse_dates(
        self, date_from: Optional[str], date_to: Optional[str],
    ) -> tuple[datetime, datetime]:
        """Parse les dates ou utilise des defaults (7 derniers jours)."""
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

