"""
Routes API Paper Trading.

Endpoints pour la simulation de trading en temps réel :
- GET  /paper/account  — État du compte
- POST /paper/account/reset — Reset du compte
- GET  /paper/status   — Statut complet (compte + position + métriques)
- POST /paper/tick     — Exécuter un tick manuellement
- GET  /paper/trades   — Journal des trades
- GET  /paper/metrics  — Métriques de performance
- POST /paper/close    — Fermeture manuelle de la position ouverte
- GET  /paper/trades/export — Export complet du journal (tous trades, sans pagination)
- GET  /paper/journal  — [v1.5] Journal d'évaluation multi-jours
- GET  /paper/style    — [v1.5] Qualification du style de trading
- GET  /paper/profile  — [v1.5] Profil de trading actif
- POST /paper/profile  — [v1.5] Changer de profil
- GET  /paper/profile/presets — [v1.5] Tous les presets disponibles
- GET  /paper/diagnostic — [v1.6] Diagnostic de fréquence
- GET  /paper/missed-opportunities — [v1.6] Opportunités manquées
- GET  /paper/leverage-analysis — [v1.6] Analyse levier
"""

import threading
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.paper_trading_service import PaperTradingService
from app.services.journal_service import JournalService
from app.services.trading_profile_service import TradingProfileService
from app.services.diagnostic_service import DiagnosticService
from app.schemas.paper_trading import (
    PaperAccountCreate,
    FullResetRequest,
    FullResetResponse,
    PaperAccountResponse,
    PaperTradeResponse,
    PaperTradeListResponse,
    PaperMetrics,
    PaperStatus,
    PaperTickResult,
    PaperExportResponse,
    AutonomousStartRequest,
    AutonomousStatusResponse,
)
from app.services.autonomous_manager import AutonomousManager
from app.schemas.journal import (
    TradingProfileParams,
    TradingProfileResponse,
    TradingProfileSetRequest,
    JournalResponse,
    TradingStyleResult,
)
from app.schemas.diagnostic import (
    DiagnosticResponse,
    MissedOpportunitySummary,
    LeverageAnalysisResponse,
)

router = APIRouter(prefix="/paper", tags=["Paper Trading"])

# [v1.9.6] Verrou global pour empêcher les ticks concurrents.
# La cause racine du bug de double ouverture de slot est une race condition
# TOCTOU : deux requêtes /paper/tick concurrentes vérifient toutes les deux
# qu'un slot est libre, puis ouvrent chacune une position.
# Ce verrou garantit qu'un seul tick s'exécute à la fois.
_tick_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints existants (inchangés)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/account", response_model=PaperAccountResponse)
def get_account(db: Session = Depends(get_db)):
    """Retourne le compte paper trading (crée un compte par défaut si absent)."""
    service = PaperTradingService(db)
    account = service.get_or_create_account()
    resp = PaperAccountResponse.model_validate(account)
    open_pos = service.get_open_position()
    if open_pos:
        resp.open_position = PaperTradeResponse.model_validate(open_pos)
    return resp


@router.post("/account", response_model=PaperAccountResponse)
def create_or_update_account(
    config: PaperAccountCreate,
    db: Session = Depends(get_db),
):
    """Crée ou met à jour le compte paper trading."""
    service = PaperTradingService(db)
    account = service.get_or_create_account(config.initial_capital)
    account.max_open_duration_hours = config.max_open_duration_hours
    account.max_open_positions = config.max_open_positions
    if not account.is_active:
        account.is_active = True
    db.commit()
    db.refresh(account)
    return PaperAccountResponse.model_validate(account)


@router.post("/account/reset", response_model=FullResetResponse)
def reset_account(
    config: FullResetRequest,
    db: Session = Depends(get_db),
):
    """
    Full reset du compte paper — DESTRUCTIF.

    Exige confirm="RESET" pour éviter les appels accidentels.

    Purge complète :
    - trades paper
    - tick_activity_log
    - learning_signal
    - strategy_feedback
    - paper_run
    - risk config (daily loss, kill switch)

    Recrée un compte vierge.
    """
    from fastapi import HTTPException

    if config.confirm != "RESET":
        raise HTTPException(
            status_code=400,
            detail="Confirmation invalide. Envoyez confirm='RESET' pour confirmer le full reset.",
        )

    service = PaperTradingService(db)
    account, purged = service.reset_account(config.initial_capital)
    account.max_open_duration_hours = config.max_open_duration_hours
    account.max_open_positions = config.max_open_positions
    db.commit()
    db.refresh(account)

    # Construire les détails lisibles
    details = []
    for table, count in purged.items():
        if table == "risk_config_reset":
            if count:
                details.append("✅ Risk config réinitialisé (daily loss, kill switch, portfolio value)")
        elif count > 0:
            details.append(f"🗑️ {count} enregistrement(s) supprimé(s) dans {table}")
        else:
            details.append(f"— {table} : déjà vide")

    return FullResetResponse(
        account=PaperAccountResponse.model_validate(account),
        purged=purged,
        reset_details=details,
        message=f"Full reset effectué. Nouveau compte #{account.id} créé avec {account.initial_capital}$ de capital.",
    )


