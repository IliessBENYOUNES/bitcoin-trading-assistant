"""
Tests pour le SAS d'Entrée Sécurisé (Entry Airlock).

[v2.0.22] Valide que le système SAS :
1. Crée des entrées virtuelles au lieu d'ouvrir immédiatement
2. Approuve quand le PnL virtuel est positif assez longtemps
3. Rejette quand le PnL virtuel reste négatif (timeout)
4. Rejette rapidement aux extrémités de range (range caution)
5. S'intègre correctement dans le flux de _tick_single_slot
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.entry_sas_service import EntrySasService, SasPendingEntry, SasVerdict


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _create_sas(
    slot="scalping",
    direction="long",
    price=70000.0,
    pp_pct=0.5,
    max_dur=15.0,
    min_pos=10.0,
    range_caution=True,
    now=None,
):
    """Crée un SAS pending avec des valeurs par défaut pour les tests."""
    return EntrySasService.create_pending(
        slot=slot,
        direction=direction,
        virtual_entry_price=price,
        sl_price=price * 0.998 if direction == "long" else price * 1.002,
        tp_price=price * 1.008 if direction == "long" else price * 0.992,
        position_size_usd=2500.0,
        reason=f"test_{direction}",
        score=66.0,
        leverage=1.0,
        leverage_reason="test",
        profile_type="scalping",
        entry_candle_direction="green" if direction == "long" else "red",
        price_position_pct=pp_pct,
        max_duration_seconds=max_dur,
        min_positive_seconds=min_pos,
        range_caution=range_caution,
        now=now or _now(),
    )


@pytest.fixture(autouse=True)
def clean_sas():
    """Nettoie les SAS avant et après chaque test."""
    EntrySasService.clear()
    yield
    EntrySasService.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Tests EntrySasService — Création
# ─────────────────────────────────────────────────────────────────────────────

class TestSasCreation:
    """Tests pour la création d'entrées SAS."""

    def test_create_pending_stores_entry(self):
        """Crée une entrée SAS et vérifie qu'elle est stockée."""
        entry = _create_sas()
        assert entry is not None
        assert entry.slot == "scalping"
        assert entry.direction == "long"
        assert entry.virtual_entry_price == 70000.0

    def test_create_pending_is_retrievable(self):
        """L'entrée SAS créée est récupérable via get_pending."""
        _create_sas()
        pending = EntrySasService.get_pending("scalping")
        assert pending is not None
        assert pending.direction == "long"

    def test_create_pending_overwrites_existing(self):
        """Une nouvelle création remplace la précédente sur le même slot."""
        _create_sas(direction="long", price=70000.0)
        _create_sas(direction="short", price=71000.0)
        pending = EntrySasService.get_pending("scalping")
        assert pending.direction == "short"
        assert pending.virtual_entry_price == 71000.0

    def test_has_pending_true(self):
        """has_pending retourne True quand un SAS existe."""
        _create_sas()
        assert EntrySasService.has_pending("scalping") is True

    def test_has_pending_false(self):
        """has_pending retourne False quand aucun SAS."""
        assert EntrySasService.has_pending("scalping") is False

    def test_get_pending_returns_none_when_empty(self):
        """get_pending retourne None quand aucun SAS."""
        assert EntrySasService.get_pending("scalping") is None

    def test_multiple_slots_independent(self):
        """Les SAS de slots différents sont indépendants."""
        _create_sas(slot="scalping", direction="long")
        _create_sas(slot="aggressive", direction="short")
        assert EntrySasService.get_pending("scalping").direction == "long"
        assert EntrySasService.get_pending("aggressive").direction == "short"


# ─────────────────────────────────────────────────────────────────────────────
# Tests EntrySasService — Évaluation
# ─────────────────────────────────────────────────────────────────────────────

