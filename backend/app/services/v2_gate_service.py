"""
Service de gate formelle v2.0 — Readiness check objectif.

Ce service évalue si le système est prêt pour le passage en mode autonome (v2.0).
Le verdict est basé sur des critères objectifs et mesurables, pas sur des impressions.

Le passage vers l'exécution réelle N'EST PAS décrété. Il est MÉRITÉ.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paper_account import PaperAccount, PaperTrade
from app.services.truth_audit_service import TruthAuditService

logger = logging.getLogger(__name__)


class V2GateService:
    """
    Service de vérification de readiness v2.0.

    Usage :
        service = V2GateService(db_session)
        result = service.check_readiness()
    """

    def __init__(self, db: Session):
        self.db = db

    def check_readiness(self) -> dict:
        """
        Évalue la readiness du système pour v2.0.

        Critères :
        1. Au moins 50 trades fermés
        2. Expectancy nette > 0 (cost model realistic)
        3. Max drawdown net < 15%
        4. Win rate net > 40%
        5. Profit factor net > 1.0
        6. Truth audit verdict ≥ VIABLE (score ≥ 50)
        7. Documentation à jour (vérification manuelle)
        8. Kill switch testé et fonctionnel (vérification manuelle)

        Returns:
            dict avec status READY/PARTIAL/NOT_READY, critères détaillés
        """
        # Lancer l'audit de vérité
        audit_service = TruthAuditService(self.db)
        audit = audit_service.run_audit(cost_preset="realistic")

        verdict = audit.get("verdict", {})
        expectancy = audit.get("expectancy_audit", {})
        drawdown = audit.get("drawdown_audit", {})

        # Évaluer chaque critère
        criteria = []

        # Critère 1 : Nombre de trades
        total_trades = audit.get("total_closed_trades", 0)
        criteria.append({
            "name": "Nombre minimum de trades",
            "passed": total_trades >= 50,
            "value": total_trades,
            "threshold": 50,
            "detail": f"{total_trades}/50 trades fermés",
        })

        # Critère 2 : Expectancy nette
        net_exp = expectancy.get("net_expectancy_per_trade", 0)
        criteria.append({
            "name": "Expectancy nette positive",
            "passed": net_exp > 0,
            "value": round(net_exp, 4),
            "threshold": 0,
            "detail": f"Expectancy nette = {net_exp:.4f} USD/trade (doit être > 0)",
        })

        # Critère 3 : Drawdown
        net_dd = drawdown.get("net_max_drawdown_pct", 100)
        criteria.append({
            "name": "Drawdown net < 15%",
            "passed": net_dd < 15,
            "value": round(net_dd, 2),
            "threshold": 15,
            "detail": f"Drawdown net max = {net_dd:.2f}% (doit être < 15%)",
        })

        # Critère 4 : Win rate
        net_wr = expectancy.get("net_win_rate", 0)
        criteria.append({
            "name": "Win rate net > 40%",
            "passed": net_wr > 40,
            "value": round(net_wr, 2),
            "threshold": 40,
            "detail": f"Win rate net = {net_wr:.2f}% (doit être > 40%)",
        })

        # Critère 5 : Profit factor
        net_pf = expectancy.get("net_profit_factor", 0)
        criteria.append({
            "name": "Profit factor net > 1.0",
            "passed": net_pf > 1.0,
            "value": round(net_pf, 2),
            "threshold": 1.0,
            "detail": f"Profit factor net = {net_pf:.2f} (doit être > 1.0)",
        })

        # Critère 6 : Verdict audit
        audit_score = verdict.get("score", 0)
        audit_label = verdict.get("label", "NOT_READY")
        criteria.append({
            "name": "Audit de vérité ≥ VIABLE",
            "passed": audit_score >= 50,
            "value": audit_score,
            "threshold": 50,
            "detail": f"Score audit = {audit_score}/100 ({audit_label})",
        })

        # Critère 7 : Documentation (auto-check basique)
        criteria.append({
            "name": "Documentation à jour",
            "passed": False,  # Toujours vérification manuelle
            "value": "manual_check",
            "threshold": "manual",
            "detail": "Vérification manuelle requise : CURRENT_STATE.md, ROADMAP.md cohérents",
        })

        # Critère 8 : Kill switch
        criteria.append({
            "name": "Kill switch fonctionnel",
            "passed": False,  # Toujours vérification manuelle
            "value": "manual_check",
            "threshold": "manual",
            "detail": "Vérification manuelle requise : POST /risk/kill-switch/activate bloque tous les trades",
        })

        # Calculer le score global
        auto_criteria = [c for c in criteria if c["value"] != "manual_check"]
        passed = sum(1 for c in auto_criteria if c["passed"])
        total = len(auto_criteria)

        if passed >= total:
            status = "READY"
        elif passed >= total * 0.6:
            status = "PARTIAL"
        else:
            status = "NOT_READY"

        blocking_reasons = [c["detail"] for c in criteria if not c["passed"]]

        return {
            "status": status,
            "score": f"{passed}/{total} critères auto-vérifiés passent",
            "criteria": criteria,
            "blocking_reasons": blocking_reasons,
            "audit_verdict": verdict,
            "recommendation": self._recommendation(status, blocking_reasons),
        }

    def _recommendation(self, status: str, blocking: list[str]) -> str:
        """Génère une recommandation textuelle."""
        if status == "READY":
            return (
                "Tous les critères objectifs sont satisfaits. "
                "Le système peut procéder à la phase v2.0 (mode fantôme d'abord, "
                "puis exécution réelle sous contrôle humain strict). "
                "Les critères manuels (documentation, kill switch) doivent être "
                "vérifiés par un humain avant de lancer."
            )
        elif status == "PARTIAL":
            return (
                f"Le système est partiellement prêt. "
                f"{len(blocking)} critère(s) bloquant(s) restent. "
                f"Prioriser : {'; '.join(blocking[:3])}"
            )
        else:
            return (
                f"Le système N'EST PAS prêt pour l'exécution réelle. "
                f"{len(blocking)} critère(s) bloquant(s). "
                f"Concentrer les efforts sur : {'; '.join(blocking[:3])}"
            )

