"""
Service d'audit de vérité — Analyse honnête des métriques de trading.

Ce service calcule des métriques objectives pour évaluer la qualité réelle
du système de paper trading. Il ne maquille rien. Il ne flatte rien.

L'audit couvre :
- Expectancy brute et nette (après coûts)
- Drawdown vérifié (capital réalisé + equity latent si possible)
- Performance par slot (balanced vs scalping vs aggressive)
- Performance par profil
- Impact du trailing stop
- Impact du levier auto
- Verdict global (DANGEROUS / FRAGILE / VIABLE / SOLID)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.paper_account import PaperAccount, PaperTrade
from app.services.trading_cost_service import (
    TradingCostModel, COST_REALISTIC, COST_OPTIMISTIC, COST_STRESSED,
    get_cost_model, COST_PRESETS,
)

logger = logging.getLogger(__name__)


class TruthAuditService:
    """
    Service d'audit de vérité.

    Usage :
        service = TruthAuditService(db_session)
        result = service.run_audit()
    """

    def __init__(self, db: Session):
        self.db = db

    def run_audit(self, cost_preset: str = "realistic") -> dict:
        """
        Lance un audit complet de vérité.

        Returns:
            dict avec toutes les sections d'audit et un verdict global.
        """
        account = self.db.query(PaperAccount).first()
        if account is None:
            return self._empty_audit("Aucun compte paper trading trouvé", cost_preset)

        closed_trades = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.account_id == account.id)
            .filter(PaperTrade.status != "open")
            .order_by(PaperTrade.exit_ts.asc())
            .all()
        )

        if not closed_trades:
            return self._empty_audit("Aucun trade fermé trouvé", cost_preset)

        cost_model = get_cost_model(cost_preset)

        # Convertir les trades en dicts pour le cost model
        trade_dicts = self._trades_to_dicts(closed_trades)

        # 1. Audit des coûts (brut/net)
        cost_audit = self._audit_costs(trade_dicts, cost_model)

        # 2. Audit de l'expectancy
        expectancy_audit = self._audit_expectancy(trade_dicts, cost_model)

        # 3. Audit du drawdown
        drawdown_audit = self._audit_drawdown(closed_trades, account, cost_model)

        # 4. Audit par slot
        slot_audit = self._audit_by_slot(trade_dicts, cost_model)

        # 5. Audit par profil
        profile_audit = self._audit_by_profile(trade_dicts, cost_model)

        # 6. Audit trailing stop
        trailing_audit = self._audit_trailing_stop(closed_trades, cost_model)

        # 7. Audit levier
        leverage_audit = self._audit_leverage(closed_trades, cost_model)

        # 8. Verdict global
        verdict = self._compute_verdict(
            cost_audit, expectancy_audit, drawdown_audit,
            slot_audit, profile_audit, trailing_audit, leverage_audit,
            len(closed_trades),
        )

        return {
            "account_id": account.id,
            "total_closed_trades": len(closed_trades),
            "cost_model_used": cost_preset,
            "cost_audit": cost_audit,
            "expectancy_audit": expectancy_audit,
            "drawdown_audit": drawdown_audit,
            "slot_audit": slot_audit,
            "profile_audit": profile_audit,
            "trailing_stop_audit": trailing_audit,
            "leverage_audit": leverage_audit,
            "verdict": verdict,
        }

    def _trades_to_dicts(self, trades: list[PaperTrade]) -> list[dict]:
        """Convertit les trades SQLAlchemy en dicts pour le cost model."""
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
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
            })
        return result

    def _audit_costs(self, trades: list[dict], cost_model: TradingCostModel) -> dict:
        """Audit des coûts : brut vs net avec tous les presets."""
        results = {}
        for name, model in COST_PRESETS.items():
            metrics = model.apply_to_trades(trades)
            results[name] = {
                "gross_pnl": metrics["gross_pnl"],
                "total_costs": metrics["total_costs"],
                "net_pnl": metrics["net_pnl"],
                "cost_drag_pct": metrics["cost_drag_pct"],
                "round_trip_cost_pct": model.round_trip_cost_pct(),
            }

        # Résumé principal avec le preset demandé
        main = cost_model.apply_to_trades(trades)
        return {
            "primary": main,
            "all_presets": results,
            "warning": self._cost_warning(main),
        }

    def _cost_warning(self, metrics: dict) -> Optional[str]:
        """Génère un avertissement si les coûts sont problématiques."""
        if metrics["gross_pnl"] > 0 and metrics["net_pnl"] <= 0:
            return "DANGER: Le PnL brut est positif mais le PnL net est négatif après coûts. Les coûts dépassent les gains."
        if metrics["gross_pnl"] > 0 and metrics["total_costs"] > metrics["gross_pnl"] * 0.5:
            return "WARNING: Les coûts consomment plus de 50% du PnL brut."
        if metrics["cost_drag_pct"] > 1.0:
            return "WARNING: Le drag des coûts dépasse 1% du capital total tradé."
        return None

    def _audit_expectancy(self, trades: list[dict], cost_model: TradingCostModel) -> dict:
        """Audit complet de l'expectancy."""
        metrics = cost_model.apply_to_trades(trades)

        # Expectancy par type de sortie
        exit_types = {}
        for t in trades:
            status = t.get("status", "unknown")
            if status not in exit_types:
                exit_types[status] = []
            exit_types[status].append(t)

        by_exit_type = {}
        for status, group in exit_types.items():
            group_metrics = cost_model.apply_to_trades(group)
            by_exit_type[status] = {
                "count": len(group),
                "gross_expectancy": group_metrics["gross_expectancy"],
                "net_expectancy": group_metrics["net_expectancy"],
                "gross_pnl": group_metrics["gross_pnl"],
                "net_pnl": group_metrics["net_pnl"],
            }

        return {
            "gross_expectancy_per_trade": metrics["gross_expectancy"],
            "net_expectancy_per_trade": metrics["net_expectancy"],
            "gross_profit_factor": metrics["gross_profit_factor"],
            "net_profit_factor": metrics["net_profit_factor"],
            "gross_win_rate": metrics["gross_win_rate"],
            "net_win_rate": metrics["net_win_rate"],
            "by_exit_type": by_exit_type,
            "is_positive_net": metrics["net_expectancy"] > 0,
        }

    def _audit_drawdown(self, trades: list[PaperTrade], account: PaperAccount,
                         cost_model: TradingCostModel) -> dict:
        """
        Audit du drawdown — vérifie la cohérence du calcul.

        Recalcule le drawdown à partir de l'equity curve des trades fermés,
        en intégrant les coûts pour le drawdown net.
        """
        initial = account.initial_capital
        gross_equity = initial
        net_equity = initial
        gross_peak = initial
        net_peak = initial
        max_gross_dd = 0
        max_net_dd = 0
        worst_gross_dd_start = None
        worst_gross_dd_end = None

        for trade in trades:
            pnl = trade.pnl or 0
            size = trade.position_size_usd or 0
            lev = getattr(trade, "leverage", 1.0) or 1.0

            # Brut
            gross_equity += pnl
            if gross_equity > gross_peak:
                gross_peak = gross_equity
            gross_dd = (gross_peak - gross_equity) / gross_peak * 100 if gross_peak > 0 else 0
            if gross_dd > max_gross_dd:
                max_gross_dd = gross_dd

            # Net
            cost = cost_model.round_trip_cost_usd(size * lev)
            net_equity += (pnl - cost)
            if net_equity > net_peak:
                net_peak = net_equity
            net_dd = (net_peak - net_equity) / net_peak * 100 if net_peak > 0 else 0
            if net_dd > max_net_dd:
                max_net_dd = net_dd

        # Comparer avec le drawdown stocké dans le compte
        stored_dd = account.max_drawdown_pct or 0
        dd_coherent = abs(max_gross_dd - stored_dd) < 1.0  # tolérance 1%

        return {
            "gross_max_drawdown_pct": round(max_gross_dd, 2),
            "net_max_drawdown_pct": round(max_net_dd, 2),
            "stored_drawdown_pct": round(stored_dd, 2),
            "drawdown_coherent": dd_coherent,
            "final_gross_equity": round(gross_equity, 2),
            "final_net_equity": round(net_equity, 2),
            "initial_capital": initial,
        }

    def _audit_by_slot(self, trades: list[dict], cost_model: TradingCostModel) -> dict:
        """Audit par slot : quel slot est profitable vs destructeur."""
        slots = {}
        for t in trades:
            slot = t.get("slot") or "default"
            if slot not in slots:
                slots[slot] = []
            slots[slot].append(t)

        result = {}
        for slot_name, group in slots.items():
            metrics = cost_model.apply_to_trades(group)
            avg_duration = sum(t.get("duration_hours", 0) for t in group) / len(group) if group else 0
            result[slot_name] = {
                "count": len(group),
                "gross_pnl": metrics["gross_pnl"],
                "net_pnl": metrics["net_pnl"],
                "total_costs": metrics["total_costs"],
                "gross_expectancy": metrics["gross_expectancy"],
                "net_expectancy": metrics["net_expectancy"],
                "gross_win_rate": metrics["gross_win_rate"],
                "net_win_rate": metrics["net_win_rate"],
                "avg_duration_hours": round(avg_duration, 2),
                "is_net_profitable": metrics["net_pnl"] > 0,
            }

        return result

    def _audit_by_profile(self, trades: list[dict], cost_model: TradingCostModel) -> dict:
        """Audit par profil de trading."""
        profiles = {}
        for t in trades:
            profile = t.get("profile_type") or "unknown"
            # Normaliser les profils auto→xxx
            if profile.startswith("auto"):
                profile = "auto"
            if profile not in profiles:
                profiles[profile] = []
            profiles[profile].append(t)

        result = {}
        for profile_name, group in profiles.items():
            metrics = cost_model.apply_to_trades(group)
            avg_duration = sum(t.get("duration_hours", 0) for t in group) / len(group) if group else 0
            result[profile_name] = {
                "count": len(group),
                "gross_pnl": metrics["gross_pnl"],
                "net_pnl": metrics["net_pnl"],
                "total_costs": metrics["total_costs"],
                "gross_expectancy": metrics["gross_expectancy"],
                "net_expectancy": metrics["net_expectancy"],
                "gross_win_rate": metrics["gross_win_rate"],
                "net_win_rate": metrics["net_win_rate"],
                "avg_duration_hours": round(avg_duration, 2),
                "is_net_profitable": metrics["net_pnl"] > 0,
            }

        return result

    def _audit_trailing_stop(self, trades: list[PaperTrade],
                              cost_model: TradingCostModel) -> dict:
        """Audit du trailing stop : protège-t-il réellement les gains ?"""
        trailing_trades = [t for t in trades if t.status == "closed_trailing_stop"]
        other_trades = [t for t in trades if t.status != "closed_trailing_stop"]

        if not trailing_trades:
            return {
                "trailing_count": 0,
                "other_count": len(other_trades),
                "trailing_used": False,
                "verdict": "Trailing stop non utilisé — impossible d'évaluer.",
            }

        trailing_dicts = self._trades_to_dicts(trailing_trades)
        other_dicts = self._trades_to_dicts(other_trades)

        t_metrics = cost_model.apply_to_trades(trailing_dicts)
        o_metrics = cost_model.apply_to_trades(other_dicts) if other_dicts else {}

        # Le trailing stop protège les gains si le PnL moyen des trades trailing
        # est supérieur au PnL moyen des autres types de fermeture
        trailing_avg = t_metrics["net_avg_trade"] if t_metrics else 0
        other_avg = o_metrics.get("net_avg_trade", 0)

        protects = trailing_avg > 0
        cuts_too_early = trailing_avg < other_avg and other_avg > 0

        verdict = "Le trailing stop "
        if protects and not cuts_too_early:
            verdict += "protège effectivement les gains (PnL moyen net positif)."
        elif protects and cuts_too_early:
            verdict += "protège les gains mais coupe potentiellement trop tôt (PnL moyen inférieur aux autres sorties)."
        elif not protects:
            verdict += "ne protège PAS les gains — PnL moyen net négatif. À reconfigurer."

        return {
            "trailing_count": len(trailing_trades),
            "other_count": len(other_trades),
            "trailing_used": True,
            "trailing_net_avg": round(trailing_avg, 4),
            "other_net_avg": round(other_avg, 4),
            "trailing_net_pnl": t_metrics["net_pnl"],
            "trailing_win_rate": t_metrics["net_win_rate"],
            "protects_gains": protects,
            "cuts_too_early": cuts_too_early,
            "verdict": verdict,
        }

    def _audit_leverage(self, trades: list[PaperTrade],
                         cost_model: TradingCostModel) -> dict:
        """Audit du levier auto : améliore-t-il le net ou juste le risque ?"""
        leveraged = [t for t in trades if (getattr(t, "leverage", 1.0) or 1.0) > 1.0]
        unleveraged = [t for t in trades if (getattr(t, "leverage", 1.0) or 1.0) <= 1.0]

        if not leveraged:
            return {
                "leveraged_count": 0,
                "unleveraged_count": len(unleveraged),
                "leverage_used": False,
                "verdict": "Levier non utilisé — impossible d'évaluer.",
            }

        lev_dicts = self._trades_to_dicts(leveraged)
        unlev_dicts = self._trades_to_dicts(unleveraged)

        l_metrics = cost_model.apply_to_trades(lev_dicts)
        u_metrics = cost_model.apply_to_trades(unlev_dicts) if unlev_dicts else {}

        # Calculer le PnL des trades levés SANS le levier (comme si levier=1)
        lev_as_x1 = []
        for t in leveraged:
            leverage = getattr(t, "leverage", 1.0) or 1.0
            # PnL brut sans levier = PnL brut / levier
            pnl_without_lev = (t.pnl or 0) / leverage if leverage > 0 else 0
            lev_as_x1.append({
                "pnl": pnl_without_lev,
                "position_size_usd": t.position_size_usd or 0,
                "leverage": 1.0,
            })
        lev_x1_metrics = cost_model.apply_to_trades(lev_as_x1)

        lev_net_benefit = l_metrics["net_pnl"] - lev_x1_metrics["net_pnl"]
        lev_improves_net = lev_net_benefit > 0

        avg_leverage = sum((getattr(t, "leverage", 1.0) or 1.0) for t in leveraged) / len(leveraged)

        verdict = f"Levier moyen x{avg_leverage:.1f}. "
        if lev_improves_net:
            verdict += f"Le levier améliore le PnL net de +{lev_net_benefit:.2f} USD."
        else:
            verdict += f"Le levier DÉGRADE le PnL net de {lev_net_benefit:.2f} USD. À reconsidérer."

        return {
            "leveraged_count": len(leveraged),
            "unleveraged_count": len(unleveraged),
            "leverage_used": True,
            "avg_leverage": round(avg_leverage, 2),
            "leveraged_net_pnl": l_metrics["net_pnl"],
            "leveraged_as_x1_net_pnl": lev_x1_metrics["net_pnl"],
            "leverage_net_benefit": round(lev_net_benefit, 2),
            "leveraged_net_expectancy": l_metrics["net_expectancy"],
            "leveraged_net_win_rate": l_metrics["net_win_rate"],
            "improves_net": lev_improves_net,
            "verdict": verdict,
        }

    def _compute_verdict(self, cost_audit, expectancy_audit, drawdown_audit,
                          slot_audit, profile_audit, trailing_audit, leverage_audit,
                          total_trades: int) -> dict:
        """
        Calcule un verdict global : DANGEROUS / FRAGILE / VIABLE / SOLID.

        Le score est sur 100 :
        - < 25 : DANGEROUS — Le système perd de l'argent net
        - 25-49 : FRAGILE — Le système est marginalement viable
        - 50-74 : VIABLE — Le système est fonctionnel mais perfectible
        - 75-100 : SOLID — Le système est prêt pour validation prolongée
        """
        score = 0
        reasons = []

        # 1. Expectancy nette > 0 (30 points max)
        net_exp = expectancy_audit.get("net_expectancy_per_trade", 0)
        if net_exp > 0:
            score += 30
        elif net_exp > -0.5:
            score += 10
            reasons.append(f"Expectancy nette marginale ({net_exp:.2f})")
        else:
            reasons.append(f"Expectancy nette NÉGATIVE ({net_exp:.2f})")

        # 2. Drawdown raisonnable (20 points max)
        net_dd = drawdown_audit.get("net_max_drawdown_pct", 100)
        if net_dd < 10:
            score += 20
        elif net_dd < 20:
            score += 10
            reasons.append(f"Drawdown net élevé ({net_dd:.1f}%)")
        else:
            reasons.append(f"Drawdown net CRITIQUE ({net_dd:.1f}%)")

        # 3. Profit factor net > 1 (15 points max)
        net_pf = expectancy_audit.get("net_profit_factor", 0)
        if net_pf > 1.5:
            score += 15
        elif net_pf > 1.0:
            score += 8
        else:
            reasons.append(f"Profit factor net < 1 ({net_pf:.2f})")

        # 4. Win rate net > 40% (10 points max)
        net_wr = expectancy_audit.get("net_win_rate", 0)
        if net_wr >= 50:
            score += 10
        elif net_wr >= 40:
            score += 5
        else:
            reasons.append(f"Win rate net faible ({net_wr:.1f}%)")

        # 5. Nombre de trades suffisant (10 points max)
        if total_trades >= 50:
            score += 10
        elif total_trades >= 20:
            score += 5
            reasons.append(f"Échantillon modeste ({total_trades} trades)")
        else:
            reasons.append(f"Échantillon INSUFFISANT ({total_trades} trades)")

        # 6. Trailing stop / Levier (15 points max)
        if trailing_audit.get("protects_gains"):
            score += 5
        if leverage_audit.get("improves_net"):
            score += 5
        if not leverage_audit.get("leverage_used", False) or leverage_audit.get("improves_net"):
            score += 5  # Bonus si pas de levier OU si le levier est bénéfique

        # Classification
        if score >= 75:
            label = "SOLID"
        elif score >= 50:
            label = "VIABLE"
        elif score >= 25:
            label = "FRAGILE"
        else:
            label = "DANGEROUS"

        return {
            "score": score,
            "label": label,
            "reasons": reasons if reasons else ["Aucun problème majeur détecté"],
            "net_expectancy": round(net_exp, 4),
            "net_drawdown_pct": round(net_dd, 2),
            "net_profit_factor": round(net_pf, 2),
            "net_win_rate": round(net_wr, 2),
            "total_trades": total_trades,
        }

    def _empty_audit(self, reason: str, cost_preset: str = "realistic") -> dict:
        """Retourne un audit vide avec une raison."""
        return {
            "account_id": None,
            "total_closed_trades": 0,
            "cost_model_used": cost_preset,
            "cost_audit": {},
            "expectancy_audit": {},
            "drawdown_audit": {},
            "slot_audit": {},
            "profile_audit": {},
            "trailing_stop_audit": {},
            "leverage_audit": {},
            "verdict": {
                "score": 0,
                "label": "NOT_READY",
                "reasons": [reason],
                "net_expectancy": 0,
                "net_drawdown_pct": 0,
                "net_profit_factor": 0,
                "net_win_rate": 0,
                "total_trades": 0,
            },
        }