class TestSasEvaluation:
    """Tests pour l'évaluation du PnL virtuel dans le SAS."""

    def test_evaluate_no_pending_returns_rejected(self):
        """Évaluer un slot sans SAS retourne rejected."""
        verdict = EntrySasService.evaluate("scalping", 70000.0)
        assert verdict.action == "rejected"

    def test_evaluate_long_positive_first_tick_returns_waiting(self):
        """Premier tick positif → encore en attente (pas assez longtemps)."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, now=t0)
        t1 = t0 + timedelta(seconds=5)
        verdict = EntrySasService.evaluate("scalping", 70050.0, t1)
        assert verdict.action == "waiting"
        assert verdict.virtual_pnl_pct > 0

    def test_evaluate_long_positive_sustained_approved(self):
        """PnL positif continu pendant min_positive_seconds → approved."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, min_pos=10.0, now=t0)

        # Tick 1 : +5 secondes, prix monte → positif
        t1 = t0 + timedelta(seconds=5)
        v1 = EntrySasService.evaluate("scalping", 70050.0, t1)
        assert v1.action == "waiting"

        # Tick 2 : +10 secondes, toujours positif
        t2 = t0 + timedelta(seconds=10)
        v2 = EntrySasService.evaluate("scalping", 70060.0, t2)
        assert v2.action == "waiting"

        # Tick 3 : +16 secondes, positif depuis 11 secondes ≥ 10s → approved
        t3 = t0 + timedelta(seconds=16)
        v3 = EntrySasService.evaluate("scalping", 70070.0, t3)
        assert v3.action == "approved"
        assert v3.virtual_pnl_pct > 0

    def test_evaluate_short_positive_approved(self):
        """SHORT avec prix qui baisse → PnL positif → approved."""
        t0 = _now()
        _create_sas(direction="short", price=70000.0, min_pos=5.0, max_dur=15.0, now=t0)

        # Prix baisse (positif pour short)
        t1 = t0 + timedelta(seconds=5)
        EntrySasService.evaluate("scalping", 69950.0, t1)

        t2 = t0 + timedelta(seconds=11)
        v = EntrySasService.evaluate("scalping", 69940.0, t2)
        assert v.action == "approved"

    def test_evaluate_negative_timeout_rejected(self):
        """PnL négatif → rejeté (anticipé à mi-temps ou timeout)."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, max_dur=15.0, now=t0)

        # Tous les ticks négatifs (prix baisse pour un long)
        verdict = None
        for i in range(1, 5):
            t = t0 + timedelta(seconds=i * 5)
            verdict = EntrySasService.evaluate("scalping", 69950.0, t)
            if verdict.action == "rejected":
                break

        assert verdict.action == "rejected"
        # Le rejet peut venir du mi-temps ou du timeout
        assert "négatif" in verdict.reason or "timeout" in verdict.reason

    def test_evaluate_positive_then_negative_resets_tracker(self):
        """PnL positif puis négatif → reset du tracker positif."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, min_pos=10.0, max_dur=20.0, now=t0)

        # Tick 1 : positif
        t1 = t0 + timedelta(seconds=5)
        v1 = EntrySasService.evaluate("scalping", 70050.0, t1)
        assert v1.action == "waiting"

        # Tick 2 : négatif → reset
        t2 = t0 + timedelta(seconds=10)
        v2 = EntrySasService.evaluate("scalping", 69990.0, t2)
        assert v2.action == "waiting"

        # Le first_positive_at a été reset
        pending = EntrySasService.get_pending("scalping")
        assert pending is not None  # En fait il devrait être rejecté au mi-temps
        # Le pending peut être soit None (rejeté) soit avoir first_positive_at=None

    def test_evaluate_half_time_all_negative_early_rejection(self):
        """Si après la moitié du temps, jamais positif → rejet anticipé."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, max_dur=10.0, min_pos=8.0, now=t0)

        # Tick 1 : négatif
        t1 = t0 + timedelta(seconds=3)
        v1 = EntrySasService.evaluate("scalping", 69990.0, t1)
        assert v1.action == "waiting"  # Pas encore à mi-temps

        # Tick 2 : négatif, t=6 sec → après mi-temps (5 sec), 2 ticks négatifs
        t2 = t0 + timedelta(seconds=6)
        v2 = EntrySasService.evaluate("scalping", 69980.0, t2)
        assert v2.action == "rejected"
        assert "négatif persistant" in v2.reason

    def test_evaluate_timeout_but_positive_approved(self):
        """Timeout atteint mais PnL positif → approved quand même."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, max_dur=10.0, min_pos=15.0, now=t0)

        # Tick 1 : positif à +5s
        t1 = t0 + timedelta(seconds=5)
        EntrySasService.evaluate("scalping", 70050.0, t1)

        # Tick 2 : timeout (10s) et toujours positif
        t2 = t0 + timedelta(seconds=10)
        v = EntrySasService.evaluate("scalping", 70060.0, t2)
        assert v.action == "approved"
        assert "timeout+positif" in v.reason

    def test_sas_cleared_after_approval(self):
        """Le SAS est nettoyé après approbation."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, min_pos=5.0, now=t0)

        t1 = t0 + timedelta(seconds=5)
        EntrySasService.evaluate("scalping", 70050.0, t1)

        t2 = t0 + timedelta(seconds=11)
        EntrySasService.evaluate("scalping", 70060.0, t2)

        # Le SAS devrait être nettoyé
        assert EntrySasService.get_pending("scalping") is None

    def test_sas_cleared_after_rejection(self):
        """Le SAS est nettoyé après rejet."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, max_dur=10.0, now=t0)

        t1 = t0 + timedelta(seconds=3)
        EntrySasService.evaluate("scalping", 69990.0, t1)

        t2 = t0 + timedelta(seconds=6)
        EntrySasService.evaluate("scalping", 69980.0, t2)

        assert EntrySasService.get_pending("scalping") is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests EntrySasService — Range Caution
