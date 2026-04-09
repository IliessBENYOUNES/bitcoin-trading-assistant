"""
RunValueAuditService — Audit de valeur économique d'un run paper trading.

Analyse les trades fermés pour diagnostiquer :
1. La valeur économique capturée par trade
2. La répartition useful / insignificant / churn
3. La dominance des sorties "signal contraire" sur les shorts
4. La distribution par bucket de PnL
5. L'économie du short scalping

Conçu pour répondre à : "Pourquoi le moteur extrait trop peu de valeur par trade ?"

v1.9.3
"""

import logging
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paper_account import PaperAccount, PaperTrade
from app.services.trading_cost_service import TradingCostModel, get_cost_model
from app.services.learning_service import LearningService

logger = logging.getLogger(__name__)


# Seuil USD au-dessus duquel un trade est "useful" en net
USEFUL_NET_THRESHOLD = 0.50

# Buckets PnL pour la distribution
PNL_BUCKETS = [
    ("≤ 0", lambda p: p <= 0),
    ("0 à 0.25", lambda p: 0 < p <= 0.25),
    ("0.25 à 0.50", lambda p: 0.25 < p <= 0.50),
    ("0.50 à 1.00", lambda p: 0.50 < p <= 1.00),
    ("1.00 à 2.00", lambda p: 1.00 < p <= 2.00),
    ("> 2.00", lambda p: p > 2.00),
]


