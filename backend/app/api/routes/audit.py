"""
Routes API pour l'audit de vérité et la gate v2.0.

Endpoints :
- GET /audit/truth : Audit complet de vérité des métriques
- GET /audit/scalping : Audit dédié du sous-système scalping
- GET /audit/costs : Presets de coûts disponibles
- GET /audit/costs/impact : Impact des coûts sur les trades existants
- GET /v2/readiness : Gate formelle de passage vers v2.0
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.truth_audit_service import TruthAuditService
from app.services.scalping_audit_service import ScalpingAuditService
from app.services.v2_gate_service import V2GateService
from app.services.trading_cost_service import (
    COST_PRESETS, get_cost_model,
)

router = APIRouter(tags=["Audit & Gate"])


@router.get("/audit/truth", summary="Audit de vérité complet")
def get_truth_audit(
    cost_preset: str = Query(
        default="realistic",
        description="Preset de coûts : optimistic, realistic, stressed",
    ),
    db: Session = Depends(get_db),
):
    """
    Lance un audit complet de vérité sur le paper trading.

    Retourne :
    - Métriques brut/net avec 3 presets de coûts
    - Expectancy par type de sortie
    - Drawdown vérifié (recalculé vs stocké)
    - Performance par slot et par profil
    - Impact du trailing stop et du levier
    - Verdict global (DANGEROUS / FRAGILE / VIABLE / SOLID)
    """
    service = TruthAuditService(db)
    return service.run_audit(cost_preset=cost_preset)


@router.get("/audit/scalping", summary="Audit dédié scalping")
def get_scalping_audit(
    cost_preset: str = Query(
        default="realistic",
        description="Preset de coûts : optimistic, realistic, stressed",
    ),
    db: Session = Depends(get_db),
):
    """
    Audit ciblé du sous-système scalping.

    Retourne :
    - Métriques scalping brut/net (après coûts)
    - Distribution des sorties (trailing, stale, signal, etc.)
    - Audit du trailing stop
    - Distribution des scores d'entrée (saturation ?)
    - Comparaison long vs short
    - Impact du levier en scalping
    - Recommandations d'optimisation
    """
    service = ScalpingAuditService(db)
    return service.run_audit(cost_preset=cost_preset)


@router.get("/audit/costs", summary="Presets de coûts disponibles")
def get_cost_presets():
    """Retourne les presets de coûts de trading avec leurs paramètres."""
    presets = []
    for name, model in COST_PRESETS.items():
        presets.append({
            "name": model.name,
            "maker_fee_pct": model.maker_fee_pct,
            "taker_fee_pct": model.taker_fee_pct,
            "spread_pct": model.spread_pct,
            "slippage_pct": model.slippage_pct,
            "round_trip_cost_pct": round(model.round_trip_cost_pct(), 4),
            "entry_cost_pct": round(model.entry_cost_pct(), 4),
            "exit_cost_pct": round(model.exit_cost_pct(), 4),
        })
    return {"presets": presets}


@router.get("/v2/readiness", summary="Gate formelle v2.0")
def check_v2_readiness(
    db: Session = Depends(get_db),
):
    """
    Évalue si le système est prêt pour le passage en mode autonome v2.0.

    Retourne un verdict READY / PARTIAL / NOT_READY basé sur des
    critères objectifs et mesurables.
    """
    service = V2GateService(db)
    return service.check_readiness()