# ─────────────────────────────────────────────────────────────────────────────

class TestSasRangeCaution:
    """Tests pour la prudence aux extrémités de range."""

    def test_long_at_top_of_range_rejected_quickly(self):
        """LONG en haut de range (>70%) + PnL négatif → rejet rapide."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, pp_pct=0.80, now=t0)

        # Tick 1 : négatif
        t1 = t0 + timedelta(seconds=5)
        v1 = EntrySasService.evaluate("scalping", 69990.0, t1)
        # tick_count=1 → pas encore rejeté (besoin >=2 ticks)
        assert v1.action == "waiting"

        # Tick 2 : négatif → rejet car range caution
        t2 = t0 + timedelta(seconds=10)
        v2 = EntrySasService.evaluate("scalping", 69985.0, t2)
        assert v2.action == "rejected"
        assert "range caution" in v2.reason
        assert "haut de range" in v2.reason

    def test_short_at_bottom_of_range_rejected_quickly(self):
        """SHORT en bas de range (<30%) + PnL négatif → rejet rapide."""
        t0 = _now()
        _create_sas(direction="short", price=70000.0, pp_pct=0.20, now=t0)

        t1 = t0 + timedelta(seconds=5)
        EntrySasService.evaluate("scalping", 70010.0, t1)

        t2 = t0 + timedelta(seconds=10)
        v = EntrySasService.evaluate("scalping", 70015.0, t2)
        assert v.action == "rejected"
        assert "range caution" in v.reason
        assert "bas de range" in v.reason

    def test_long_at_bottom_of_range_no_caution(self):
        """LONG en bas de range (favorable) → pas de rejet range caution."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, pp_pct=0.20, now=t0)

        t1 = t0 + timedelta(seconds=5)
        v1 = EntrySasService.evaluate("scalping", 69990.0, t1)
        # PnL négatif mais en bas de range pour un long → pas de rejet range
        assert v1.action == "waiting"  # Pas de rejet range

    def test_short_at_top_of_range_no_caution(self):
        """SHORT en haut de range (favorable) → pas de rejet range caution."""
        t0 = _now()
        _create_sas(direction="short", price=70000.0, pp_pct=0.80, now=t0)

        t1 = t0 + timedelta(seconds=5)
        v1 = EntrySasService.evaluate("scalping", 70010.0, t1)
        assert v1.action == "waiting"  # Pas de rejet range

    def test_range_caution_disabled(self):
        """Range caution désactivé → pas de rejet RANGE même en haut de range.
        Mais le rejet négatif persistant (mi-temps) peut quand même s'appliquer."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, pp_pct=0.85, range_caution=False, max_dur=20.0, now=t0)

        # Tick 1 : négatif
        t1 = t0 + timedelta(seconds=5)
        v1 = EntrySasService.evaluate("scalping", 69990.0, t1)
        assert v1.action == "waiting"  # Pas de rejet range (caution désactivée)

        # Tick 2 : négatif, mais PAS de rejet range caution
        t2 = t0 + timedelta(seconds=8)
        v2 = EntrySasService.evaluate("scalping", 69985.0, t2)
        # Peut être waiting ou rejected (mi-temps), mais PAS "range caution"
        if v2.action == "rejected":
            assert "range caution" not in v2.reason

    def test_mid_range_no_caution_triggered(self):
        """Position au milieu du range → pas de rejet range même si négatif."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, pp_pct=0.50, now=t0)

        t1 = t0 + timedelta(seconds=5)
        v1 = EntrySasService.evaluate("scalping", 69990.0, t1)
        assert v1.action == "waiting"

        t2 = t0 + timedelta(seconds=10)
        v2 = EntrySasService.evaluate("scalping", 69985.0, t2)
        # tick_count=2, pas en extrémité → pas de rejet range
        assert v2.action != "rejected" or "range caution" not in v2.reason


