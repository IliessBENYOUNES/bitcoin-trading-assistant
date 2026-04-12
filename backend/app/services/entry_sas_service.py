"""
EntrySasService — SAS d'Entrée Sécurisé (Entry Airlock).

[v2.0.22] Avant d'ouvrir une position réelle, le système crée une entrée
VIRTUELLE et observe le PnL pendant quelques secondes.

Le concept :
- Quand tous les gates passent (market quality, economic, structural proofs...),
  au lieu d'ouvrir immédiatement, on entre dans un "SAS" (sas d'entrée).
- Le SAS est une phase d'observation de ~10-15 secondes.
- Pendant le SAS, on calcule le PnL virtuel (comme si on avait ouvert).
- Si le PnL reste négatif → l'entrée est annulée. On ne perd RIEN.
- Si le PnL devient positif et y reste → l'entrée réelle est confirmée.
- Prudence renforcée aux extrémités de range (haut→pas de long, bas→pas de short).

Ce service est IN-MEMORY (comme TickMomentumService). Les SAS pending se
perdent au restart, ce qui est sans conséquence (pas de trade ouvert).

Résout le problème catastrophique des entrées destructrices :
- Trade #620 : short ouvert, -$15.27 en 36 secondes → SL immédiat.
- Avec le SAS, ce trade n'aurait jamais été ouvert car le PnL virtuel
  serait resté négatif dès les premières secondes.

v2.0.22
"""

import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SasPendingEntry:
    """Entrée virtuelle en attente de confirmation dans le SAS."""
    slot: str
    direction: str  # "long" ou "short"
    virtual_entry_price: float
    created_at: datetime

    # Paramètres de la position à ouvrir si confirmé
    sl_price: float
    tp_price: float
    position_size_usd: float
    reason: str
    score: float
    leverage: float
    leverage_reason: str
    profile_type: str
    entry_candle_direction: str

    # Données market quality au moment de la création
    price_position_pct: float = 0.5  # 0=bas de range, 1=haut de range

    # Paramètres SAS
    max_duration_seconds: float = 15.0
    min_positive_seconds: float = 10.0
    range_caution: bool = True

    # Tracking du PnL virtuel
    first_positive_at: Optional[datetime] = None
    best_virtual_pnl_pct: float = 0.0
    worst_virtual_pnl_pct: float = 0.0
    tick_count: int = 0
    positive_tick_count: int = 0
    negative_tick_count: int = 0


@dataclass
class SasVerdict:
    """Résultat de l'évaluation d'un SAS."""
    # "approved" → ouvrir la position réelle
    # "rejected" → annuler l'entrée
    # "waiting" → encore en observation
    action: str
    reason: str
    virtual_pnl_pct: float = 0.0
    elapsed_seconds: float = 0.0
    # Prix courant au moment de l'évaluation (pour l'ouverture si approved)
    current_price: float = 0.0