@router.get("/status", response_model=PaperStatus)
def get_status(db: Session = Depends(get_db)):
    """Statut complet du paper trading."""
    service = PaperTradingService(db)
    return service.get_status()


@router.post("/tick", response_model=PaperTickResult)
def manual_tick(db: Session = Depends(get_db)):
    """
    Exécute un tick manuellement (utile pour debug/test).

    [v1.9.6] Protégé par un verrou : un seul tick à la fois.
    Cela empêche la race condition de double ouverture de slot.

    [v2.0.3-fix] Auto-activation : si le compte existe mais est inactif,
    le tick l'active automatiquement avant d'exécuter. L'utilisateur final
    ne doit jamais avoir à faire de requête POST manuelle pour activer.
    """
    acquired = _tick_lock.acquire(blocking=False)
    if not acquired:
        # Un autre tick est déjà en cours — retourner un résultat neutre
        from datetime import datetime, timezone
        return PaperTickResult(
            action_taken="hold",
            detail="Un tick est déjà en cours d'exécution. Réessayez.",
            current_price=0.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            non_trade_reason="tick_in_progress",
        )
    try:
        service = PaperTradingService(db)
        # [v2.0.3-fix] Auto-activation du compte si inactif.
        # Quand le frontend appelle /paper/tick, c'est que l'utilisateur
        # veut trader — pas besoin de lui demander d'activer manuellement.
        account = service.get_or_create_account()
        if not account.is_active:
            account.is_active = True
            account.max_open_positions = max(account.max_open_positions or 1, 3)
            db.commit()
        return service.tick()
    finally:
        _tick_lock.release()


@router.get("/trades", response_model=PaperTradeListResponse)
def get_trades(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str = Query(default=None, description="Filtre: open, closed, closed_tp, closed_sl, etc."),
    db: Session = Depends(get_db),
):
    """Liste des trades paper avec pagination et filtres."""
    service = PaperTradingService(db)
    trades, total = service.get_trades(limit=limit, offset=offset, status_filter=status)
    return PaperTradeListResponse(
        trades=[PaperTradeResponse.model_validate(t) for t in trades],
        total=total,
    )


@router.get("/metrics", response_model=PaperMetrics)
def get_metrics(db: Session = Depends(get_db)):
    """Métriques de performance du paper trading."""
    service = PaperTradingService(db)
    return service.get_metrics()


@router.post("/close", response_model=PaperTradeResponse)
def close_position(
    reason: str = Query(default="Fermeture manuelle", max_length=200),
    db: Session = Depends(get_db),
):
    """Ferme manuellement la position ouverte."""
    service = PaperTradingService(db)
    trade = service.close_position_manual(reason)
    if trade is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail="Aucune position ouverte à fermer"
        )
    return PaperTradeResponse.model_validate(trade)


@router.get("/trades/export", response_model=PaperExportResponse)
def export_trades(db: Session = Depends(get_db)):
    """
    Export complet du journal de trading (tous les trades, sans pagination).

    Retourne un JSON structuré contenant :
    - Résumé du compte (capital, PnL, profil, dates)
    - Métriques de performance agrégées
    - Prix BTC actuel
    - Toutes les positions ouvertes
    - Tous les trades fermés avec détails complets

    Conçu pour être copié/collé dans un LLM (ChatGPT, Claude)
    ou sauvegardé en fichier JSON pour analyse.
    """
    service = PaperTradingService(db)
    return service.export_trades()