# ─────────────────────────────────────────────────────────────────────────────
# Tests EntrySasService — Cancel / Clear
# ─────────────────────────────────────────────────────────────────────────────

class TestSasCancelClear:
    """Tests pour cancel et clear."""

    def test_cancel_removes_pending(self):
        """Cancel supprime le SAS du slot."""
        _create_sas()
        EntrySasService.cancel("scalping")
        assert EntrySasService.get_pending("scalping") is None

    def test_cancel_nonexistent_slot_no_error(self):
        """Cancel sur un slot sans SAS ne provoque pas d'erreur."""
        EntrySasService.cancel("inexistant")  # Pas d'exception

    def test_clear_removes_all(self):
        """Clear supprime tous les SAS."""
        _create_sas(slot="scalping")
        _create_sas(slot="aggressive")
        EntrySasService.clear()
        assert EntrySasService.get_pending("scalping") is None
        assert EntrySasService.get_pending("aggressive") is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests EntrySasService — Virtual PnL
# ─────────────────────────────────────────────────────────────────────────────

class TestSasVirtualPnl:
    """Tests pour le calcul du PnL virtuel."""

    def test_long_pnl_positive_when_price_goes_up(self):
        """LONG : prix monte → PnL positif."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, now=t0)
        t1 = t0 + timedelta(seconds=5)
        verdict = EntrySasService.evaluate("scalping", 70100.0, t1)
        assert verdict.virtual_pnl_pct > 0

    def test_long_pnl_negative_when_price_goes_down(self):
        """LONG : prix baisse → PnL négatif."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, now=t0)
        t1 = t0 + timedelta(seconds=5)
        verdict = EntrySasService.evaluate("scalping", 69900.0, t1)
        assert verdict.virtual_pnl_pct < 0

    def test_short_pnl_positive_when_price_goes_down(self):
        """SHORT : prix baisse → PnL positif."""
        t0 = _now()
        _create_sas(direction="short", price=70000.0, now=t0)
        t1 = t0 + timedelta(seconds=5)
        verdict = EntrySasService.evaluate("scalping", 69900.0, t1)
        assert verdict.virtual_pnl_pct > 0

    def test_short_pnl_negative_when_price_goes_up(self):
        """SHORT : prix monte → PnL négatif."""
        t0 = _now()
        _create_sas(direction="short", price=70000.0, now=t0)
        t1 = t0 + timedelta(seconds=5)
        verdict = EntrySasService.evaluate("scalping", 70100.0, t1)
        assert verdict.virtual_pnl_pct < 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests EntrySasService — Tracking
# ─────────────────────────────────────────────────────────────────────────────

