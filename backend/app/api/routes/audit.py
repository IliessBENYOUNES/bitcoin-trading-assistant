"""
Routes API pour l'audit de vérité et la gate v2.0.

Endpoints :
- GET /audit/truth : Audit complet de vérité des métriques
- GET /audit/scalping : Audit dédié du sous-système scalping
- GET /audit/costs : Presets de coûts disponibles
- GET /audit/costs/impact : Impact des coûts sur les trades existants
- GET /v2/readiness : Gate formelle de passage vers v2.0
- GET /audit/enriched-export : Export enrichi tick-par-tick avec corrélation BTC
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.truth_audit_service import TruthAuditService
from app.services.scalping_audit_service import ScalpingAuditService
from app.services.v2_gate_service import V2GateService
from app.services.run_value_audit_service import RunValueAuditService
from app.services.stability_audit_service import StabilityAuditService
from app.services.runtime_correlation_service import RuntimeCorrelationService
from app.services.enriched_export_service import EnrichedExportService
from app.services.trading_cost_service import (
    COST_PRESETS, get_cost_model,
)
from app.schemas.enriched_export import EnrichedExportResponse

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


@router.get("/audit/run-value", summary="Audit de valeur économique du run")
def get_run_value_audit(
    cost_preset: str = Query(
        default="realistic",
        description="Preset de coûts : optimistic, realistic, stressed",
    ),
    db: Session = Depends(get_db),
):
    """
    Audit de valeur économique du run paper trading.

    Diagnostic approfondi de la valeur capturée par trade :
    - Métriques brut/net complètes
    - Répartition useful / insignificant / churn
    - Distribution par bucket de PnL
    - Audit de la sortie "signal contraire" sur les shorts
    - Économie du short scalping
    """
    service = RunValueAuditService(db)
    return service.run_audit(cost_preset=cost_preset)


@router.get("/audit/stability", summary="Audit de stabilité du moteur")
def get_stability_audit(
    window: int = Query(
        default=20,
        description="Nombre de trades récents à analyser",
    ),
    db: Session = Depends(get_db),
):
    """
    Diagnostic de stabilité du moteur de trading.

    Détecte les patterns d'oscillation entre surcorrections :
    - Balance directionnelle (long/short ratio)
    - Homogénéité des scores d'entrée
    - Ratio gain/perte effectif vs théorique
    - Domination d'un type de sortie
    - Oscillation entre fenêtres de trades
    - Verdict : UNSTABLE / IMPROVING / STABLE
    """
    service = StabilityAuditService(db)
    return service.run_audit(window_size=window)


@router.get("/audit/runtime-correlation", summary="Corrélation runtime trades vs BTC")
def get_runtime_correlation(
    symbol: str = Query(
        default="BTC/USD",
        description="Symbole BTC (ex: BTC/USD)",
    ),
    missed_threshold_pct: float = Query(
        default=0.15,
        ge=0.01,
        le=5.0,
        description="Seuil minimum de mouvement BTC pour qualifier un 'missed movement' (%)",
    ),
    db: Session = Depends(get_db),
):
    """
    Corrélation runtime : chaque trade vs mouvement BTC réel.

    Retourne :
    - Chaque trade enrichi avec le contexte BTC (trend à l'entrée, mouvement pendant/après)
    - Mouvements BTC significatifs ratés (aucun trade ouvert)
    - Efficacité de capture globale (% du mouvement BTC monétisé)
    - Identification des sorties stale prématurées
    - Verdicts : stale, capture, timing
    """
    service = RuntimeCorrelationService(db)
    return service.build_correlation(
        symbol=symbol,
        missed_threshold_pct=missed_threshold_pct,
    )


@router.get(
    "/audit/enriched-export",
    response_model=EnrichedExportResponse,
    summary="Export enrichi tick-par-tick",
)
def get_enriched_export(
    profile_type: str = Query(
        default=None,
        description="Filtrer par profil (scalping, aggressive, etc.). None = tous.",
    ),
    limit: int = Query(
        default=5000,
        ge=1,
        le=50000,
        description="Nombre max de ticks à retourner",
    ),
    missed_threshold_pct: float = Query(
        default=0.15,
        ge=0.01,
        le=5.0,
        description="Seuil minimum de mouvement BTC pour qualifier une tendance ratée (%)",
    ),
    db: Session = Depends(get_db),
):
    """
    Export enrichi tick-par-tick avec corrélation BTC et analyse des gates.

    Retourne :
    - Chaque tick avec contexte complet (prix BTC, décision, score, raison de non-trade)
    - Événements de trade (entrée/sortie/PnL)
    - Ventilation des refus par gate (quel paramètre bloque le plus)
    - Détection des tendances BTC ratées (le moteur ne trade pas mais BTC bouge)
    - Indicateurs de mouvement raté par tick

    Conçu pour l'analyse minute-par-minute de la corrélation
    entre les décisions du moteur et le mouvement BTC réel.
    """
    service = EnrichedExportService(db)
    return service.build_export(
        profile_type=profile_type,
        limit=limit,
        missed_threshold_pct=missed_threshold_pct,
    )