class EntrySasService:
    """
    Service SAS d'Entrée Sécurisé — In-memory, statique.

    Gère les entrées virtuelles en attente de confirmation par slot.
    Pattern identique à TickMomentumService (class-level dict).

    Usage :
        # Quand tous les gates passent :
        EntrySasService.create_pending(slot="scalping", direction="long", ...)

        # À chaque tick suivant :
        verdict = EntrySasService.evaluate(slot="scalping", current_price=70500, now=...)
        if verdict.action == "approved":
            # Ouvrir la vraie position
        elif verdict.action == "rejected":
            # Annuler et passer au prochain signal
    """

    # Entrées SAS en attente : { slot_name: SasPendingEntry }
    _pending: dict[str, SasPendingEntry] = {}

    @classmethod
    def create_pending(
        cls,
        slot: str,
        direction: str,
        virtual_entry_price: float,
        sl_price: float,
        tp_price: float,
        position_size_usd: float,
        reason: str,
        score: float,
        leverage: float,
        leverage_reason: str,
        profile_type: str,
        entry_candle_direction: str,
        price_position_pct: float = 0.5,
        max_duration_seconds: float = 15.0,
        min_positive_seconds: float = 10.0,
        range_caution: bool = True,
        now: Optional[datetime] = None,
    ) -> SasPendingEntry:
        """
        Crée une entrée virtuelle en attente de confirmation.

        Appelé quand tous les gates passent mais avant d'ouvrir réellement.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        entry = SasPendingEntry(
            slot=slot,
            direction=direction,
            virtual_entry_price=virtual_entry_price,
            created_at=now,
            sl_price=sl_price,
            tp_price=tp_price,
            position_size_usd=position_size_usd,
            reason=reason,
            score=score,
            leverage=leverage,
            leverage_reason=leverage_reason,
            profile_type=profile_type,
            entry_candle_direction=entry_candle_direction,
            price_position_pct=price_position_pct,
            max_duration_seconds=max_duration_seconds,
            min_positive_seconds=min_positive_seconds,
            range_caution=range_caution,
        )

        cls._pending[slot] = entry

        logger.info(
            f"🚪 SAS créé [{slot}] : {direction.upper()} virtuel @ "
            f"{virtual_entry_price:.2f} | range_pos={price_position_pct:.0%} | "
            f"max {max_duration_seconds}s, besoin {min_positive_seconds}s positif"
        )

        return entry

    @classmethod
    def get_pending(cls, slot: str) -> Optional[SasPendingEntry]:
        """Retourne l'entrée SAS en attente pour un slot (None si pas de SAS)."""
        return cls._pending.get(slot)

    @classmethod
    def evaluate(
        cls,
        slot: str,
        current_price: float,
        now: Optional[datetime] = None,
    ) -> SasVerdict:
        """
        Évalue le SAS en attente pour un slot.

        Vérifie le PnL virtuel et décide :
        - "approved" : le PnL est positif depuis assez longtemps → ouvrir
        - "rejected" : timeout atteint ou conditions dangereuses → annuler
        - "waiting" : encore en observation

        La logique de range caution :
        - LONG en haut de range (>70%) → rejet immédiat si PnL négatif (pas de seconde chance)
        - SHORT en bas de range (<30%) → idem
        - Ces positions sont structurellement dangereuses (achat au plafond, vente au plancher)
        """
        if now is None:
            now = datetime.now(timezone.utc)

        pending = cls._pending.get(slot)
        if pending is None:
            return SasVerdict(
                action="rejected",
                reason="Pas de SAS en attente",
                current_price=current_price,
            )

        # Calculer le temps écoulé
        elapsed = (now - pending.created_at).total_seconds()

        # Calculer le PnL virtuel
        if pending.direction == "long":
            virtual_pnl_pct = (current_price - pending.virtual_entry_price) / pending.virtual_entry_price * 100
        else:  # short
            virtual_pnl_pct = (pending.virtual_entry_price - current_price) / pending.virtual_entry_price * 100

        # Mettre à jour les trackers
        pending.tick_count += 1
        pending.best_virtual_pnl_pct = max(pending.best_virtual_pnl_pct, virtual_pnl_pct)
        pending.worst_virtual_pnl_pct = min(pending.worst_virtual_pnl_pct, virtual_pnl_pct)

        is_positive = virtual_pnl_pct > 0

        if is_positive:
            pending.positive_tick_count += 1
            if pending.first_positive_at is None:
                pending.first_positive_at = now
                logger.debug(
                    f"🚪 SAS [{slot}] : premier tick positif @ "
                    f"{virtual_pnl_pct:+.4f}% (t+{elapsed:.0f}s)"
                )
        else:
            pending.negative_tick_count += 1
            # Reset du tracker positif : le PnL doit être CONTINU (pas intermittent)
            pending.first_positive_at = None

        # ── Vérification range caution (rejet rapide) ──
        if pending.range_caution and not is_positive and pending.tick_count >= 2:
            # Détecter les positions structurellement dangereuses
            is_dangerous_range = False
            range_detail = ""

            if pending.direction == "long" and pending.price_position_pct > 0.70:
                is_dangerous_range = True
                range_detail = (
                    f"LONG en haut de range ({pending.price_position_pct:.0%})"
                )
            elif pending.direction == "short" and pending.price_position_pct < 0.30:
                is_dangerous_range = True
                range_detail = (
                    f"SHORT en bas de range ({pending.price_position_pct:.0%})"
                )

            if is_dangerous_range:
                reason = (
                    f"🚫 SAS rejeté (range caution) : {range_detail}, "
                    f"PnL virtuel {virtual_pnl_pct:+.4f}% après {elapsed:.0f}s — "
                    f"position structurellement dangereuse"
                )
                logger.info(f"🚪 {reason}")
                cls._cancel(slot)
                return SasVerdict(
                    action="rejected",
                    reason=reason,
                    virtual_pnl_pct=virtual_pnl_pct,
                    elapsed_seconds=elapsed,
                    current_price=current_price,
                )

        # ── Timeout : durée max atteinte ──
        if elapsed >= pending.max_duration_seconds:
            if is_positive and pending.first_positive_at is not None:
                # Timeout mais le PnL est positif maintenant → on valide quand même
                # (le min_positive_seconds n'est pas atteint mais le timeout l'est)
                positive_duration = (now - pending.first_positive_at).total_seconds()
                reason = (
                    f"✅ SAS approuvé (timeout+positif) : PnL virtuel {virtual_pnl_pct:+.4f}% "
                    f"positif depuis {positive_duration:.0f}s, timeout {elapsed:.0f}s atteint"
                )
                logger.info(f"🚪 {reason}")
                cls._cancel(slot)
                return SasVerdict(
                    action="approved",
                    reason=reason,
                    virtual_pnl_pct=virtual_pnl_pct,
                    elapsed_seconds=elapsed,
                    current_price=current_price,
                )
            else:
                reason = (
                    f"🚫 SAS rejeté (timeout) : PnL virtuel {virtual_pnl_pct:+.4f}% "
                    f"après {elapsed:.0f}s, jamais assez positif — "
                    f"best={pending.best_virtual_pnl_pct:+.4f}%, "
                    f"worst={pending.worst_virtual_pnl_pct:+.4f}%, "
                    f"ticks +{pending.positive_tick_count}/-{pending.negative_tick_count}"
                )
                logger.info(f"🚪 {reason}")
                cls._cancel(slot)
                return SasVerdict(
                    action="rejected",
                    reason=reason,
                    virtual_pnl_pct=virtual_pnl_pct,
                    elapsed_seconds=elapsed,
                    current_price=current_price,
                )

        # ── Vérification durée positive continue ──
        if pending.first_positive_at is not None:
            positive_duration = (now - pending.first_positive_at).total_seconds()
            if positive_duration >= pending.min_positive_seconds:
                reason = (
                    f"✅ SAS approuvé : PnL virtuel {virtual_pnl_pct:+.4f}% "
                    f"positif depuis {positive_duration:.0f}s ≥ {pending.min_positive_seconds}s — "
                    f"best={pending.best_virtual_pnl_pct:+.4f}%, "
                    f"ticks +{pending.positive_tick_count}/-{pending.negative_tick_count}"
                )
                logger.info(f"🚪 {reason}")
                cls._cancel(slot)
                return SasVerdict(
                    action="approved",
                    reason=reason,
                    virtual_pnl_pct=virtual_pnl_pct,
                    elapsed_seconds=elapsed,
                    current_price=current_price,
                )

        # ── Rejet rapide : si négatif sur tous les ticks après un certain temps ──
        # Si après la moitié du temps max, AUCUN tick n'a été positif → rejet anticipé
        half_time = pending.max_duration_seconds / 2
        if elapsed >= half_time and pending.positive_tick_count == 0 and pending.tick_count >= 2:
            reason = (
                f"🚫 SAS rejeté (négatif persistant) : PnL virtuel {virtual_pnl_pct:+.4f}% "
                f"jamais positif après {elapsed:.0f}s ({pending.tick_count} ticks) — "
                f"worst={pending.worst_virtual_pnl_pct:+.4f}%"
            )
            logger.info(f"🚪 {reason}")
            cls._cancel(slot)
            return SasVerdict(
                action="rejected",
                reason=reason,
                virtual_pnl_pct=virtual_pnl_pct,
                elapsed_seconds=elapsed,
                current_price=current_price,
            )

        # ── Encore en observation ──
        positive_info = ""
        if pending.first_positive_at is not None:
            pos_dur = (now - pending.first_positive_at).total_seconds()
            positive_info = f", positif depuis {pos_dur:.0f}s/{pending.min_positive_seconds}s"

        reason = (
            f"⏳ SAS en observation : PnL virtuel {virtual_pnl_pct:+.4f}%, "
            f"t+{elapsed:.0f}s/{pending.max_duration_seconds:.0f}s"
            f"{positive_info} — "
            f"ticks +{pending.positive_tick_count}/-{pending.negative_tick_count}"
        )
        logger.debug(f"🚪 {reason}")
        return SasVerdict(
            action="waiting",
            reason=reason,
            virtual_pnl_pct=virtual_pnl_pct,
            elapsed_seconds=elapsed,
            current_price=current_price,
        )

    @classmethod
    def _cancel(cls, slot: str):
        """Supprime l'entrée SAS en attente pour un slot (interne)."""
        cls._pending.pop(slot, None)

    @classmethod
    def cancel(cls, slot: str):
        """Annule manuellement l'entrée SAS en attente pour un slot."""
        if slot in cls._pending:
            logger.info(f"🚪 SAS annulé [{slot}] (cancel explicite)")
            cls._pending.pop(slot, None)

    @classmethod
    def clear(cls):
        """Vide toutes les entrées SAS (reset ou tests)."""
        cls._pending.clear()

    @classmethod
    def has_pending(cls, slot: str) -> bool:
        """Vérifie si un SAS est en attente pour un slot."""
        return slot in cls._pending

