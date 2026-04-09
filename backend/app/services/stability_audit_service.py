"""
StabilityAuditService — Détection d'oscillation et diagnostic de convergence.

Le moteur scalping a montré une tendance à osciller entre surcorrections :
- v1.9.3 : trop de shorts → pertes
- v1.9.4 : correction → quasi aucun short → excès long → pertes
- v1.9.5 : stabilisation globale

Ce service détecte les patterns d'instabilité et produit un verdict de stabilité.

Métriques :
1. Direction balance — ratio long/short et flip detection
2. Score homogeneity — écart-type des scores d'entrée
3. Effective R:R — ratio gain moyen / perte moyenne réel
4. Exit type domination — une sortie trop dominante = problème
5. Stability verdict — UNSTABLE / IMPROVING / STABLE

v1.9.5
"""

import logging
import math
from collections import Counter, defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paper_account import PaperAccount, PaperTrade

logger = logging.getLogger(__name__)


class StabilityAuditService:
    """
    Audit de stabilité du moteur de trading.

    Usage :
        service = StabilityAuditService(db_session)
        result = service.run_audit()
    """

    def __init__(self, db: Session):
        self.db = db

    def run_audit(self, window_size: int = 20) -> dict:
        """
        Audit complet de stabilité.

        Args:
            window_size: nombre de trades récents à analyser.
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

        if len(all_closed) < 5:
            return self._empty(f"Pas assez de trades fermés ({len(all_closed)}/5 min)")

        # Fenêtre d'analyse
        recent = all_closed[-window_size:] if len(all_closed) > window_size else all_closed

        # 1. Direction balance
        direction_balance = self._direction_balance(recent)

        # 2. Score homogeneity
        score_homogeneity = self._score_homogeneity(recent)

        # 3. Effective R:R
        effective_rr = self._effective_rr(recent)

        # 4. Exit type domination
        exit_domination = self._exit_type_domination(recent)

        # 5. Gain/Loss asymmetry
        gain_loss = self._gain_loss_analysis(recent)

        # 6. Oscillation detection (si assez de trades, comparer 2 fenêtres)
        oscillation = self._detect_oscillation(all_closed, window_size)

        # 7. Verdict de stabilité global
        verdict = self._compute_verdict(
            direction_balance, score_homogeneity, effective_rr,
            exit_domination, gain_loss, oscillation,
        )

        return {
            "total_closed_trades": len(all_closed),
            "analysis_window": len(recent),
            "direction_balance": direction_balance,
            "score_homogeneity": score_homogeneity,
            "effective_rr": effective_rr,
            "exit_domination": exit_domination,
            "gain_loss_analysis": gain_loss,
            "oscillation_detection": oscillation,
            "verdict": verdict,
        }

    # ================================================================
    # 1. DIRECTION BALANCE
    # ================================================================

    def _direction_balance(self, trades: list) -> dict:
        """Analyse l'équilibre long/short."""
        longs = [t for t in trades if t.direction == "long"]
        shorts = [t for t in trades if t.direction == "short"]
        total = len(trades)

        long_pct = round(len(longs) / total * 100, 1) if total else 0
        short_pct = round(len(shorts) / total * 100, 1) if total else 0

        # PnL par direction
        long_pnl = sum(t.pnl or 0 for t in longs)
        short_pnl = sum(t.pnl or 0 for t in shorts)

        if long_pct >= 90:
            status = "mono_long"
        elif short_pct >= 90:
            status = "mono_short"
        elif long_pct >= 75:
            status = "long_biased"
        elif short_pct >= 75:
            status = "short_biased"
        else:
            status = "balanced"

        return {
            "long_count": len(longs),
            "short_count": len(shorts),
            "long_pct": long_pct,
            "short_pct": short_pct,
            "long_total_pnl": round(long_pnl, 2),
            "short_total_pnl": round(short_pnl, 2),
            "status": status,
        }

    # ================================================================
    # 2. SCORE HOMOGENEITY
    # ================================================================

    def _score_homogeneity(self, trades: list) -> dict:
        """Analyse l'homogénéité des scores d'entrée."""
        scores = [abs(t.decision_score) for t in trades if t.decision_score is not None]
        if not scores:
            return {"std_dev": 0, "mean": 0, "min": 0, "max": 0, "status": "no_data"}

        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std_dev = math.sqrt(variance)
        score_range = max(scores) - min(scores)

        if std_dev < 3:
            status = "very_homogeneous"
        elif std_dev < 8:
            status = "moderately_homogeneous"
        else:
            status = "well_distributed"

        return {
            "mean": round(mean, 1),
            "std_dev": round(std_dev, 1),
            "min": min(scores),
            "max": max(scores),
            "range": score_range,
            "status": status,
        }

    # ================================================================
    # 3. EFFECTIVE R:R
    # ================================================================

    def _effective_rr(self, trades: list) -> dict:
        """Calcule le ratio gain/perte effectif (R:R réel vs théorique)."""
        pnls = [t.pnl or 0 for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0
        effective_rr = round(avg_win / avg_loss, 2) if avg_loss > 0 else float("inf")

        # R:R théorique basé sur le profil (approximatif)
        theoretical_rr = 2.4  # 0.6% TP / 0.25% SL pour scalping v1.9.5

        if effective_rr >= 1.0:
            status = "healthy"
        elif effective_rr >= 0.5:
            status = "mediocre"
        else:
            status = "broken"

        return {
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "effective_rr": effective_rr if effective_rr != float("inf") else 999,
            "theoretical_rr": theoretical_rr,
            "rr_gap": round(theoretical_rr - effective_rr, 2) if effective_rr != float("inf") else 0,
            "status": status,
        }

    # ================================================================
    # 4. EXIT TYPE DOMINATION
    # ================================================================

    def _exit_type_domination(self, trades: list) -> dict:
        """Détecte si un type de sortie domine excessivement."""
        exit_counts = Counter(t.status for t in trades if t.status != "open")
        total = len(trades)

        distribution = {}
        for exit_type, count in exit_counts.most_common():
            pnl_group = [t.pnl or 0 for t in trades if t.status == exit_type]
            avg_pnl = sum(pnl_group) / len(pnl_group) if pnl_group else 0
            distribution[exit_type] = {
                "count": count,
                "pct": round(count / total * 100, 1) if total else 0,
                "avg_pnl": round(avg_pnl, 2),
                "is_destructive": avg_pnl < -1.0,
            }

        # Sortie la plus fréquente
        dominant = exit_counts.most_common(1)[0] if exit_counts else ("none", 0)
        dominant_pct = dominant[1] / total * 100 if total else 0

        if dominant_pct >= 50:
            status = "over_dominant"
        elif dominant_pct >= 35:
            status = "slightly_dominant"
        else:
            status = "diverse"

        # Sorties destructrices (PnL moyen < -1.0)
        destructive_exits = [
            k for k, v in distribution.items()
            if v.get("is_destructive")
        ]

        return {
            "distribution": distribution,
            "dominant_exit": dominant[0],
            "dominant_pct": round(dominant_pct, 1),
            "destructive_exits": destructive_exits,
            "status": status,
        }

    # ================================================================
    # 5. GAIN/LOSS ANALYSIS
    # ================================================================

    def _gain_loss_analysis(self, trades: list) -> dict:
        """Analyse détaillée du ratio gain/perte."""
        pnls = [t.pnl or 0 for t in trades]
        wins = sorted([p for p in pnls if p > 0], reverse=True)
        losses = sorted([p for p in pnls if p < 0])

        # Médiane
        median_win = wins[len(wins) // 2] if wins else 0
        median_loss = losses[len(losses) // 2] if losses else 0

        # Top 3 pertes et leur contribution
        top3_losses = losses[:3]
        total_loss = abs(sum(losses))
        top3_contribution = round(
            abs(sum(top3_losses)) / total_loss * 100, 1
        ) if total_loss > 0 else 0

        # Profit factor
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999

        win_rate = round(len(wins) / len(pnls) * 100, 1) if pnls else 0

        # Verdict
        if profit_factor >= 1.5:
            status = "healthy"
        elif profit_factor >= 1.0:
            status = "breakeven"
        elif profit_factor >= 0.5:
            status = "mediocre"
        else:
            status = "broken"

        return {
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": win_rate,
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
            "median_win": round(median_win, 2),
            "median_loss": round(median_loss, 2),
            "top3_losses": [round(p, 2) for p in top3_losses],
            "top3_loss_contribution_pct": top3_contribution,
            "profit_factor": profit_factor,
            "status": status,
        }

    # ================================================================
    # 6. OSCILLATION DETECTION
    # ================================================================

    def _detect_oscillation(self, all_trades: list, window: int) -> dict:
        """
        Compare les 2 dernières fenêtres de N trades pour détecter une oscillation.

        Oscillation = la direction majoritaire s'inverse entre 2 fenêtres.
        Exemple : fenêtre 1 = 80% short, fenêtre 2 = 80% long → oscillation.
        """
        if len(all_trades) < window * 2:
            return {
                "detected": False,
                "reason": f"Pas assez de trades pour comparer 2 fenêtres ({len(all_trades)}/{window * 2})",
            }

        # Fenêtre récente
        recent = all_trades[-window:]
        # Fenêtre précédente
        previous = all_trades[-window * 2:-window]

        recent_longs = sum(1 for t in recent if t.direction == "long")
        recent_shorts = sum(1 for t in recent if t.direction == "short")
        prev_longs = sum(1 for t in previous if t.direction == "long")
        prev_shorts = sum(1 for t in previous if t.direction == "short")

        recent_long_pct = recent_longs / len(recent) * 100
        prev_long_pct = prev_longs / len(previous) * 100

        # Oscillation = flip de direction dominante
        recent_dominant = "long" if recent_long_pct >= 60 else ("short" if recent_long_pct <= 40 else "mixed")
        prev_dominant = "long" if prev_long_pct >= 60 else ("short" if prev_long_pct <= 40 else "mixed")

        flip = (recent_dominant == "long" and prev_dominant == "short") or \
               (recent_dominant == "short" and prev_dominant == "long")

        # PnL par fenêtre
        recent_pnl = sum(t.pnl or 0 for t in recent)
        prev_pnl = sum(t.pnl or 0 for t in previous)

        return {
            "detected": flip,
            "previous_window": {
                "long_pct": round(prev_long_pct, 1),
                "dominant": prev_dominant,
                "total_pnl": round(prev_pnl, 2),
            },
            "recent_window": {
                "long_pct": round(recent_long_pct, 1),
                "dominant": recent_dominant,
                "total_pnl": round(recent_pnl, 2),
            },
            "reason": (
                f"Direction flip: {prev_dominant} → {recent_dominant}"
                if flip else "Pas d'oscillation directionnelle détectée"
            ),
        }

    # ================================================================
    # 7. VERDICT DE STABILITÉ
    # ================================================================

    def _compute_verdict(
        self, direction, score_homog, rr, exit_dom, gain_loss, oscillation,
    ) -> dict:
        """
        Produit un verdict global de stabilité.

        Score de stabilité 0-100 :
        - < 30 : UNSTABLE
        - 30-60 : IMPROVING
        - > 60 : STABLE
        """
        score = 100  # On part de 100 et on enlève des points
        issues = []

        # Direction balance
        if direction["status"] in ("mono_long", "mono_short"):
            score -= 30
            issues.append(f"Direction mono-{direction['status'].split('_')[1]} ({direction['long_pct']}% long)")
        elif direction["status"] in ("long_biased", "short_biased"):
            score -= 15
            issues.append(f"Biais directionnel : {direction['status']}")

        # Score homogeneity
        if score_homog.get("status") == "very_homogeneous":
            score -= 20
            issues.append(f"Scores très homogènes (σ={score_homog.get('std_dev', 0)})")
        elif score_homog.get("status") == "moderately_homogeneous":
            score -= 10
            issues.append(f"Scores modérément homogènes (σ={score_homog.get('std_dev', 0)})")

        # R:R
        if rr.get("status") == "broken":
            score -= 25
            issues.append(f"R:R cassé ({rr.get('effective_rr', 0)}:1)")
        elif rr.get("status") == "mediocre":
            score -= 12
            issues.append(f"R:R médiocre ({rr.get('effective_rr', 0)}:1)")

        # Exit domination
        if exit_dom.get("status") == "over_dominant":
            score -= 15
            issues.append(f"Sortie sur-dominante : {exit_dom.get('dominant_exit')} ({exit_dom.get('dominant_pct')}%)")
        if exit_dom.get("destructive_exits"):
            score -= 10
            issues.append(f"Sorties destructrices : {', '.join(exit_dom['destructive_exits'])}")

        # Gain/Loss
        if gain_loss.get("status") == "broken":
            score -= 20
            issues.append(f"Profit factor cassé ({gain_loss.get('profit_factor', 0)})")
        elif gain_loss.get("status") == "mediocre":
            score -= 10
            issues.append(f"Profit factor médiocre ({gain_loss.get('profit_factor', 0)})")

        # Oscillation
        if oscillation.get("detected"):
            score -= 15
            issues.append("Oscillation directionnelle détectée entre 2 fenêtres")

        # Clamp
        score = max(0, score)

        # Verdict
        if score >= 60:
            level = "STABLE"
            summary = "Le moteur converge vers un comportement stable."
        elif score >= 30:
            level = "IMPROVING"
            summary = "Le moteur montre des signes d'amélioration mais des problèmes persistent."
        else:
            level = "UNSTABLE"
            summary = "Le moteur est instable — oscillations ou R:R cassé."

        return {
            "stability_score": score,
            "level": level,
            "summary": summary,
            "issues": issues,
            "issue_count": len(issues),
        }

    def _empty(self, reason: str) -> dict:
        return {
            "total_closed_trades": 0,
            "analysis_window": 0,
            "direction_balance": {},
            "score_homogeneity": {},
            "effective_rr": {},
            "exit_domination": {},
            "gain_loss_analysis": {},
            "oscillation_detection": {},
            "verdict": {
                "stability_score": 0,
                "level": "UNSTABLE",
                "summary": reason,
                "issues": [reason],
                "issue_count": 1,
            },
        }

