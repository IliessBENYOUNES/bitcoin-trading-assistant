"""
Service d'Audit Scalping — Analyse dédiée du sous-système scalping.

Ce service analyse UNIQUEMENT les trades scalping (slot=scalping ou profile_type=scalping)
et fournit un diagnostic détaillé :
- Métriques brutes et nettes (après coûts realistic)
- Distribution des sorties (trailing, stale, signal, momentum_fade, etc.)
- Audit du trailing stop spécifique scalping
- Distribution des scores à l'entrée
- Comparaison long vs short
- Analyse du levier
- Recommandations d'optimisation

Conçu pour diagnostiquer exactement pourquoi le scalping ne fonctionne pas
et quantifier l'impact de chaque paramètre.
"""

import logging
from collections import Counter
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paper_account import PaperAccount, PaperTrade
from app.services.trading_cost_service import (
    TradingCostModel, get_cost_model, COST_PRESETS,
)

logger = logging.getLogger(__name__)


class ScalpingAuditService:
    """
    Service d'audit dédié au scalping.

    Usage :
        service = ScalpingAuditService(db_session)
        result = service.run_audit()
    """

    def __init__(self, db: Session):
        self.db = db

    def run_audit(self, cost_preset: str = "realistic") -> dict:
        """
        Audit complet du sous-système scalping.

        Returns:
            dict avec diagnostic complet scalping et recommandations.
        """
        account = self.db.query(PaperAccount).first()
        if account is None:
            return self._empty_audit("Aucun compte paper trading trouvé")

        # Récupérer TOUS les trades fermés
        all_closed = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.account_id == account.id)
            .filter(PaperTrade.status != "open")
            .order_by(PaperTrade.exit_ts.asc())
            .all()
        )

        # Filtrer les trades scalping (slot OU profile_type = scalping)
        scalping_trades = [
            t for t in all_closed
            if (getattr(t, "slot", None) == "scalping"
                or getattr(t, "profile_type", None) == "scalping")
        ]

        # Trades non-scalping
        other_trades = [t for t in all_closed if t not in scalping_trades]

        # Positions ouvertes scalping
        open_scalping = (
            self.db.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account.id,
                PaperTrade.status == "open",
            )
            .all()
        )
        open_scalping = [
            t for t in open_scalping
            if (getattr(t, "slot", None) == "scalping"
                or getattr(t, "profile_type", None) == "scalping")
        ]

        cost_model = get_cost_model(cost_preset)

        if not scalping_trades:
            return self._empty_audit("Aucun trade scalping fermé trouvé")

        # 1. Métriques globales scalping (brut + net)
        overview = self._scalping_overview(scalping_trades, cost_model)

        # 2. Distribution des sorties
        exit_analysis = self._exit_distribution(scalping_trades, cost_model)

        # 3. Audit du trailing stop
        trailing_audit = self._trailing_stop_audit(scalping_trades, cost_model)

        # 4. Distribution des scores
        score_audit = self._score_distribution(scalping_trades)

        # 5. Long vs Short
        direction_audit = self._direction_audit(scalping_trades, cost_model)

        # 6. Levier
        leverage_audit = self._leverage_audit(scalping_trades, cost_model)

        # 7. Durée des trades
        duration_audit = self._duration_audit(scalping_trades)

        # 8. Comparaison scalping vs autres slots
        comparison = self._slot_comparison(scalping_trades, other_trades, cost_model)

        # 9. Recommandations
        recommendations = self._generate_recommendations(
            overview, exit_analysis, trailing_audit,
            score_audit, direction_audit, leverage_audit,
        )

        return {
            "total_scalping_trades": len(scalping_trades),
            "total_other_trades": len(other_trades),
            "open_scalping_positions": len(open_scalping),
            "cost_model_used": cost_preset,
            "overview": overview,
            "exit_analysis": exit_analysis,
            "trailing_stop_audit": trailing_audit,
            "score_distribution": score_audit,
            "direction_audit": direction_audit,
            "leverage_audit": leverage_audit,
            "duration_audit": duration_audit,
            "slot_comparison": comparison,
            "recommendations": recommendations,
        }

    # ================================================================
    # 1. OVERVIEW
    # ================================================================

    def _scalping_overview(self, trades: list[PaperTrade],
                           cost_model: TradingCostModel) -> dict:
        """Métriques globales du scalping."""
        trade_dicts = self._to_dicts(trades)
        metrics = cost_model.apply_to_trades(trade_dicts)

        pnls = [t.pnl or 0 for t in trades]
        wins = [p for p in pnls if p >= 0]
        losses = [p for p in pnls if p < 0]

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        return {
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_gross": round(len(wins) / len(trades) * 100, 2) if trades else 0,
            "gross_pnl": round(sum(pnls), 2),
            "net_pnl": round(metrics["net_pnl"], 2),
            "total_costs": round(metrics["total_costs"], 2),
            "avg_trade_pnl_gross": round(sum(pnls) / len(trades), 2) if trades else 0,
            "avg_trade_pnl_net": round(metrics["net_avg_trade"], 4) if "net_avg_trade" in metrics else 0,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "best_trade": round(max(pnls), 2) if pnls else 0,
            "worst_trade": round(min(pnls), 2) if pnls else 0,
            "gross_expectancy": round(metrics.get("gross_expectancy", 0), 4),
            "net_expectancy": round(metrics.get("net_expectancy", 0), 4),
            "gross_profit_factor": round(metrics.get("gross_profit_factor", 0), 2),
            "net_profit_factor": round(metrics.get("net_profit_factor", 0), 2),
            "gross_win_rate": round(metrics.get("gross_win_rate", 0), 2),
            "net_win_rate": round(metrics.get("net_win_rate", 0), 2),
            "cost_per_trade": round(metrics["total_costs"] / len(trades), 2) if trades else 0,
            "verdict": self._overview_verdict(metrics, pnls),
        }

    def _overview_verdict(self, metrics: dict, pnls: list[float]) -> str:
        """Verdict texte sur la santé globale du scalping."""
        net_pnl = metrics.get("net_pnl", 0)
        gross_pnl = sum(pnls)
        if net_pnl > 0:
            return "✅ Le scalping est net-positif après coûts."
        elif gross_pnl > 0 and net_pnl <= 0:
            return "⚠️ Le scalping est brut-positif mais NET-NÉGATIF après coûts. Les coûts dévorent les gains."
        else:
            return "❌ Le scalping perd de l'argent même en brut. Recalibrage nécessaire."

    # ================================================================
    # 2. EXIT DISTRIBUTION
    # ================================================================

    def _exit_distribution(self, trades: list[PaperTrade],
                           cost_model: TradingCostModel) -> dict:
        """Distribution des raisons de sortie avec PnL par type."""
        by_exit: dict[str, list[PaperTrade]] = {}
        for t in trades:
            status = t.status or "unknown"
            if status not in by_exit:
                by_exit[status] = []
            by_exit[status].append(t)

        result = {}
        for status, group in sorted(by_exit.items(), key=lambda x: -len(x[1])):
            pnls = [t.pnl or 0 for t in group]
            dicts = self._to_dicts(group)
            metrics = cost_model.apply_to_trades(dicts)
            wins = len([p for p in pnls if p >= 0])
            result[status] = {
                "count": len(group),
                "pct_of_total": round(len(group) / len(trades) * 100, 1),
                "gross_pnl": round(sum(pnls), 2),
                "net_pnl": round(metrics["net_pnl"], 2),
                "avg_pnl_gross": round(sum(pnls) / len(group), 2),
                "win_count": wins,
                "loss_count": len(group) - wins,
                "win_rate": round(wins / len(group) * 100, 1) if group else 0,
                "verdict": self._exit_verdict(status, pnls, metrics),
            }

        return result

    def _exit_verdict(self, status: str, pnls: list[float], metrics: dict) -> str:
        """Verdict par type de sortie."""
        avg = sum(pnls) / len(pnls) if pnls else 0
        net = metrics.get("net_pnl", 0)
        if status == "closed_trailing_stop":
            if net <= 0:
                return "🔴 Le trailing stop DÉTRUIT le PnL — trop serré, sort au bruit."
            return "🟡 Trailing stop marginal — vérifie s'il protège vraiment."
        elif status == "closed_stale":
            if avg > 0:
                return "🟢 Stale exit capture du profit sur positions qui stagnent."
            return "🟡 Stale exit coupe trop tôt — considérer allonger le timeout."
        elif status == "closed_signal":
            if avg > 0:
                return "🟢 Sorties signal capturent bien le retournement."
            return "🔴 Sorties signal perdantes — les coupures de perte rapide sont coûteuses."
        elif status == "closed_momentum_fade":
            if avg > 0:
                return "🟢 Momentum fade protège les gains correctement."
            return "🟡 Momentum fade sort trop tôt."
        return ""

    # ================================================================
    # 3. TRAILING STOP AUDIT
    # ================================================================

    def _trailing_stop_audit(self, trades: list[PaperTrade],
                              cost_model: TradingCostModel) -> dict:
        """Audit détaillé du trailing stop scalping."""
        trailing = [t for t in trades if t.status == "closed_trailing_stop"]
        other = [t for t in trades if t.status != "closed_trailing_stop"]

        if not trailing:
            return {
                "trailing_count": 0,
                "used": False,
                "verdict": "Trailing stop non utilisé.",
            }

        t_pnls = [t.pnl or 0 for t in trailing]
        t_wins = len([p for p in t_pnls if p > 0])
        t_flat = len([p for p in t_pnls if abs(p) < 0.5])  # quasi-plat
        t_losses = len([p for p in t_pnls if p < 0])

        t_dicts = self._to_dicts(trailing)
        t_metrics = cost_model.apply_to_trades(t_dicts)

        # Comparaison avec les autres sorties
        o_avg = 0
        if other:
            o_pnls = [t.pnl or 0 for t in other]
            o_avg = sum(o_pnls) / len(o_pnls)

        t_avg = sum(t_pnls) / len(t_pnls)

        # Analyse par PnL : combien sont à plat, positifs, négatifs
        near_zero = [p for p in t_pnls if abs(p) < 1.0]
        pct_near_zero = len(near_zero) / len(t_pnls) * 100

        verdict = []
        if pct_near_zero > 60:
            verdict.append("🔴 >60% des trailing exits sont quasi à plat — le trail est du BRUIT.")
        if t_avg < 0:
            verdict.append("🔴 PnL moyen trailing NÉGATIF — le trailing stop perd de l'argent.")
        if t_avg < o_avg and other:
            verdict.append(f"🔴 Trailing avg ({t_avg:.2f}) < autres sorties avg ({o_avg:.2f}).")
        if t_wins == 0:
            verdict.append("🔴 Aucun trailing exit gagnant.")
        if not verdict:
            verdict.append("🟢 Le trailing stop semble fonctionner correctement.")

        return {
            "trailing_count": len(trailing),
            "other_count": len(other),
            "used": True,
            "trailing_wins": t_wins,
            "trailing_losses": t_losses,
            "trailing_flat": t_flat,
            "pct_near_zero": round(pct_near_zero, 1),
            "trailing_avg_pnl": round(t_avg, 2),
            "trailing_net_pnl": round(t_metrics["net_pnl"], 2),
            "other_avg_pnl": round(o_avg, 2),
            "trailing_pnl_list": [round(p, 2) for p in t_pnls],
            "verdict": " ".join(verdict),
        }

    # ================================================================
    # 4. SCORE DISTRIBUTION
    # ================================================================

    def _score_distribution(self, trades: list[PaperTrade]) -> dict:
        """Analyse la distribution des scores d'entrée."""
        scores = [t.decision_score or 0 for t in trades]
        if not scores:
            return {"saturated": True, "verdict": "Aucun score."}

        unique_scores = set(scores)
        score_counts = Counter(scores)
        most_common = score_counts.most_common(3)

        # Détection de saturation : si >70% des trades ont le même score
        top_score, top_count = most_common[0]
        saturation_pct = top_count / len(scores) * 100

        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)
        score_range = max_score - min_score

        verdict = []
        if saturation_pct > 70:
            verdict.append(
                f"🔴 SATURATION : {saturation_pct:.0f}% des trades ont score={top_score}. "
                f"Le moteur ne discrimine PAS les setups."
            )
        if score_range < 10:
            verdict.append(
                f"🔴 GRANULARITÉ NULLE : range de scores = {score_range:.0f} "
                f"(min={min_score:.0f}, max={max_score:.0f}). Tous les setups sont identiques."
            )
        if len(unique_scores) <= 3 and len(trades) > 5:
            verdict.append(
                f"🟡 Seulement {len(unique_scores)} scores uniques sur {len(trades)} trades."
            )
        if not verdict:
            verdict.append("🟢 Distribution des scores correcte.")

        return {
            "total_trades": len(trades),
            "unique_scores": len(unique_scores),
            "avg_score": round(avg_score, 1),
            "min_score": round(min_score, 1),
            "max_score": round(max_score, 1),
            "score_range": round(score_range, 1),
            "most_common_scores": [{"score": s, "count": c, "pct": round(c / len(trades) * 100, 1)} for s, c in most_common],
            "saturation_pct": round(saturation_pct, 1),
            "saturated": saturation_pct > 70,
            "verdict": " ".join(verdict),
        }

    # ================================================================
    # 5. DIRECTION AUDIT (Long vs Short)
    # ================================================================

    def _direction_audit(self, trades: list[PaperTrade],
                          cost_model: TradingCostModel) -> dict:
        """Audit long vs short en scalping."""
        longs = [t for t in trades if t.direction == "long"]
        shorts = [t for t in trades if t.direction == "short"]

        result = {
            "total_trades": len(trades),
            "long_count": len(longs),
            "short_count": len(shorts),
            "long_pct": round(len(longs) / len(trades) * 100, 1) if trades else 0,
            "short_pct": round(len(shorts) / len(trades) * 100, 1) if trades else 0,
        }

        if longs:
            l_pnls = [t.pnl or 0 for t in longs]
            l_dicts = self._to_dicts(longs)
            l_metrics = cost_model.apply_to_trades(l_dicts)
            result["long"] = {
                "count": len(longs),
                "gross_pnl": round(sum(l_pnls), 2),
                "net_pnl": round(l_metrics["net_pnl"], 2),
                "win_rate": round(len([p for p in l_pnls if p >= 0]) / len(longs) * 100, 1),
                "avg_pnl": round(sum(l_pnls) / len(longs), 2),
                "net_expectancy": round(l_metrics.get("net_expectancy", 0), 4),
            }

        if shorts:
            s_pnls = [t.pnl or 0 for t in shorts]
            s_dicts = self._to_dicts(shorts)
            s_metrics = cost_model.apply_to_trades(s_dicts)
            result["short"] = {
                "count": len(shorts),
                "gross_pnl": round(sum(s_pnls), 2),
                "net_pnl": round(s_metrics["net_pnl"], 2),
                "win_rate": round(len([p for p in s_pnls if p >= 0]) / len(shorts) * 100, 1),
                "avg_pnl": round(sum(s_pnls) / len(shorts), 2),
                "net_expectancy": round(s_metrics.get("net_expectancy", 0), 4),
            }

        # Verdict
        if len(shorts) == 0:
            result["verdict"] = (
                "🔴 AUCUN trade short scalping. Le short est MORT en runtime. "
                "La logique de mean reversion ne se déclenche pas ou est bloquée."
            )
        elif len(shorts) < len(trades) * 0.15:
            result["verdict"] = (
                f"🟡 Seulement {len(shorts)} shorts ({result['short_pct']:.0f}%). "
                "Le short scalping est très sous-représenté."
            )
        else:
            result["verdict"] = f"🟢 Mix long/short : {len(longs)}L / {len(shorts)}S."

        return result

    # ================================================================
    # 6. LEVERAGE AUDIT
    # ================================================================

    def _leverage_audit(self, trades: list[PaperTrade],
                         cost_model: TradingCostModel) -> dict:
        """Audit du levier en scalping."""
        leverages = [(getattr(t, "leverage", 1.0) or 1.0) for t in trades]
        avg_lev = sum(leverages) / len(leverages)
        unique_levs = set(leverages)

        # Calculer PnL comme si tout était x1
        pnl_as_x1 = []
        pnl_with_lev = []
        for t in trades:
            lev = getattr(t, "leverage", 1.0) or 1.0
            pnl = t.pnl or 0
            pnl_with_lev.append(pnl)
            pnl_as_x1.append(pnl / lev if lev > 0 else 0)

        total_with = sum(pnl_with_lev)
        total_without = sum(pnl_as_x1)
        lev_delta = total_with - total_without

        # Net avec/sans levier
        dicts_with = self._to_dicts(trades)
        metrics_with = cost_model.apply_to_trades(dicts_with)

        dicts_x1 = [
            {"pnl": p, "position_size_usd": t.position_size_usd or 0, "leverage": 1.0}
            for p, t in zip(pnl_as_x1, trades)
        ]
        metrics_x1 = cost_model.apply_to_trades(dicts_x1)

        net_benefit = metrics_with["net_pnl"] - metrics_x1["net_pnl"]

        verdict = []
        if len(unique_levs) <= 1:
            verdict.append(f"🟡 Levier UNIFORME (x{avg_lev:.1f}) — pas de discrimination.")
        if net_benefit < 0:
            verdict.append(f"🔴 Le levier DÉGRADE le net de {net_benefit:.2f} USD.")
        elif net_benefit > 0:
            verdict.append(f"🟢 Le levier améliore le net de +{net_benefit:.2f} USD.")
        if avg_lev > 1.0 and metrics_with.get("net_pnl", 0) < 0:
            verdict.append("🔴 Levier actif sur un système net-négatif — amplifie les pertes.")

        return {
            "avg_leverage": round(avg_lev, 2),
            "unique_leverages": sorted(unique_levs),
            "leverage_uniform": len(unique_levs) <= 1,
            "gross_pnl_with_leverage": round(total_with, 2),
            "gross_pnl_without_leverage": round(total_without, 2),
            "leverage_gross_delta": round(lev_delta, 2),
            "net_pnl_with_leverage": round(metrics_with["net_pnl"], 2),
            "net_pnl_without_leverage": round(metrics_x1["net_pnl"], 2),
            "leverage_net_benefit": round(net_benefit, 2),
            "improves_net": net_benefit > 0,
            "verdict": " ".join(verdict),
        }

    # ================================================================
    # 7. DURATION AUDIT
    # ================================================================

    def _duration_audit(self, trades: list[PaperTrade]) -> dict:
        """Analyse des durées de trades scalping."""
        durations_min = []
        for t in trades:
            h = t.duration_hours or 0
            durations_min.append(h * 60)

        if not durations_min:
            return {"avg_minutes": 0, "verdict": "Pas de données de durée."}

        avg = sum(durations_min) / len(durations_min)
        sorted_d = sorted(durations_min)
        median = sorted_d[len(sorted_d) // 2]

        # Buckets
        under_1 = len([d for d in durations_min if d < 1])
        under_5 = len([d for d in durations_min if 1 <= d < 5])
        under_15 = len([d for d in durations_min if 5 <= d < 15])
        over_15 = len([d for d in durations_min if d >= 15])

        return {
            "total_trades": len(trades),
            "avg_minutes": round(avg, 1),
            "median_minutes": round(median, 1),
            "min_minutes": round(min(durations_min), 1),
            "max_minutes": round(max(durations_min), 1),
            "buckets": {
                "under_1min": under_1,
                "1_5min": under_5,
                "5_15min": under_15,
                "over_15min": over_15,
            },
            "verdict": (
                f"Durée moyenne {avg:.1f}min, médiane {median:.1f}min. "
                f"{under_1} trades <1min (bruit ?)."
            ),
        }

    # ================================================================
    # 8. SLOT COMPARISON
    # ================================================================

    def _slot_comparison(self, scalping_trades: list[PaperTrade],
                          other_trades: list[PaperTrade],
                          cost_model: TradingCostModel) -> dict:
        """Compare scalping vs autres slots."""
        s_pnls = [t.pnl or 0 for t in scalping_trades]
        s_dicts = self._to_dicts(scalping_trades)
        s_metrics = cost_model.apply_to_trades(s_dicts)

        result = {
            "scalping": {
                "count": len(scalping_trades),
                "gross_pnl": round(sum(s_pnls), 2),
                "net_pnl": round(s_metrics["net_pnl"], 2),
                "costs": round(s_metrics["total_costs"], 2),
            }
        }

        if other_trades:
            o_pnls = [t.pnl or 0 for t in other_trades]
            o_dicts = self._to_dicts(other_trades)
            o_metrics = cost_model.apply_to_trades(o_dicts)
            result["other"] = {
                "count": len(other_trades),
                "gross_pnl": round(sum(o_pnls), 2),
                "net_pnl": round(o_metrics["net_pnl"], 2),
                "costs": round(o_metrics["total_costs"], 2),
            }

        return result

    # ================================================================
    # 9. RECOMMENDATIONS
    # ================================================================

    def _generate_recommendations(self, overview, exit_analysis,
                                   trailing_audit, score_audit,
                                   direction_audit, leverage_audit) -> list[str]:
        """Génère des recommandations actionables."""
        recs = []

        # Trailing stop
        if trailing_audit.get("used"):
            if trailing_audit.get("pct_near_zero", 0) > 50:
                recs.append(
                    "🔧 TRAILING STOP : Augmenter trailing_stop_activation_pct (ex: 0.08%) "
                    "et trailing_stop_pct (ex: 0.12%). Le trail actuel sort au bruit du marché."
                )
            if trailing_audit.get("trailing_avg_pnl", 0) < 0:
                recs.append(
                    "🔧 TRAILING STOP : PnL moyen négatif — considérer désactiver le trailing "
                    "ou augmenter fortement les seuils."
                )

        # Score
        if score_audit.get("saturated"):
            recs.append(
                "🔧 SCORING : Score saturé — augmenter buy_threshold (ex: 20) et min_score (ex: 15) "
                "pour ne garder que les meilleurs setups."
            )
        if score_audit.get("score_range", 0) < 15:
            recs.append(
                "🔧 SCORING : Ajouter de la granularité au scoring scalping "
                "(timeframe plus court, indicateurs micro-structure)."
            )

        # Short
        if direction_audit.get("short_count", 0) == 0:
            recs.append(
                "🔧 SHORT : Aucun trade short — vérifier _scalping_reversal_check, "
                "abaisser les seuils de surachat/survente, ou ajouter des oscillateurs."
            )

        # Leverage
        if leverage_audit.get("leverage_uniform") and not leverage_audit.get("improves_net"):
            recs.append(
                "🔧 LEVIER : Levier uniforme et net-négatif — forcer x1.0 en scalping "
                "jusqu'à edge net positif prouvé."
            )

        # Overview
        net_pnl = overview.get("net_pnl", 0)
        if net_pnl < 0 and overview.get("gross_pnl", 0) > 0:
            recs.append(
                "🔧 COÛTS : Brut positif mais net négatif — réduire la fréquence de trading "
                "et augmenter la sélectivité des entrées."
            )

        # Stale exit
        if "closed_stale" in exit_analysis:
            stale = exit_analysis["closed_stale"]
            if stale.get("avg_pnl_gross", 0) > 0:
                recs.append(
                    "ℹ️ STALE : Les sorties stagnantes sont nettes positives — "
                    "possiblement augmenter légèrement stale_exit_minutes."
                )

        if not recs:
            recs.append("✅ Pas de recommandation critique — le scalping fonctionne.")

        return recs

    # ================================================================
    # HELPERS
    # ================================================================

    def _to_dicts(self, trades: list[PaperTrade]) -> list[dict]:
        """Convertit les trades en dicts pour le cost model."""
        result = []
        for t in trades:
            result.append({
                "pnl": t.pnl or 0,
                "position_size_usd": t.position_size_usd or 0,
                "leverage": getattr(t, "leverage", 1.0) or 1.0,
                "slot": getattr(t, "slot", None),
                "profile_type": getattr(t, "profile_type", None),
                "status": t.status,
                "direction": t.direction,
                "duration_hours": t.duration_hours or 0,
                "pnl_pct": t.pnl_pct or 0,
            })
        return result

    def _empty_audit(self, reason: str) -> dict:
        """Retourne un audit vide."""
        return {
            "total_scalping_trades": 0,
            "total_other_trades": 0,
            "open_scalping_positions": 0,
            "cost_model_used": "realistic",
            "overview": {"verdict": reason},
            "exit_analysis": {},
            "trailing_stop_audit": {"used": False},
            "score_distribution": {},
            "direction_audit": {"verdict": reason},
            "leverage_audit": {},
            "duration_audit": {},
            "slot_comparison": {},
            "recommendations": [reason],
        }

