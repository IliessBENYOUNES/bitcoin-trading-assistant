"""
TickMomentumService — Confirmation de direction par micro price-action.

Au lieu de se baser uniquement sur des indicateurs lagging (15 min),
ce service analyse les ticks récents (dernières ~30 secondes) pour
déterminer la direction IMMÉDIATE du prix BTC.

Utilisation :
1. **Gate de confirmation** (v2.0.13) :
   - SHORT → le prix doit être en baisse (momentum négatif)
   - LONG → le prix doit être en hausse (momentum positif)

2. **Override de direction** (v2.0.14) :
   - detect_direction() retourne la direction dominante sans attendre de direction souhaitée.
   - En mode override, c'est la direction tick-level qui DÉTERMINE si on entre long ou short,
     au lieu de suivre le score technique lagging.
   - Prix monte depuis 30 sec → LONG, peu importe ce que disent les indicateurs 15 min.
   - Prix descend depuis 30 sec → SHORT, idem.
   - Élimine le biais 100% short quand les indicateurs restent bearish en marché ranging.

v2.0.14
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TickMomentumResult:
    """Résultat de l'analyse de momentum tick."""
    # Direction détectée : "up", "down", "flat", "insufficient_data"
    direction: str
    # Variation du prix sur la fenêtre (en USD)
    price_change_usd: float = 0.0
    # Variation du prix sur la fenêtre (en %)
    price_change_pct: float = 0.0
    # Nombre de ticks dans la fenêtre
    tick_count: int = 0
    # Prix au début de la fenêtre
    price_start: float = 0.0
    # Prix à la fin de la fenêtre (= prix courant)
    price_end: float = 0.0
    # Durée réelle de la fenêtre analysée (en secondes)
    window_seconds: float = 0.0
    # Ratio de ticks montants vs descendants (0.0-1.0)
    up_ratio: float = 0.5
    # Explication lisible
    detail: str = ""


