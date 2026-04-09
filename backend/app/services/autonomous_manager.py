"""
AutonomousManager — Gestionnaire du mode autonome backend pour le paper trading.

Ce singleton gère un thread d'exécution de ticks automatiques côté backend,
permettant au robot de tourner sans navigateur ouvert (mode headless).

Architecture :
- Thread daemon avec boucle Timer récurrente
- Intervalle configurable en secondes (min 5s)
- Démarrage/arrêt via API sans redémarrage du serveur
- Indépendant du scheduler APScheduler (pas de conflit)

Le frontend n'est plus nécessaire pour que le robot trade.
"""

import threading
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AutonomousManager:
    """
    Singleton gérant le mode autonome du paper trading.

    Usage :
        manager = AutonomousManager()
        manager.start(interval_seconds=10, profile="scalping")
        status = manager.get_status()
        manager.stop()
    """

    _instance: Optional["AutonomousManager"] = None
    _creation_lock = threading.Lock()

    def __new__(cls) -> "AutonomousManager":
        if cls._instance is None:
            with cls._creation_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._running = False
        self._interval_seconds = 30
        self._profile: str = "scalping"
        self._timer: Optional[threading.Timer] = None
        self._tick_count = 0
        self._trade_count = 0
        self._last_tick_time: Optional[datetime] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._started_at: Optional[datetime] = None
        self._tick_lock = threading.Lock()
        self._state_lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────────
    # API publique
    # ──────────────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def start(
        self,
        interval_seconds: int = 30,
        profile: str = "scalping",
    ) -> Dict[str, Any]:
        """
        Démarre le mode autonome backend.

        Args:
            interval_seconds: Intervalle entre les ticks (min 5s, max 3600s).
            profile: Profil de trading à utiliser.

        Returns:
            Statut du démarrage.
        """
        with self._state_lock:
            if self._running:
                return {
                    "status": "already_running",
                    "interval_seconds": self._interval_seconds,
                    "profile": self._profile,
                    "tick_count": self._tick_count,
                }

            self._interval_seconds = max(5, min(3600, interval_seconds))
            self._profile = profile
            self._running = True
            self._tick_count = 0
            self._trade_count = 0
            self._started_at = datetime.now(timezone.utc)
            self._last_result = None

        # Configurer le profil en base
        self._set_profile(profile)

        # Exécuter le premier tick immédiatement dans un thread séparé
        threading.Thread(target=self._do_tick, daemon=True).start()

        logger.info(
            f"🤖 Mode autonome backend démarré : "
            f"interval={self._interval_seconds}s, profile={profile}"
        )
        return {
            "status": "started",
            "interval_seconds": self._interval_seconds,
            "profile": profile,
        }

    def stop(self) -> Dict[str, Any]:
        """Arrête le mode autonome."""
        with self._state_lock:
            was_running = self._running
            self._running = False
            if self._timer:
                self._timer.cancel()
                self._timer = None

        uptime = 0.0
        if self._started_at and was_running:
            uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()

        result = {
            "status": "stopped" if was_running else "was_not_running",
            "total_ticks": self._tick_count,
            "total_trades": self._trade_count,
            "uptime_seconds": round(uptime, 1),
        }

        if was_running:
            logger.info(
                f"🛑 Mode autonome arrêté après {self._tick_count} ticks, "
                f"{self._trade_count} trades, {round(uptime)}s"
            )
        return result

    def get_status(self) -> Dict[str, Any]:
        """Retourne le statut complet du mode autonome."""
        uptime = None
        if self._started_at and self._running:
            uptime = round(
                (datetime.now(timezone.utc) - self._started_at).total_seconds(), 1
            )

        return {
            "running": self._running,
            "interval_seconds": self._interval_seconds if self._running else None,
            "profile": self._profile if self._running else None,
            "tick_count": self._tick_count,
            "trade_count": self._trade_count,
            "last_tick_time": (
                self._last_tick_time.isoformat() if self._last_tick_time else None
            ),
            "last_result": self._last_result,
            "started_at": (
                self._started_at.isoformat() if self._started_at else None
            ),
            "uptime_seconds": uptime,
            "frontend_required": False,
            "headless_capable": True,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Boucle interne
    # ──────────────────────────────────────────────────────────────────────

    def _schedule_next(self) -> None:
        """Planifie le prochain tick après l'intervalle configuré."""
        if not self._running:
            return
        self._timer = threading.Timer(self._interval_seconds, self._do_tick)
        self._timer.daemon = True
        self._timer.start()

    def _do_tick(self) -> None:
        """Exécute un tick du paper trading en mode autonome."""
        if not self._running:
            return

        # Protection contre les ticks concurrents
        acquired = self._tick_lock.acquire(blocking=False)
        if not acquired:
            self._schedule_next()
            return

        db = None
        try:
            # Import tardif pour éviter les imports circulaires
            from app.database import SessionLocal
            from app.services.paper_trading_service import PaperTradingService

            db = SessionLocal()
            service = PaperTradingService(db)

            tick_result = service.tick()

            with self._state_lock:
                self._tick_count += 1
                self._last_tick_time = datetime.now(timezone.utc)
                self._last_result = {
                    "action": tick_result.action_taken,
                    "detail": tick_result.detail[:120] if tick_result.detail else "",
                    "price": tick_result.current_price,
                    "timestamp": self._last_tick_time.isoformat(),
                }

                # Compter les trades (ouverture ou fermeture)
                action = tick_result.action_taken
                if "opened" in action or "closed" in action:
                    self._trade_count += 1
                    logger.info(
                        f"🤖 Autonomous tick #{self._tick_count}: "
                        f"{action} — {tick_result.detail[:80]}"
                    )

        except Exception as e:
            logger.error(f"🤖 Autonomous tick error: {e}")
            with self._state_lock:
                self._tick_count += 1
                self._last_tick_time = datetime.now(timezone.utc)
                self._last_result = {
                    "action": "error",
                    "detail": str(e)[:120],
                    "price": 0.0,
                    "timestamp": self._last_tick_time.isoformat(),
                }
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass
            self._tick_lock.release()
            # Planifier le prochain tick
            self._schedule_next()

    def _set_profile(self, profile: str) -> None:
        """Configure le profil de trading en base."""
        db = None
        try:
            from app.database import SessionLocal
            from app.services.trading_profile_service import TradingProfileService
            from app.services.paper_trading_service import PaperTradingService

            db = SessionLocal()

            # S'assurer que le compte existe et est actif
            service = PaperTradingService(db)
            account = service.get_or_create_account()
            if not account.is_active:
                account.is_active = True
            # Activer multi-slot (3 positions simultanées)
            account.max_open_positions = 3
            db.commit()

            # Définir le profil
            profile_service = TradingProfileService(db)
            profile_service.set_profile(profile)

            logger.info(f"🤖 Profil configuré : {profile}")
        except Exception as e:
            logger.error(f"🤖 Erreur config profil : {e}")
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass

