"""
Tests v2.0.0 — Pivot stratégique : economic viability, structural proofs,
momentum fade restricted, scoring refondu.

Tests couvrant :
1. Economic viability gate (TradingCostModel.estimate_economic_viability)
2. Momentum fade restricted (amplitude minimum, net-positif après coûts)
3. Structural proofs gate (preuves structurelles requises)
4. Scoring refondu (poids oscillateurs réduits en tendance)
5. Profil scalping v2.0 (configuration correcte)
6. Non-régression aggressive (sanctuarisé, pas de gate économique)
7. Tick logging (nouvelles colonnes)
"""

import pytest
from datetime import datetime, timezone

from app.services.trading_cost_service import (
    TradingCostModel, COST_REALISTIC, COST_OPTIMISTIC, get_cost_model,
)
from app.services.trading_profile_service import PROFILE_PRESETS
from app.services.signal_service import (
    compute_composite_score, REGIME_WEIGHTS, SignalItem, SignalDirection,
)
from app.services.smart_cooldown_service import SmartCooldownService


# ================================================================
# 1. ECONOMIC VIABILITY GATE
# ================================================================

class TestEconomicViability:
    """Tests pour TradingCostModel.estimate_economic_viability."""

    def test_viable_trade_with_high_capture(self):
        """Un trade avec capture >> coût doit être viable."""
        model = COST_REALISTIC
        result = model.estimate_economic_viability(
            position_size_usd=2500, leverage=1.0,
            expected_capture_pct=1.0,  # 1% capture
            min_ev_multiple=2.0,
        )
        assert result["is_viable"] is True
        assert result["rejection_reason"] is None
        assert result["round_trip_cost_pct"] > 0

    def test_non_viable_trade_small_capture(self):
        """Un trade avec capture < seuil doit être refusé."""
        model = COST_REALISTIC
        result = model.estimate_economic_viability(
            position_size_usd=2500, leverage=1.0,
            expected_capture_pct=0.10,  # 0.10% << 0.31% × 2 = 0.62%
            min_ev_multiple=2.0,
        )
        assert result["is_viable"] is False
        assert result["rejection_reason"] is not None
        assert "Capture attendue" in result["rejection_reason"]

    def test_realistic_cost_round_trip(self):
        """Vérifier le coût RT du preset realistic."""
        model = COST_REALISTIC
        rt = model.round_trip_cost_pct()
        # maker 0.10 + taker 0.10 + spread 0.05 + slippage 0.03×2 = 0.31%
        assert abs(rt - 0.31) < 0.01

    def test_scalping_cost_usd(self):
        """Coût RT pour un scalping $2500 × 1x."""
        model = COST_REALISTIC
        cost = model.round_trip_cost_usd(2500)
        # 2500 × 0.31% = $7.75
        assert abs(cost - 7.75) < 0.1

    def test_leverage_amplifies_cost(self):
        """Le levier doit amplifier le coût proportionnellement."""
        model = COST_REALISTIC
        cost_1x = model.round_trip_cost_usd(2500 * 1.0)
        cost_1_5x = model.round_trip_cost_usd(2500 * 1.5)
        assert cost_1_5x > cost_1x
        assert abs(cost_1_5x / cost_1x - 1.5) < 0.01

    def test_viability_with_multiplier_1_5(self):
        """Avec min_ev_multiple=1.5, seuil = 0.31% × 1.5 = 0.465%."""
        model = COST_REALISTIC
        # 0.465% est le seuil exact
        result_fail = model.estimate_economic_viability(
            position_size_usd=2500, leverage=1.0,
            expected_capture_pct=0.40, min_ev_multiple=1.5,
        )
        assert result_fail["is_viable"] is False

        result_pass = model.estimate_economic_viability(
            position_size_usd=2500, leverage=1.0,
            expected_capture_pct=0.50, min_ev_multiple=1.5,
        )
        assert result_pass["is_viable"] is True

    def test_result_contains_all_fields(self):
        """Le résultat doit contenir tous les champs documentés."""
        model = COST_REALISTIC
        result = model.estimate_economic_viability(
            position_size_usd=2500, leverage=1.0,
            expected_capture_pct=0.5, min_ev_multiple=2.0,
        )
        required_fields = [
            "round_trip_cost_usd", "round_trip_cost_pct",
            "min_capture_required_pct", "min_capture_required_usd",
            "expected_capture_pct", "expected_net_pnl",
            "is_viable", "rejection_reason",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_expected_net_pnl_calculation(self):
        """Le net PnL attendu doit être capture - coût."""
        model = COST_REALISTIC
        result = model.estimate_economic_viability(
            position_size_usd=2500, leverage=1.0,
            expected_capture_pct=1.0, min_ev_multiple=2.0,
        )
        # expected_capture = 2500 × 1.0% = $25
        # cost = $7.75
        # net = $25 - $7.75 = $17.25
        assert abs(result["expected_net_pnl"] - 17.25) < 0.5


# ================================================================
# 2. MOMENTUM FADE RESTRICTED
# ================================================================

class TestMomentumFadeRestricted:
    """Tests pour le mode restricted du momentum fade."""

    def test_scalping_profile_has_restricted_mode(self):
        """Le profil scalping doit avoir momentum_fade_mode=restricted."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.momentum_fade_mode == "restricted"

    def test_scalping_min_amplitude_set(self):
        """Le profil scalping doit avoir un seuil d'amplitude minimum."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.momentum_fade_min_amplitude_pct is not None
        assert scalp.momentum_fade_min_amplitude_pct >= 0.30

    def test_aggressive_has_normal_momentum_fade(self):
        """L'aggressive garde le momentum fade normal."""
        aggro = PROFILE_PRESETS["aggressive"]
        assert aggro.momentum_fade_mode == "enabled"

    def test_conservative_default_mode(self):
        """Les profils sans config explicite ont le mode enabled par défaut."""
        cons = PROFILE_PRESETS["conservative"]
        assert cons.momentum_fade_mode == "enabled"


# ================================================================
# 3. STRUCTURAL PROOFS GATE
# ================================================================

class TestStructuralProofs:
    """Tests pour le gate de preuves structurelles."""

    def test_scalping_requires_2_proofs(self):
        """Le profil scalping doit exiger au moins 2 preuves."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.min_structural_proofs >= 2

    def test_aggressive_no_structural_proofs_required(self):
        """L'aggressive ne doit PAS exiger de preuves structurelles."""
        aggro = PROFILE_PRESETS["aggressive"]
        assert aggro.min_structural_proofs == 0

    def test_conservative_no_structural_proofs(self):
        """Conservative n'a pas de preuves structurelles."""
        cons = PROFILE_PRESETS["conservative"]
        assert cons.min_structural_proofs == 0


# ================================================================
# 4. SCORING REFONDU — Poids oscillateurs réduits
# ================================================================

class TestScoringRefonte:
    """Tests pour les poids de régime recalibrés."""

    def test_bollinger_reduced_in_trending(self):
        """Bollinger doit avoir un poids ≤ 0.3 en tendance."""
        assert REGIME_WEIGHTS["trending"]["bollinger"] <= 0.3

    def test_stochrsi_reduced_in_trending(self):
        """StochRSI doit avoir un poids ≤ 0.3 en tendance."""
        assert REGIME_WEIGHTS["trending"]["stoch_rsi"] <= 0.3

    def test_price_position_boosted_in_trending(self):
        """Price position doit être boosté en tendance (≥ 1.3)."""
        assert REGIME_WEIGHTS["trending"]["price_position"] >= 1.3

    def test_macd_sma_still_strong_in_trending(self):
        """MACD et SMA restent forts en tendance."""
        assert REGIME_WEIGHTS["trending"]["macd"] >= 1.2
        assert REGIME_WEIGHTS["trending"]["sma"] >= 1.2

    def test_ranging_oscillators_still_boosted(self):
        """En range, les oscillateurs restent boostés (pas de changement)."""
        assert REGIME_WEIGHTS["ranging"]["bollinger"] >= 1.2
        assert REGIME_WEIGHTS["ranging"]["stoch_rsi"] >= 1.3

    def test_price_position_boosted_in_ranging(self):
        """Price position boosté aussi en range."""
        assert REGIME_WEIGHTS["ranging"]["price_position"] >= 1.3

    def test_score_trending_bullish_market_capped(self):
        """Un marché bullish trending normal ne doit pas saturer le score."""
        signals = [
            SignalItem(indicator="macd", direction=SignalDirection.BULLISH, strength=0.7, message="MACD bullish"),
            SignalItem(indicator="sma", direction=SignalDirection.BULLISH, strength=0.6, message="SMA bullish"),
            SignalItem(indicator="ema_cross", direction=SignalDirection.BULLISH, strength=0.7, message="EMA bullish"),
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.5, message="RSI ~55"),
            SignalItem(indicator="bollinger", direction=SignalDirection.BULLISH, strength=0.4, message="BB bullish"),
            SignalItem(indicator="stoch_rsi", direction=SignalDirection.BULLISH, strength=0.3, message="StochRSI bullish"),
            SignalItem(indicator="adx", direction=SignalDirection.BULLISH, strength=0.6, message="ADX 30", value=30),
        ]
        result = compute_composite_score(signals)
        # Le score ne doit PAS être à 100 ni même 95
        assert result.score <= 88, f"Score {result.score} trop haut pour un setup normal"

    def test_score_with_neutral_market_structure(self):
        """Des signaux structure NEUTRAL doivent réduire le score."""
        signals = [
            SignalItem(indicator="macd", direction=SignalDirection.BULLISH, strength=0.7, message="MACD bullish"),
            SignalItem(indicator="sma", direction=SignalDirection.BULLISH, strength=0.6, message="SMA bullish"),
            SignalItem(indicator="price_position", direction=SignalDirection.NEUTRAL, strength=0.5, message="Mid range"),
            SignalItem(indicator="range_quality", direction=SignalDirection.NEUTRAL, strength=0.5, message="Tight range"),
            SignalItem(indicator="adx", direction=SignalDirection.BULLISH, strength=0.5, message="ADX 25", value=25),
        ]
        result = compute_composite_score(signals)
        # Les signaux NEUTRAL doivent diluer significativement
        assert result.score < 75, f"Score {result.score} pas assez dilué par les NEUTRAL"