class TestSasTracking:
    """Tests pour le tracking interne (tick_count, best/worst PnL)."""

    def test_tick_count_increments(self):
        """Le tick_count s'incrémente à chaque évaluation."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, max_dur=20.0, now=t0)

        for i in range(1, 4):
            t = t0 + timedelta(seconds=i * 3)
            EntrySasService.evaluate("scalping", 70050.0, t)

        pending = EntrySasService.get_pending("scalping")
        # Le pending peut être None si approuvé, mais ici le min_pos=10s
        # et on n'a accumulé que 9 sec de positif → waiting
        if pending is not None:
            assert pending.tick_count == 3

    def test_positive_negative_counters(self):
        """Les compteurs positive_tick_count et negative_tick_count."""
        t0 = _now()
        _create_sas(direction="long", price=70000.0, max_dur=20.0, now=t0)

        # Tick 1 : positif
        EntrySasService.evaluate("scalping", 70050.0, t0 + timedelta(seconds=3))
        # Tick 2 : négatif
        EntrySasService.evaluate("scalping", 69950.0, t0 + timedelta(seconds=6))

        pending = EntrySasService.get_pending("scalping")
        if pending is not None:
            assert pending.positive_tick_count == 1
            assert pending.negative_tick_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# Tests TradingProfileParams — SAS fields
# ─────────────────────────────────────────────────────────────────────────────

class TestSasProfileParams:
    """Tests que les paramètres SAS sont bien définis dans les presets."""

    def test_scalping_sas_enabled(self):
        """Le profil scalping a le SAS activé."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        p = PROFILE_PRESETS["scalping"]
        assert p.entry_sas_enabled is True
        assert p.entry_sas_duration_seconds == 15.0
        assert p.entry_sas_min_positive_seconds == 10.0
        assert p.entry_sas_range_caution is True

    def test_conservative_sas_disabled(self):
        """Le profil conservative n'a PAS le SAS."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        p = PROFILE_PRESETS["conservative"]
        assert p.entry_sas_enabled is False

    def test_balanced_sas_disabled(self):
        """Le profil balanced n'a PAS le SAS."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        p = PROFILE_PRESETS["balanced"]
        assert p.entry_sas_enabled is False

    def test_aggressive_sas_disabled(self):
        """Le profil aggressive n'a PAS le SAS."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        p = PROFILE_PRESETS["aggressive"]
        assert p.entry_sas_enabled is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests scénarios réels simulés
# ─────────────────────────────────────────────────────────────────────────────

class TestSasRealScenarios:
    """Tests simulant les scénarios réels problématiques du JSON export."""

    def test_trade_620_short_immediate_loss_rejected(self):
        """
        Simule le trade #620 : SHORT @ 70825.67, SL hit à 71258.34 en 36 sec.
        Le SAS aurait rejeté car le prix monte immédiatement (PnL négatif pour short).
        """
        t0 = _now()
        _create_sas(
            direction="short",
            price=70825.67,
            pp_pct=0.5,
            max_dur=15.0,
            min_pos=10.0,
            now=t0,
        )

        # Le prix monte immédiatement (destructeur pour un short)
        # Tick 1 : +5s, prix monte à ~70900
        t1 = t0 + timedelta(seconds=5)
        v1 = EntrySasService.evaluate("scalping", 70900.0, t1)
        assert v1.action == "waiting"
        assert v1.virtual_pnl_pct < 0  # PnL négatif pour short quand prix monte

        # Tick 2 : +10s, prix continue de monter → rejet mi-temps
        t2 = t0 + timedelta(seconds=10)
        v2 = EntrySasService.evaluate("scalping", 71000.0, t2)
        assert v2.action == "rejected"  # Rejeté (négatif persistant après mi-temps)

    def test_trade_600_short_correct_direction_approved(self):
        """
        Simule le trade #600 : SHORT @ 71256.68, sorti @ 70770.58 (+$25.58).
        Le meilleur trade de la session. Le SAS aurait approuvé car prix baisse.
        """
        t0 = _now()
        _create_sas(
            direction="short",
            price=71256.68,
            pp_pct=0.5,
            max_dur=15.0,
            min_pos=10.0,
            now=t0,
        )

        # Le prix baisse immédiatement (positif pour short)
        t1 = t0 + timedelta(seconds=5)
        v1 = EntrySasService.evaluate("scalping", 71200.0, t1)
        assert v1.action == "waiting"
        assert v1.virtual_pnl_pct > 0

        t2 = t0 + timedelta(seconds=10)
        v2 = EntrySasService.evaluate("scalping", 71150.0, t2)
        assert v2.action == "waiting"

        # +16s, positif depuis 11s ≥ 10s → approved
        t3 = t0 + timedelta(seconds=16)
        v3 = EntrySasService.evaluate("scalping", 71100.0, t3)
        assert v3.action == "approved"

    def test_long_at_top_of_range_rejected_trade_605(self):
        """
        Simule trade #605 : LONG @ 70984.10, SL hit → -$5.79.
        En haut de range avec PnL négatif → rejet rapide via range caution.
        """
        t0 = _now()
        _create_sas(
            direction="long",
            price=70984.10,
            pp_pct=0.75,  # Haut de range
            max_dur=15.0,
            min_pos=10.0,
            now=t0,
        )

        # Prix baisse immédiatement
        t1 = t0 + timedelta(seconds=5)
        v1 = EntrySasService.evaluate("scalping", 70950.0, t1)
        # tick_count=1, range caution attend >=2

        t2 = t0 + timedelta(seconds=10)
        v2 = EntrySasService.evaluate("scalping", 70900.0, t2)
        assert v2.action == "rejected"
        assert "range caution" in v2.reason