class RunValueAuditService:
    """
    Audit de valeur économique d'un run paper trading.

    Usage :
        service = RunValueAuditService(db_session)
        result = service.run_audit()
    """

    def __init__(self, db: Session):
        self.db = db

    def run_audit(self, cost_preset: str = "realistic") -> dict:
        """
        Audit complet : valeur par trade, useful vs churn, signal contraire, buckets PnL.
        """
        account = self.db.query(PaperAccount).first()
        if account is None:
            return self._empty("Aucun compte paper trading trouvé")

        all_closed = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.account_id == account.id, PaperTrade.status != "open")
            .order_by(PaperTrade.exit_ts.asc())
            .all()
        )

        if not all_closed:
            return self._empty("Aucun trade fermé trouvé")

        cost_model = get_cost_model(cost_preset)

        # ---- SECTION A : Audit économique global ----
        economic = self._economic_audit(all_closed, cost_model)

        # ---- SECTION B : Useful / insignificant / churn ----
        usefulness = self._usefulness_audit(all_closed, cost_model)

        # ---- SECTION C : Distribution par bucket de PnL ----
        pnl_buckets = self._pnl_bucket_distribution(all_closed, cost_model)

        # ---- SECTION D : Audit signal contraire sur shorts ----
        signal_exit = self._signal_exit_audit(all_closed, cost_model)

        # ---- SECTION E : Short economics ----
        short_economics = self._short_economics(all_closed, cost_model)

        return {
            "total_trades": len(all_closed),
            "cost_model": cost_preset,
            "economic_audit": economic,
            "usefulness_audit": usefulness,
            "pnl_bucket_distribution": pnl_buckets,
            "signal_exit_audit": signal_exit,
            "short_economics": short_economics,
        }

    # ================================================================
    # A. AUDIT ÉCONOMIQUE GLOBAL
    # ================================================================

    def _economic_audit(self, trades: list, cost_model: TradingCostModel) -> dict:
        """Métriques économiques brut vs net pour tout le run."""
        dicts = self._to_dicts(trades)
        metrics = cost_model.apply_to_trades(dicts)

        pnls = [t.pnl or 0 for t in trades]
        wins = [p for p in pnls if p >= 0]
        losses = [p for p in pnls if p < 0]

        return {
            "total_trades": len(trades),
            "gross_pnl": round(sum(pnls), 2),
            "total_costs": round(metrics["total_costs"], 2),
            "net_pnl": round(metrics["net_pnl"], 2),
            "avg_trade_pnl_gross": round(sum(pnls) / len(pnls), 4) if pnls else 0,
            "avg_trade_pnl_net": round(metrics.get("net_avg_trade", 0), 4),
            "cost_per_trade": round(metrics["total_costs"] / len(trades), 4) if trades else 0,
            "gross_expectancy": round(metrics.get("gross_expectancy", 0), 4),
            "net_expectancy": round(metrics.get("net_expectancy", 0), 4),
            "gross_profit_factor": round(metrics.get("gross_profit_factor", 0), 2),
            "net_profit_factor": round(metrics.get("net_profit_factor", 0), 2),
            "gross_win_rate": round(metrics.get("gross_win_rate", 0), 2),
            "net_win_rate": round(metrics.get("net_win_rate", 0), 2),
            "avg_win_gross": round(sum(wins) / len(wins), 2) if wins else 0,
            "avg_loss_gross": round(sum(losses) / len(losses), 2) if losses else 0,
        }

    # ================================================================
    # B. USEFULNESS AUDIT
    # ================================================================

    def _usefulness_audit(self, trades: list, cost_model: TradingCostModel) -> dict:
        """Catégorisation useful / insignificant / churn / loss_useful / loss_destructive."""
        categories = defaultdict(list)

        for t in trades:
            pnl = t.pnl or 0
            size = (t.position_size_usd or 0) * (getattr(t, "leverage", 1.0) or 1.0)
            cost = cost_model.round_trip_cost_usd(size)
            net = pnl - cost
            dur_min = (t.duration_hours or 0) * 60
            pnl_pct = t.pnl_pct

            cat = LearningService._classify_usefulness(
                pnl_brut=pnl, pnl_net=net,
                pnl_pct=pnl_pct, duration_min=dur_min,
            )
            categories[cat].append({
                "pnl_brut": pnl, "pnl_net": net, "cost": cost,
                "dur_min": dur_min, "direction": t.direction,
            })

        result = {}
        total = len(trades)
        for cat, items in categories.items():
            avg_brut = sum(i["pnl_brut"] for i in items) / len(items) if items else 0
            avg_net = sum(i["pnl_net"] for i in items) / len(items) if items else 0
            result[cat] = {
                "count": len(items),
                "pct": round(len(items) / total * 100, 1) if total else 0,
                "avg_pnl_brut": round(avg_brut, 2),
                "avg_pnl_net": round(avg_net, 2),
                "total_pnl_net": round(sum(i["pnl_net"] for i in items), 2),
            }

        return {
            "total": total,
            "categories": result,
            "pct_useful": result.get("useful", {}).get("pct", 0),
            "pct_insignificant": result.get("insignificant", {}).get("pct", 0),
            "pct_churn": result.get("churn", {}).get("pct", 0),
            "verdict": self._usefulness_verdict(result, total),
        }

    def _usefulness_verdict(self, cats: dict, total: int) -> str:
        useful_pct = cats.get("useful", {}).get("pct", 0)
        insignif_pct = cats.get("insignificant", {}).get("pct", 0)
        churn_pct = cats.get("churn", {}).get("pct", 0)

        if useful_pct >= 50:
            return f"🟢 {useful_pct:.0f}% de trades utiles — le moteur extrait de la valeur."
        elif useful_pct >= 30:
            return (
                f"🟡 {useful_pct:.0f}% utiles, {insignif_pct:.0f}% insignifiants, {churn_pct:.0f}% churn "
                f"— valeur extraite mais trop de bruit."
            )
        else:
            return (
                f"🔴 Seulement {useful_pct:.0f}% utiles. {insignif_pct:.0f}% insignifiants + {churn_pct:.0f}% churn "
                f"= le moteur extrait trop peu de valeur par trade."
            )

    # ================================================================
    # C. PNL BUCKET DISTRIBUTION
    # ================================================================

    def _pnl_bucket_distribution(self, trades: list, cost_model: TradingCostModel) -> dict:
        """Distribution des trades par bucket de PnL brut et net."""
        gross_buckets = {label: 0 for label, _ in PNL_BUCKETS}
        net_buckets = {label: 0 for label, _ in PNL_BUCKETS}

        for t in trades:
            pnl = t.pnl or 0
            size = (t.position_size_usd or 0) * (getattr(t, "leverage", 1.0) or 1.0)
            cost = cost_model.round_trip_cost_usd(size)
            net = pnl - cost

            for label, fn in PNL_BUCKETS:
                if fn(pnl):
                    gross_buckets[label] += 1
                    break
            for label, fn in PNL_BUCKETS:
                if fn(net):
                    net_buckets[label] += 1
                    break

        return {
            "gross": gross_buckets,
            "net": net_buckets,
            "dust_zone_pct": round(
                (gross_buckets.get("0 à 0.25", 0) + gross_buckets.get("≤ 0", 0))
                / len(trades) * 100, 1
            ) if trades else 0,
        }

    # ================================================================
    # D. SIGNAL EXIT AUDIT (signal contraire)
    # ================================================================

    def _signal_exit_audit(self, trades: list, cost_model: TradingCostModel) -> dict:
        """Audit détaillé des sorties par signal contraire, focus shorts."""
        signal_exits = [t for t in trades if t.status == "closed_signal"]
        short_signal_exits = [t for t in signal_exits if t.direction == "short"]
        all_shorts = [t for t in trades if t.direction == "short"]

        result = {
            "total_signal_exits": len(signal_exits),
            "total_short_signal_exits": len(short_signal_exits),
            "total_shorts": len(all_shorts),
            "signal_exit_pct_of_shorts": round(
                len(short_signal_exits) / len(all_shorts) * 100, 1
            ) if all_shorts else 0,
        }

        if short_signal_exits:
            pnls = [t.pnl or 0 for t in short_signal_exits]
            durs = [(t.duration_hours or 0) * 60 for t in short_signal_exits]
            dicts = self._to_dicts(short_signal_exits)
            metrics = cost_model.apply_to_trades(dicts)

            # Catégories d'utilité
            useful = 0
            insignif = 0
            churn = 0
            for t in short_signal_exits:
                size = (t.position_size_usd or 0) * (getattr(t, "leverage", 1.0) or 1.0)
                cost = cost_model.round_trip_cost_usd(size)
                net = (t.pnl or 0) - cost
                dur = (t.duration_hours or 0) * 60
                cat = LearningService._classify_usefulness(
                    pnl_brut=t.pnl or 0, pnl_net=net,
                    pnl_pct=t.pnl_pct, duration_min=dur,
                )
                if cat == "useful":
                    useful += 1
                elif cat == "insignificant":
                    insignif += 1
                elif cat == "churn":
                    churn += 1

            result.update({
                "avg_pnl_gross": round(sum(pnls) / len(pnls), 2),
                "avg_pnl_net": round(metrics.get("net_avg_trade", 0), 4),
                "avg_duration_min": round(sum(durs) / len(durs), 1),
                "useful": useful,
                "insignificant": insignif,
                "churn": churn,
                "is_kill_switch": len(short_signal_exits) > len(all_shorts) * 0.5,
                "verdict": self._signal_exit_verdict(
                    short_signal_exits, all_shorts, metrics
                ),
            })

        return result

    def _signal_exit_verdict(self, signal_exits, all_shorts, metrics) -> str:
        pct = len(signal_exits) / len(all_shorts) * 100 if all_shorts else 0
        net_avg = metrics.get("net_avg_trade", 0)
        if pct > 60:
            return (
                f"🔴 SIGNAL CONTRAIRE DOMINANT : {pct:.0f}% des shorts clos par signal contraire. "
                f"PnL net moyen {net_avg:.4f}. Cela agit comme un kill switch trop sensible."
            )
        elif pct > 40:
            return (
                f"🟡 Signal contraire fréquent ({pct:.0f}%). "
                f"Vérifier si le moteur principal repasse trop vite bullish."
            )
        else:
            return f"🟢 Signal contraire maîtrisé ({pct:.0f}%)."

    # ================================================================
    # E. SHORT ECONOMICS
    # ================================================================

    def _short_economics(self, trades: list, cost_model: TradingCostModel) -> dict:
        """Audit économique dédié aux shorts."""
        shorts = [t for t in trades if t.direction == "short"]
        longs = [t for t in trades if t.direction == "long"]

        if not shorts:
            return {"short_count": 0, "verdict": "Aucun trade short."}

        s_dicts = self._to_dicts(shorts)
        s_metrics = cost_model.apply_to_trades(s_dicts)
        s_pnls = [t.pnl or 0 for t in shorts]
        s_durs = [(t.duration_hours or 0) * 60 for t in shorts]

        # Sortie dominante
        exit_counts = defaultdict(int)
        for t in shorts:
            exit_counts[t.status] += 1
        dominant_exit = max(exit_counts, key=exit_counts.get) if exit_counts else "none"

        # Catégories
        useful = 0
        insignif = 0
        churn_count = 0
        for t in shorts:
            size = (t.position_size_usd or 0) * (getattr(t, "leverage", 1.0) or 1.0)
            cost = cost_model.round_trip_cost_usd(size)
            net = (t.pnl or 0) - cost
            dur = (t.duration_hours or 0) * 60
            cat = LearningService._classify_usefulness(
                pnl_brut=t.pnl or 0, pnl_net=net,
                pnl_pct=t.pnl_pct, duration_min=dur,
            )
            if cat == "useful":
                useful += 1
            elif cat == "insignificant":
                insignif += 1
            elif cat == "churn":
                churn_count += 1

        return {
            "short_count": len(shorts),
            "long_count": len(longs),
            "short_pct": round(len(shorts) / len(trades) * 100, 1) if trades else 0,
            "gross_pnl": round(sum(s_pnls), 2),
            "net_pnl": round(s_metrics["net_pnl"], 2),
            "avg_pnl_gross": round(sum(s_pnls) / len(shorts), 2),
            "avg_pnl_net": round(s_metrics.get("net_avg_trade", 0), 4),
            "avg_duration_min": round(sum(s_durs) / len(s_durs), 1) if s_durs else 0,
            "dominant_exit": dominant_exit,
            "exit_distribution": dict(exit_counts),
            "useful": useful,
            "insignificant": insignif,
            "churn": churn_count,
            "pct_useful": round(useful / len(shorts) * 100, 1) if shorts else 0,
            "win_rate": round(s_metrics.get("gross_win_rate", 0), 2),
            "net_win_rate": round(s_metrics.get("net_win_rate", 0), 2),
            "verdict": self._short_verdict(shorts, useful, insignif, churn_count, s_metrics),
        }

    def _short_verdict(self, shorts, useful, insignif, churn, metrics) -> str:
        pct_useful = useful / len(shorts) * 100 if shorts else 0
        net = metrics.get("net_pnl", 0)
        if pct_useful >= 40 and net > 0:
            return f"🟢 Short utile : {pct_useful:.0f}% useful, net={net:.2f}."
        elif net > 0:
            return f"🟡 Short net-positif mais seulement {pct_useful:.0f}% useful."
        else:
            return (
                f"🔴 Short net-négatif ({net:.2f}). "
                f"{pct_useful:.0f}% useful, {round(insignif/len(shorts)*100) if shorts else 0}% insignif, "
                f"{round(churn/len(shorts)*100) if shorts else 0}% churn."
            )

    # ================================================================
    # HELPERS
    # ================================================================

    def _to_dicts(self, trades) -> list[dict]:
        return [
            {
                "pnl": t.pnl or 0,
                "position_size_usd": t.position_size_usd or 0,
                "leverage": getattr(t, "leverage", 1.0) or 1.0,
            }
            for t in trades
        ]

    def _empty(self, reason: str) -> dict:
        return {
            "total_trades": 0,
            "cost_model": "realistic",
            "economic_audit": {"verdict": reason},
            "usefulness_audit": {"verdict": reason},
            "pnl_bucket_distribution": {},
            "signal_exit_audit": {},
            "short_economics": {"verdict": reason},
        }