# ================================================================
# 5. PROFIL SCALPING V2.0
# ================================================================

class TestScalpingProfileV200:
    """Tests de la configuration du profil scalping v2.0."""

    def test_economic_gate_enabled(self):
        """Le gate économique doit être activé sur scalping."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.economic_gate_enabled is True

    def test_min_ev_multiple(self):
        """Le multiplicateur EV minimum doit être ≥ 1.5."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.min_ev_multiple >= 1.5

    def test_tp_enlarged(self):
        """Le TP doit être élargi (≥ 0.8%)."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.profit_take_pct >= 0.8

    def test_trailing_activation_raised(self):
        """Trailing stop activation ≥ 0.15% (v2.0.3: abaissé de 0.20% pour être plus atteignable)."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.trailing_stop_activation_pct >= 0.15

    def test_max_trades_reduced(self):
        """Moins de trades par jour (≤ 30)."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.max_trades_per_day <= 30

    def test_market_quality_raised(self):
        """Qualité marché relevée (≥ 50)."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.min_market_quality >= 50

    def test_volume_ratio_raised(self):
        """Volume ratio relevé (≥ 0.8)."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.min_volume_ratio >= 0.8


# ================================================================
# 6. NON-RÉGRESSION AGGRESSIVE (sanctuarisé)
# ================================================================

class TestAggressiveSanctuarized:
    """Tests pour garantir que l'aggressive n'est pas dégradé."""

    def test_aggressive_no_economic_gate(self):
        """L'aggressive ne doit PAS avoir de gate économique."""
        aggro = PROFILE_PRESETS["aggressive"]
        assert aggro.economic_gate_enabled is False

    def test_aggressive_profit_take_unchanged(self):
        """Le TP aggressive reste à 1.0%."""
        aggro = PROFILE_PRESETS["aggressive"]
        assert aggro.profit_take_pct == 1.0

    def test_aggressive_max_leverage_unchanged(self):
        """Le levier max aggressive reste à 3.0."""
        aggro = PROFILE_PRESETS["aggressive"]
        assert aggro.max_leverage == 3.0

    def test_aggressive_min_score_unchanged(self):
        """Le min_score aggressive reste à 10."""
        aggro = PROFILE_PRESETS["aggressive"]
        assert aggro.min_score == 10

    def test_aggressive_market_quality_unchanged(self):
        """Le gate marché aggressive reste bas (25)."""
        aggro = PROFILE_PRESETS["aggressive"]
        assert aggro.min_market_quality == 25

    def test_aggressive_momentum_fade_normal(self):
        """L'aggressive garde le momentum fade normal (pas restricted)."""
        aggro = PROFILE_PRESETS["aggressive"]
        assert aggro.momentum_fade_mode == "enabled"