# ─────────────────────────────────────────────────────────────────────────────
# [v1.5] Journal d'évaluation
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/journal", response_model=JournalResponse)
def get_journal(
    date_from: str = Query(default=None, description="Date de début (YYYY-MM-DD)"),
    date_to: str = Query(default=None, description="Date de fin (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """
    Journal d'évaluation paper trading multi-jours.

    Retourne :
    - Synthèse de la période (PnL, win rate, expectancy, verdict...)
    - Résumé jour par jour
    - Statistiques d'activité (ticks, ratio, fréquence)
    - Raisons de non-trade agrégées
    """
    journal = JournalService(db)
    return journal.get_journal(date_from=date_from, date_to=date_to)


# ─────────────────────────────────────────────────────────────────────────────
# [v1.5] Qualification du style de trading
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/style", response_model=TradingStyleResult)
def get_trading_style(db: Session = Depends(get_db)):
    """
    Qualification du style de trading :
    - Distribution des durées de position
    - Style dominant (scalping-like, intraday, swing)
    - Statistiques micro-temporelles
    """
    journal = JournalService(db)
    return journal.get_trading_style()


# ─────────────────────────────────────────────────────────────────────────────
# [v1.5] Profils de trading
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/profile", response_model=TradingProfileResponse)
def get_profile(db: Session = Depends(get_db)):
    """Retourne le profil de trading actif et ses paramètres."""
    service = TradingProfileService(db)
    return service.get_active_profile()


@router.post("/profile", response_model=TradingProfileResponse)
def set_profile(
    request: TradingProfileSetRequest,
    db: Session = Depends(get_db),
):
    """Change le profil de trading actif (conservative, balanced, aggressive)."""
    service = TradingProfileService(db)
    return service.set_profile(request.profile.value)


@router.get("/profile/presets", response_model=list[TradingProfileParams])
def get_presets():
    """Retourne tous les presets de profils disponibles."""
    return TradingProfileService.get_all_presets()


# ─────────────────────────────────────────────────────────────────────────────
# [v1.6] Diagnostic de fréquence + Opportunités manquées + Levier
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/diagnostic", response_model=DiagnosticResponse)
def get_diagnostic(
    date_from: str = Query(default=None, description="Date de début (YYYY-MM-DD)"),
    date_to: str = Query(default=None, description="Date de fin (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """
    Diagnostic de fréquence de trading.

    Identifie pourquoi le bot trade peu :
    - Top raisons de non-trade classées
    - Analyse de la durée des positions
    - Comparaison simulée des profils
    - Analyse du risk engine comme frein
    - Bottleneck principal + recommandations
    """
    service = DiagnosticService(db)
    return service.get_diagnostic(date_from=date_from, date_to=date_to)


@router.get("/missed-opportunities", response_model=MissedOpportunitySummary)
def get_missed_opportunities(
    date_from: str = Query(default=None, description="Date de début (YYYY-MM-DD)"),
    date_to: str = Query(default=None, description="Date de fin (YYYY-MM-DD)"),
    lookforward_minutes: int = Query(default=30, ge=5, le=120, description="Fenêtre d'observation après le tick (minutes)"),
    min_move_pct: float = Query(default=0.10, ge=0.01, le=5.0, description="Mouvement minimum considéré comme opportunité (%)"),
    db: Session = Depends(get_db),
):
    """
    Détection d'opportunités manquées (analyse ex-post).

    Analyse les ticks non-trade et vérifie si un mouvement favorable
    s'est produit dans les N minutes suivantes.

    ⚠️ Ces chiffres sont ex-post et surestiment les gains réels.
    """
    service = DiagnosticService(db)
    return service.get_missed_opportunities(
        date_from=date_from, date_to=date_to,
        lookforward_minutes=lookforward_minutes,
        min_move_pct=min_move_pct,
    )


@router.get("/leverage-analysis", response_model=LeverageAnalysisResponse)
def get_leverage_analysis(
    date_from: str = Query(default=None, description="Date de début (YYYY-MM-DD)"),
    date_to: str = Query(default=None, description="Date de fin (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """
    Analyse comparative avec/sans levier.

    Compare les résultats réels (avec levier) vs simulés (sans levier)
    pour déterminer si le levier aide ou freine le trading.
    """
    service = DiagnosticService(db)
    return service.get_leverage_analysis(date_from=date_from, date_to=date_to)


# ─────────────────────────────────────────────────────────────────────────────
# [v1.9.7] Mode autonome backend (headless / low-bandwidth)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/autonomous/start", response_model=AutonomousStatusResponse)
def start_autonomous(
    request: AutonomousStartRequest,
    db: Session = Depends(get_db),
):
    """
    Démarre le mode autonome backend.

    Le robot exécutera des ticks automatiquement côté serveur,
    sans nécessiter le frontend ouvert. Permet le mode headless
    pour les runs de nuit ou sur connexion limitée.

    Args:
        interval_seconds: Intervalle entre les ticks (5-3600s).
        profile: Profil de trading à utiliser.
    """
    # [v2.0.0-fix] S'assurer que le compte est actif ET multi-slot.
    # Avant, seul le cas `not is_active` configurait max_open_positions.
    # Après un full reset (qui recrée le compte is_active=False, max_open_positions=3),
    # cela fonctionnait. Mais si le compte était déjà actif avec max_open_positions=1
    # (ex: activé manuellement depuis le frontend), le multi-slot n'était pas restauré.
    service = PaperTradingService(db)
    account = service.get_or_create_account()
    account.is_active = True
    account.max_open_positions = max(account.max_open_positions or 1, 3)
    db.commit()

    manager = AutonomousManager()
    result = manager.start(
        interval_seconds=request.interval_seconds,
        profile=request.profile,
    )
    status = manager.get_status()
    return AutonomousStatusResponse(**status)


@router.post("/autonomous/stop", response_model=AutonomousStatusResponse)
def stop_autonomous():
    """
    Arrête le mode autonome backend.

    Les positions ouvertes ne sont PAS fermées automatiquement.
    Elles seront gérées au prochain tick (scheduler ou manuel).
    """
    manager = AutonomousManager()
    manager.stop()
    status = manager.get_status()
    return AutonomousStatusResponse(**status)


@router.get("/autonomous/status", response_model=AutonomousStatusResponse)
def get_autonomous_status():
    """
    Retourne le statut du mode autonome backend.

    Permet de savoir si le robot tourne en headless,
    combien de ticks ont été exécutés, le dernier résultat, etc.
    """
    manager = AutonomousManager()
    status = manager.get_status()
    return AutonomousStatusResponse(**status)