class TickMomentumService:
    """
    Service de confirmation de direction par momentum tick-par-tick.

    Stocke un buffer circulaire de prix récents en mémoire (par slot).
    À chaque tick, on enregistre le prix. Avant d'entrer en position,
    on analyse les dernières N secondes pour confirmer la direction.

    Usage :
        # À chaque tick :
        TickMomentumService.record_tick(slot, price, timestamp)

        # Avant d'ouvrir :
        result = TickMomentumService.check_direction(
            slot, direction="short", window_seconds=10
        )
        if result.direction != "down":
            # Bloquer l'entrée
    """

    # Buffer en mémoire : { slot_name: [(timestamp, price), ...] }
    _buffers: dict[str, list[tuple[datetime, float]]] = {}

    # Taille max du buffer par slot (éviter fuite mémoire)
    # [v2.0.14] 200→500 : fenêtre élargie à 30s+ nécessite plus de ticks
    MAX_BUFFER_SIZE = 500

    # Variation minimale (en %) pour considérer un mouvement significatif.
    # En dessous, c'est du bruit et on retourne "flat".
    # [v2.0.14] Calibré pour BTC ~$83K : 0.002% ≈ $1.66
    # Sur 30 sec, le BTC bouge typiquement de $10-$50 (0.012-0.060%).
    # 0.002% filtre le bruit sans bloquer les vrais mouvements.
    MIN_MOVE_PCT = 0.002

    @classmethod
    def record_tick(cls, slot: str, price: float, timestamp: datetime = None):
        """
        Enregistre un tick (prix) dans le buffer.

        Appelé à CHAQUE tick, même si on n'ouvre pas de position.
        Le buffer est nettoyé automatiquement (garde les 60 dernières secondes).
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        if slot not in cls._buffers:
            cls._buffers[slot] = []

        cls._buffers[slot].append((timestamp, price))

        # Nettoyage : garder seulement les 60 dernières secondes
        cutoff = timestamp.replace(second=0, microsecond=0)  # roughly
        # Plus simple : garder MAX_BUFFER_SIZE ticks
        if len(cls._buffers[slot]) > cls.MAX_BUFFER_SIZE:
            cls._buffers[slot] = cls._buffers[slot][-cls.MAX_BUFFER_SIZE:]

    @classmethod
    def check_direction(
        cls,
        slot: str,
        direction: str,
        window_seconds: float = 10.0,
        min_ticks: int = 2,
    ) -> tuple[bool, TickMomentumResult]:
        """
        Vérifie si le momentum tick confirme la direction demandée.

        Args:
            slot: Nom du slot (ex: "scalping")
            direction: Direction souhaitée ("long" ou "short")
            window_seconds: Fenêtre d'analyse en secondes (défaut: 10)
            min_ticks: Nombre minimum de ticks requis dans la fenêtre

        Returns:
            (confirmed, result) :
            - confirmed: True si le momentum confirme la direction
            - result: TickMomentumResult avec les détails
        """
        buffer = cls._buffers.get(slot, [])

        if len(buffer) < min_ticks:
            result = TickMomentumResult(
                direction="insufficient_data",
                tick_count=len(buffer),
                detail=f"Données insuffisantes : {len(buffer)} ticks < {min_ticks} minimum",
            )
            # En cas de données insuffisantes, on laisse passer (ne pas bloquer au démarrage)
            return True, result

        # Prendre les ticks dans la fenêtre temporelle
        now = buffer[-1][0]  # Le dernier tick est le plus récent
        cutoff_time = now.timestamp() - window_seconds

        window_ticks = [
            (ts, price) for ts, price in buffer
            if ts.timestamp() >= cutoff_time
        ]

        if len(window_ticks) < min_ticks:
            result = TickMomentumResult(
                direction="insufficient_data",
                tick_count=len(window_ticks),
                detail=f"Ticks dans fenêtre : {len(window_ticks)} < {min_ticks} minimum (fenêtre {window_seconds}s)",
            )
            return True, result

        # Analyser la direction
        price_start = window_ticks[0][1]
        price_end = window_ticks[-1][1]
        price_change = price_end - price_start
        price_change_pct = (price_change / price_start * 100) if price_start > 0 else 0
        actual_window = now.timestamp() - window_ticks[0][0].timestamp()

        # Compter les ticks montants vs descendants
        up_ticks = 0
        down_ticks = 0
        for i in range(1, len(window_ticks)):
            if window_ticks[i][1] > window_ticks[i - 1][1]:
                up_ticks += 1
            elif window_ticks[i][1] < window_ticks[i - 1][1]:
                down_ticks += 1

        total_moves = up_ticks + down_ticks
        up_ratio = up_ticks / total_moves if total_moves > 0 else 0.5

        # Déterminer la direction du momentum
        if abs(price_change_pct) < cls.MIN_MOVE_PCT:
            tick_direction = "flat"
        elif price_change > 0:
            tick_direction = "up"
        else:
            tick_direction = "down"

        result = TickMomentumResult(
            direction=tick_direction,
            price_change_usd=round(price_change, 2),
            price_change_pct=round(price_change_pct, 5),
            tick_count=len(window_ticks),
            price_start=price_start,
            price_end=price_end,
            window_seconds=round(actual_window, 1),
            up_ratio=round(up_ratio, 2),
        )

        # Vérifier si le momentum confirme la direction demandée
        if direction == "long":
            if tick_direction == "up":
                confirmed = True
                result.detail = (
                    f"✅ Momentum LONG confirmé : prix en hausse "
                    f"+${abs(price_change):.2f} ({price_change_pct:+.4f}%) "
                    f"sur {len(window_ticks)} ticks ({actual_window:.0f}s), "
                    f"ticks montants {up_ratio:.0%}"
                )
            elif tick_direction == "flat":
                confirmed = False
                result.detail = (
                    f"⚠️ Momentum LONG non confirmé : prix plat "
                    f"${price_change:+.2f} ({price_change_pct:+.4f}%) "
                    f"sur {len(window_ticks)} ticks ({actual_window:.0f}s)"
                )
            else:
                confirmed = False
                result.detail = (
                    f"❌ Momentum LONG rejeté : prix en BAISSE "
                    f"-${abs(price_change):.2f} ({price_change_pct:+.4f}%) "
                    f"sur {len(window_ticks)} ticks ({actual_window:.0f}s), "
                    f"ticks montants seulement {up_ratio:.0%}"
                )
        elif direction == "short":
            if tick_direction == "down":
                confirmed = True
                result.detail = (
                    f"✅ Momentum SHORT confirmé : prix en baisse "
                    f"-${abs(price_change):.2f} ({price_change_pct:+.4f}%) "
                    f"sur {len(window_ticks)} ticks ({actual_window:.0f}s), "
                    f"ticks descendants {1 - up_ratio:.0%}"
                )
            elif tick_direction == "flat":
                confirmed = False
                result.detail = (
                    f"⚠️ Momentum SHORT non confirmé : prix plat "
                    f"${price_change:+.2f} ({price_change_pct:+.4f}%) "
                    f"sur {len(window_ticks)} ticks ({actual_window:.0f}s)"
                )
            else:
                confirmed = False
                result.detail = (
                    f"❌ Momentum SHORT rejeté : prix en HAUSSE "
                    f"+${abs(price_change):.2f} ({price_change_pct:+.4f}%) "
                    f"sur {len(window_ticks)} ticks ({actual_window:.0f}s), "
                    f"ticks montants {up_ratio:.0%}"
                )
        else:
            confirmed = True
            result.detail = f"Direction inconnue '{direction}', momentum non vérifié"

        logger.info(f"📊 Tick momentum [{slot}]: {result.detail}")
        return confirmed, result

    @classmethod
    def detect_direction(
        cls,
        slot: str,
        window_seconds: float = 30.0,
        min_ticks: int = 3,
    ) -> tuple[str | None, TickMomentumResult]:
        """
        Détecte la direction dominante du prix sans attendre de direction souhaitée.

        [v2.0.14] Utilisé en mode "override" : c'est la direction tick-level
        qui DÉTERMINE si on entre long ou short, au lieu de confirmer la direction
        du score technique.

        Args:
            slot: Nom du slot (ex: "scalping")
            window_seconds: Fenêtre d'analyse en secondes (défaut: 30)
            min_ticks: Nombre minimum de ticks requis dans la fenêtre

        Returns:
            (direction, result) :
            - direction: "long" si prix monte, "short" si prix descend, None si flat/insufficient
            - result: TickMomentumResult avec les détails
        """
        buffer = cls._buffers.get(slot, [])

        if len(buffer) < min_ticks:
            result = TickMomentumResult(
                direction="insufficient_data",
                tick_count=len(buffer),
                detail=f"Données insuffisantes : {len(buffer)} ticks < {min_ticks} minimum",
            )
            return None, result

        # Prendre les ticks dans la fenêtre temporelle
        now = buffer[-1][0]
        cutoff_time = now.timestamp() - window_seconds

        window_ticks = [
            (ts, price) for ts, price in buffer
            if ts.timestamp() >= cutoff_time
        ]

        if len(window_ticks) < min_ticks:
            result = TickMomentumResult(
                direction="insufficient_data",
                tick_count=len(window_ticks),
                detail=f"Ticks dans fenêtre : {len(window_ticks)} < {min_ticks} minimum (fenêtre {window_seconds}s)",
            )
            return None, result

        # Analyser la direction
        price_start = window_ticks[0][1]
        price_end = window_ticks[-1][1]
        price_change = price_end - price_start
        price_change_pct = (price_change / price_start * 100) if price_start > 0 else 0
        actual_window = now.timestamp() - window_ticks[0][0].timestamp()

        # Compter les ticks montants vs descendants
        up_ticks = 0
        down_ticks = 0
        for i in range(1, len(window_ticks)):
            if window_ticks[i][1] > window_ticks[i - 1][1]:
                up_ticks += 1
            elif window_ticks[i][1] < window_ticks[i - 1][1]:
                down_ticks += 1

        total_moves = up_ticks + down_ticks
        up_ratio = up_ticks / total_moves if total_moves > 0 else 0.5

        # Déterminer la direction du momentum
        if abs(price_change_pct) < cls.MIN_MOVE_PCT:
            tick_direction = "flat"
        elif price_change > 0:
            tick_direction = "up"
        else:
            tick_direction = "down"

        result = TickMomentumResult(
            direction=tick_direction,
            price_change_usd=round(price_change, 2),
            price_change_pct=round(price_change_pct, 5),
            tick_count=len(window_ticks),
            price_start=price_start,
            price_end=price_end,
            window_seconds=round(actual_window, 1),
            up_ratio=round(up_ratio, 2),
        )

        # Mapper la direction du prix vers la direction de trade
        if tick_direction == "up":
            trade_direction = "long"
            result.detail = (
                f"🟢 Bougie verte : prix en hausse "
                f"+${abs(price_change):.2f} ({price_change_pct:+.4f}%) "
                f"sur {len(window_ticks)} ticks ({actual_window:.0f}s) → LONG"
            )
        elif tick_direction == "down":
            trade_direction = "short"
            result.detail = (
                f"🔴 Bougie rouge : prix en baisse "
                f"-${abs(price_change):.2f} ({price_change_pct:+.4f}%) "
                f"sur {len(window_ticks)} ticks ({actual_window:.0f}s) → SHORT"
            )
        else:
            trade_direction = None
            result.detail = (
                f"⚪ Bougie neutre : prix plat "
                f"${price_change:+.2f} ({price_change_pct:+.4f}%) "
                f"sur {len(window_ticks)} ticks ({actual_window:.0f}s) → pas de trade"
            )

        logger.info(f"🕯️ Candle direction [{slot}]: {result.detail}")
        return trade_direction, result

    @classmethod
    def clear_buffer(cls, slot: str = None):
        """
        Vide le buffer (pour les tests ou le reset).

        Args:
            slot: Si fourni, vide seulement ce slot. Sinon, vide tout.
        """
        if slot is None:
            cls._buffers.clear()
        elif slot in cls._buffers:
            del cls._buffers[slot]

    @classmethod
    def get_buffer_size(cls, slot: str) -> int:
        """Retourne la taille du buffer pour un slot."""
        return len(cls._buffers.get(slot, []))