# ================================================================
# 7. TICK LOGGING — Nouvelles colonnes
# ================================================================

class TestTickLoggingV200:
    """Tests pour les nouvelles colonnes de tick_activity_log."""

    def test_model_has_economic_fields(self):
        """Le modèle TickActivityLog doit avoir les champs economic."""
        from app.models.tick_activity_log import TickActivityLog
        assert hasattr(TickActivityLog, "estimated_round_trip_cost")
        assert hasattr(TickActivityLog, "min_capture_required_pct")
        assert hasattr(TickActivityLog, "economic_gate_passed")
        assert hasattr(TickActivityLog, "rejection_category")

    def test_log_tick_accepts_economic_params(self, db_session):
        """log_tick doit accepter les paramètres economic viability."""
        from app.services.journal_service import JournalService
        from app.models.paper_account import PaperAccount

        account = PaperAccount(initial_capital=10000, current_capital=10000)
        db_session.add(account)
        db_session.commit()

        journal = JournalService(db_session)
        entry = journal.log_tick(
            account_id=account.id,
            action_taken="hold",
            btc_price=72000.0,
            estimated_round_trip_cost=7.75,
            min_capture_required_pct=0.465,
            economic_gate_passed=False,
            rejection_category="economic",
        )
        assert entry.estimated_round_trip_cost == 7.75
        assert entry.min_capture_required_pct == 0.465
        assert entry.economic_gate_passed == 0
        assert entry.rejection_category == "economic"

    def test_log_tick_accepts_rejection_category(self, db_session):
        """log_tick doit accepter la rejection_category."""
        from app.services.journal_service import JournalService
        from app.models.paper_account import PaperAccount

        account = PaperAccount(initial_capital=10000, current_capital=10000)
        db_session.add(account)
        db_session.commit()

        journal = JournalService(db_session)
        entry = journal.log_tick(
            account_id=account.id,
            action_taken="hold",
            btc_price=72000.0,
            rejection_category="structure",
        )
        assert entry.rejection_category == "structure"


