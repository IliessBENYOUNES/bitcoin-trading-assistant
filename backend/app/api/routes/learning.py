"""
Routes API Learning Layer — Apprentissage explicable.

Endpoints :
- GET  /learning/stats      — Statistiques du dataset
- GET  /learning/patterns    — Patterns identifiés
- POST /learning/analyze     — Analyse complète + suggestions
- GET  /learning/suggestions — Suggestions shadow
- POST /learning/promote/{id} — Promouvoir une suggestion
- POST /learning/rollback/{id} — Rollback un ajustement
- GET  /learning/versions    — Historique des versions
- GET  /learning/signals     — Échantillons d'apprentissage

v1.9.0
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.learning_service import LearningService
from app.services.paper_run_service import PaperRunService
from app.schemas.learning import (
    LearningDatasetStats,
    PatternInsight,
    LearningAnalysisResponse,
    StrategyFeedbackItem,
    LearningVersionHistory,
    LearningSignalItem,
)
from app.schemas.paper_run import (
    PaperRunCreate,
    PaperRunResponse,
    PaperRunMetrics,
    RunComparison,
)

router = APIRouter(prefix="/learning", tags=["Learning Layer"])


# ─────────────────────────────────────────────────────────────────────────────
# Dataset & Patterns
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=LearningDatasetStats)
def get_learning_stats(db: Session = Depends(get_db)):
    """Statistiques globales du dataset d'apprentissage."""
    svc = LearningService(db)
    return svc.get_dataset_stats()


@router.get("/patterns", response_model=list[PatternInsight])
def get_patterns(db: Session = Depends(get_db)):
    """Patterns identifiés (gagnants/perdants)."""
    svc = LearningService(db)
    return svc.analyze_patterns()


@router.post("/analyze", response_model=LearningAnalysisResponse)
def analyze_learning(
    profile_type: str = Query(default="scalping"),
    db: Session = Depends(get_db),
):
    """Analyse complète + génération de suggestions."""
    svc = LearningService(db)
    return svc.analyze(profile_type)


# ─────────────────────────────────────────────────────────────────────────────
# Suggestions & Ajustements
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/suggestions", response_model=list[StrategyFeedbackItem])
def get_suggestions(db: Session = Depends(get_db)):
    """Suggestions en mode shadow (non appliquées)."""
    svc = LearningService(db)
    return [StrategyFeedbackItem.model_validate(s) for s in svc.get_shadow_suggestions()]


@router.post("/promote/{feedback_id}", response_model=StrategyFeedbackItem)
def promote_suggestion(feedback_id: int, db: Session = Depends(get_db)):
    """Promeut une suggestion shadow → applied."""
    svc = LearningService(db)
    fb = svc.promote_adjustment(feedback_id)
    if fb is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Suggestion non trouvée")
    return StrategyFeedbackItem.model_validate(fb)


@router.post("/rollback/{feedback_id}", response_model=StrategyFeedbackItem)
def rollback_adjustment(feedback_id: int, db: Session = Depends(get_db)):
    """Annule un ajustement appliqué."""
    svc = LearningService(db)
    fb = svc.rollback_adjustment(feedback_id)
    if fb is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Ajustement non trouvé")
    return StrategyFeedbackItem.model_validate(fb)


@router.get("/versions", response_model=LearningVersionHistory)
def get_versions(db: Session = Depends(get_db)):
    """Historique des versions d'ajustements."""
    svc = LearningService(db)
    return svc.get_version_history()


@router.get("/signals", response_model=list[LearningSignalItem])
def get_learning_signals(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Échantillons d'apprentissage récents."""
    from app.models.learning import LearningSignal
    samples = (
        db.query(LearningSignal)
        .order_by(LearningSignal.created_at.desc())
        .limit(limit)
        .all()
    )
    return [LearningSignalItem.model_validate(s) for s in samples]


@router.post("/learn-runtime", response_model=list[StrategyFeedbackItem])
def learn_from_runtime(
    profile_type: str = Query(default="scalping"),
    db: Session = Depends(get_db),
):
    """
    [v2.0.4] Apprentissage basé sur les données runtime (TickActivityLog).

    Analyse les ticks du profil spécifié pour identifier :
    - Les gates sur-bloquants (micro_trend, quality, economic, etc.)
    - Les paramètres à assouplir quand le moteur veut trader mais est bloqué

    Génère des suggestions en mode shadow basées sur les refus runtime,
    contrairement à /learning/analyze qui se base sur les trades fermés.
    """
    svc = LearningService(db)
    suggestions = svc.learn_from_runtime(profile_type)
    return [StrategyFeedbackItem.model_validate(s) for s in suggestions]


# ─────────────────────────────────────────────────────────────────────────────
# PaperRun — Campagnes de validation
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/run/start", response_model=PaperRunResponse)
def start_run(request: PaperRunCreate, db: Session = Depends(get_db)):
    """Démarre une campagne de validation."""
    svc = PaperRunService(db)
    run = svc.start_run(name=request.name, profile_type=request.profile_type)
    return PaperRunResponse.model_validate(run)


@router.post("/run/{run_id}/end", response_model=PaperRunResponse)
def end_run(run_id: int, db: Session = Depends(get_db)):
    """Termine une campagne de validation."""
    svc = PaperRunService(db)
    run = svc.end_run(run_id)
    if run is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Run non trouvé")
    return PaperRunResponse.model_validate(run)


@router.get("/runs", response_model=list[PaperRunResponse])
def list_runs(db: Session = Depends(get_db)):
    """Liste toutes les campagnes de validation."""
    svc = PaperRunService(db)
    return [PaperRunResponse.model_validate(r) for r in svc.get_runs()]


@router.get("/run/{run_id}/metrics", response_model=PaperRunMetrics)
def get_run_metrics(run_id: int, db: Session = Depends(get_db)):
    """Métriques complètes d'un run (brut + net)."""
    svc = PaperRunService(db)
    metrics = svc.get_run_metrics(run_id)
    if metrics is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Run non trouvé")
    return metrics


@router.get("/runs/compare", response_model=RunComparison)
def compare_runs(
    before_id: int = Query(description="ID du run 'avant'"),
    after_id: int = Query(description="ID du run 'après'"),
    db: Session = Depends(get_db),
):
    """Compare deux runs (avant/après)."""
    svc = PaperRunService(db)
    comparison = svc.compare_runs(before_id, after_id)
    if comparison is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Un ou les deux runs non trouvés")
    return comparison