# ================================================================
# 8. REASON LABELS — Nouvelles raisons
# ================================================================

class TestReasonLabels:
    """Tests pour les nouvelles raisons de non-trade."""

    def test_economic_viability_label_exists(self):
        """Le label economic_viability_low doit exister."""
        from app.services.journal_service import REASON_LABELS
        assert "economic_viability_low" in REASON_LABELS

    def test_structural_proof_label_exists(self):
        """Le label structural_proof_insufficient doit exister."""
        from app.services.journal_service import REASON_LABELS
        assert "structural_proof_insufficient" in REASON_LABELS

    def test_micro_trend_insufficient_label_exists(self):
        """Le label micro_trend_insufficient doit exister (v2.0.3)."""
        from app.services.journal_service import REASON_LABELS
        assert "micro_trend_insufficient" in REASON_LABELS


# ================================================================
# 9. MINI-LOT CORRECTIF v2.0.3 — Post-audit runtime
# ================================================================

class TestScalpingV203MiniLot:
    """
    Tests v2.0.3 — Mini-lot correctif post-audit runtime.

    Audit : 57 trades, 52 closed_stale (91.2%), 4 trailing_stop.
    Changements :
    1. buy_threshold 25→30, min_score 25→30
    2. trailing_stop_activation_pct 0.20→0.15
    3. min_micro_trend_long=2 (gate obligatoire pour les longs)
    """

    def test_buy_threshold_raised_to_30(self):
        """buy_threshold relevé de 25 à 30 pour filtrer le bruit directionnel."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.buy_threshold == 30, f"Attendu 30, obtenu {scalp.buy_threshold}"

    def test_min_score_raised_to_30(self):
        """min_score relevé de 25 à 30 pour relever le plancher d'entrée."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.min_score == 30, f"Attendu 30, obtenu {scalp.min_score}"

    def test_trailing_activation_lowered_to_015(self):
        """trailing_stop_activation_pct abaissé de 0.20 à 0.15 pour être plus atteignable."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.trailing_stop_activation_pct == 0.15, (
            f"Attendu 0.15, obtenu {scalp.trailing_stop_activation_pct}"
        )

    def test_trailing_pct_unchanged(self):
        """trailing_stop_pct reste à 0.10 — pas de changement du trail width."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.trailing_stop_pct == 0.10

    def test_min_micro_trend_long_is_2(self):
        """Gate micro-tendance obligatoire pour longs : micro_trend_score ≥ 2."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.min_micro_trend_long == 2, (
            f"Attendu 2, obtenu {scalp.min_micro_trend_long}"
        )

    def test_min_micro_trend_long_absent_on_aggressive(self):
        """Le gate micro-tendance n'est PAS activé sur aggressive (sanctuarisé)."""
        agg = PROFILE_PRESETS["aggressive"]
        assert getattr(agg, "min_micro_trend_long", None) is None

    def test_min_micro_trend_long_absent_on_conservative(self):
        """Le gate micro-tendance n'est PAS activé sur conservative."""
        cons = PROFILE_PRESETS["conservative"]
        assert getattr(cons, "min_micro_trend_long", None) is None

    def test_min_capture_still_covers_costs(self):
        """
        Avec trailing activation à 0.15% et trail à 0.10%,
        la capture minimum est 0.05%. C'est faible mais meilleur que stale (0%).
        Le gate économique (expected_capture_pct=0.50%) reste inchangé et valide.
        """
        scalp = PROFILE_PRESETS["scalping"]
        min_capture = scalp.trailing_stop_activation_pct - scalp.trailing_stop_pct
        assert min_capture >= 0.04, f"Min capture trop faible: {min_capture}"
        # Le gate économique utilise expected_capture_pct, pas trailing
        assert scalp.expected_capture_pct == 0.50

    def test_economic_gate_still_passes(self):
        """
        Le gate économique doit toujours passer avec les nouveaux paramètres.
        expected_capture_pct (0.50%) ≥ cost_rt (0.31%) × min_ev_multiple (1.5) = 0.465%.
        """
        scalp = PROFILE_PRESETS["scalping"]
        from app.services.trading_cost_service import get_cost_model
        cost_model = get_cost_model("realistic")
        result = cost_model.estimate_economic_viability(
            position_size_usd=2500,
            leverage=1.0,
            expected_capture_pct=scalp.expected_capture_pct,
            min_ev_multiple=scalp.min_ev_multiple,
        )
        assert result["is_viable"] is True, (
            f"Gate économique ne passe plus : {result}"
        )

    def test_other_params_unchanged(self):
        """Les paramètres non ciblés restent identiques (isolation du mini-lot)."""
        scalp = PROFILE_PRESETS["scalping"]
        # Paramètres qui ne doivent PAS changer
        assert scalp.profit_take_pct == 0.8, "TP ne doit pas changer"
        assert scalp.loss_cut_pct == 0.20, "SL ne doit pas changer"
        assert scalp.max_trades_per_day == 30, "max_trades ne doit pas changer"
        assert scalp.min_market_quality == 50, "market quality ne doit pas changer"
        assert scalp.min_volume_ratio == 0.8, "volume ratio ne doit pas changer"
        assert scalp.min_structural_proofs == 2, "structural proofs ne doit pas changer"
        assert scalp.stale_exit_minutes == 15, "stale exit ne doit pas changer"
        assert scalp.stale_negative_exit_minutes == 5, "stale negative ne doit pas changer"
        assert scalp.momentum_fade_mode == "restricted", "momentum fade mode ne doit pas changer"

    def test_aggressive_not_touched(self):
        """L'aggressive est sanctuarisé — aucun paramètre v2.0.3 ne l'affecte."""
        agg = PROFILE_PRESETS["aggressive"]
        assert agg.buy_threshold == 20, "aggressive buy_threshold doit rester 20"
        assert agg.sell_threshold == 15, "aggressive sell_threshold doit rester 15"
        assert agg.economic_gate_enabled is False, "aggressive economic gate doit rester off"
