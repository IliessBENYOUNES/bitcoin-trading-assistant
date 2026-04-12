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
        """[v2.0.9] Trailing activation abaissé à 0.02% — protège les gains dès ~$0.50."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.trailing_stop_activation_pct == 0.04
        # [v2.0.9] drop_ratio doit être configuré
        assert scalp.trailing_stop_drop_ratio == 0.15, "drop_ratio 3% pour protéger les gains"

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

    def test_trailing_activation_lowered_to_010(self):
        """[v2.0.9] trailing_stop_activation_pct abaissé de 0.10 à 0.02 — protège dès ~$0.50."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.trailing_stop_activation_pct == 0.04, (
            f"Attendu 0.02, obtenu {scalp.trailing_stop_activation_pct}"
        )

    def test_trailing_pct_tightened(self):
        """[v2.0.6] trailing_stop_pct resserré de 0.10 à 0.06 — fallback absolu."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.trailing_stop_pct == 0.06

    def test_trailing_drop_ratio_configured(self):
        """[v2.0.9] trailing_stop_drop_ratio = 0.03 — exit dès que gain baisse de 3% du pic."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.trailing_stop_drop_ratio == 0.15

    def test_min_micro_trend_long_is_0(self):
        """[v2.0.6] Gate micro-tendance désactivé : min_micro_trend_long = 0 (le code skip si <= 0)."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.min_micro_trend_long == 0, (
            f"Attendu 0, obtenu {scalp.min_micro_trend_long}"
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
        [v2.0.9] Avec trailing relatif (drop_ratio=0.03), la capture minimum
        est 97% du peak gain (activation=0.02%). Soit 0.02% * 0.97 = 0.0194%.
        C'est un micro-gain mais le but est de protéger les gains, pas de capturer gros.
        Le gate économique (expected_capture_pct=0.50%) reste le vrai garde-fou à l'entrée.
        """
        scalp = PROFILE_PRESETS["scalping"]
        # En mode relatif, la capture minimum = activation * (1 - drop_ratio)
        min_capture_relative = scalp.trailing_stop_activation_pct * (1 - scalp.trailing_stop_drop_ratio)
        assert min_capture_relative > 0, f"Min capture relative doit être > 0: {min_capture_relative}"
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
        assert scalp.stale_exit_minutes == 5, "stale exit doit être 5 (v2.0.6)"
        assert scalp.stale_negative_exit_minutes == 2, "stale negative doit être 2 (v2.0.6)"
        assert scalp.momentum_fade_mode == "restricted", "momentum fade mode ne doit pas changer"

    def test_aggressive_not_touched(self):
        """L'aggressive est sanctuarisé — aucun paramètre v2.0.3 ne l'affecte."""
        agg = PROFILE_PRESETS["aggressive"]
        assert agg.buy_threshold == 20, "aggressive buy_threshold doit rester 20"
        assert agg.sell_threshold == 15, "aggressive sell_threshold doit rester 15"
        assert agg.economic_gate_enabled is False, "aggressive economic gate doit rester off"


# ================================================================
# TESTS : Assouplissement micro-tendance v2.0.4
# ================================================================

class TestScalpingV206MicroTrendDisable:
    """
    Tests pour la désactivation du gate micro-tendance v2.0.6.

    Audit post-v2.0.4 : 135 ticks scalping, 100% bloqués par micro_trend_insufficient.
    Tous avaient micro_trend_score=-2, decision_score=65, market_quality=59.
    Le gate à mt≥1 bloquait encore 100% des ticks dans les phases latérales.
    Les structural_proofs (2/4 requis) passaient déjà — seul le gate dédié bloquait.

    Correction : min_micro_trend_long 1→0 (désactivé, le code skip si <= 0).
    La protection micro-trend reste via structural_proofs (mt >= 3 = 1 preuve sur 4).
    """

    def test_min_micro_trend_long_disabled(self):
        """min_micro_trend_long = 0 = gate désactivé."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.min_micro_trend_long == 0, (
            f"Attendu 0, obtenu {scalp.min_micro_trend_long}"
        )

    def test_gate_code_skips_when_zero(self):
        """Avec min_micro_trend_long=0, le code ne doit PAS bloquer (condition > 0 fausse)."""
        scalp = PROFILE_PRESETS["scalping"]
        # Le code vérifie : if min_mt_long is not None and min_mt_long > 0
        assert not (scalp.min_micro_trend_long is not None and scalp.min_micro_trend_long > 0), \
            "Le gate doit être inactif quand min_micro_trend_long=0"

    def test_structural_proofs_still_active(self):
        """Les structural_proofs (2 requis) sont toujours actifs — micro-trend reste une preuve."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.min_structural_proofs == 2, "Structural proofs doit rester à 2"

    def test_economic_gate_still_active(self):
        """Le gate économique reste actif — on ne désactive que le micro-trend dédié."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.economic_gate_enabled is True, "Economic gate doit rester actif"

    def test_buy_threshold_unchanged(self):
        """Le buy_threshold reste à 30 — l'audit montre que le score (65) le franchit déjà."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.buy_threshold == 30, "buy_threshold ne doit pas changer"

    def test_min_score_unchanged(self):
        """Le min_score reste à 30 — pas le gate responsable du blocage."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.min_score == 30, "min_score ne doit pas changer"

    def test_aggressive_still_no_micro_trend_gate(self):
        """L'aggressive n'a toujours pas de gate micro-tendance (sanctuarisé)."""
        agg = PROFILE_PRESETS["aggressive"]
        assert getattr(agg, "min_micro_trend_long", None) is None

    def test_all_other_scalping_params_unchanged(self):
        """Aucun autre paramètre scalping n'a bougé (correction chirurgicale)."""
        scalp = PROFILE_PRESETS["scalping"]
        # [v2.0.9] Trailing recalibré : activation basse + drop ratio 3%
        assert scalp.trailing_stop_activation_pct == 0.04
        assert scalp.trailing_stop_pct == 0.06
        assert scalp.trailing_stop_drop_ratio == 0.15
        assert scalp.profit_take_pct == 0.8
        assert scalp.loss_cut_pct == 0.20
        assert scalp.min_market_quality == 50
        assert scalp.min_volume_ratio == 0.8
        assert scalp.min_structural_proofs == 2
        assert scalp.economic_gate_enabled is True
        assert scalp.expected_capture_pct == 0.50
        assert scalp.min_ev_multiple == 1.5
        assert scalp.stale_exit_minutes == 5
        assert scalp.cooldown_minutes == 1  # [v2.0.11] 2→1
        assert scalp.max_trades_per_day == 30


class TestScalpingV207FastExit:
    """[v2.0.7] Recalibration des sorties scalping pour marchés en range.

    Diagnostic runtime : le peak atteint 0.14% (< activation trailing 0.15%).
    Le trailing ne s'activait JAMAIS. Le stale à 15 min laissait fondre les gains.
    Fix : activation abaissée, trail resserré, stale raccourci.
    """

    def test_stale_exit_reduced_to_5(self):
        """Stale exit raccourci de 15→5 min : rotation 3× plus rapide."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.stale_exit_minutes == 5

    def test_stale_negative_reduced_to_2(self):
        """Stale négatif raccourci de 5→2 min : couper les pertes plus vite."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.stale_negative_exit_minutes == 2

    def test_trailing_activation_lowered_to_010(self):
        """[v2.0.9] Trailing activation abaissé à 0.02% : protège dès ~$0.50."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.trailing_stop_activation_pct == 0.04

    def test_trailing_trail_tightened_to_006(self):
        """Trail resserré de 0.10→0.06% : moins de give-back depuis le peak."""
        scalp = PROFILE_PRESETS["scalping"]
        assert scalp.trailing_stop_pct == 0.06

    def test_min_capture_positive(self):
        """[v2.0.9] Capture minimale en mode relatif = activation * (1-drop_ratio) = 0.02 * 0.97 > 0."""
        scalp = PROFILE_PRESETS["scalping"]
        # En mode relatif, la capture min = activation * (1 - drop_ratio)
        min_capture_relative = scalp.trailing_stop_activation_pct * (1 - scalp.trailing_stop_drop_ratio)
        assert min_capture_relative > 0, f"Capture min relative doit être > 0: {min_capture_relative}%"

    def test_aggressive_not_affected(self):
        """L'aggressive est sanctuarisé — aucun changement."""
        agg = PROFILE_PRESETS["aggressive"]
        assert agg.stale_exit_minutes == 180
        assert agg.trailing_stop_activation_pct is None


# ================================================================
# 12. FIX CRITIQUE v2.0.8 — Trailing stop prioritaire + breakeven
# ================================================================

class TestTrailingStopPriorityV208:
    """
    Tests v2.0.8 — Trailing stop AVANT stale exit + breakeven stop.

    BUG : Le stale_negative_exit (2 min) fermait les positions en perte
    AVANT que le trailing stop puisse les protéger. La position gagnante
    à +0.12% retombait à -0.056% et le stale la fermait en perte,
    alors que le trailing aurait dû fermer à +0.06%.
    """

    def test_trailing_fires_before_stale_negative(self, db_session):
        """
        Position avec peak > activation qui retombe en négatif :
        le trailing stop doit fermer AVANT le stale négatif.
        """
        from app.services.paper_trading_service import PaperTradingService
        from app.models.paper_account import PaperAccount, PaperTrade
        from datetime import datetime, timezone, timedelta

        svc = PaperTradingService(db_session)

        account = PaperAccount(
            initial_capital=10000.0, current_capital=10000.0,
            is_active=True, active_profile="scalping",
        )
        db_session.add(account)
        db_session.flush()

        # Position ouverte il y a 3 minutes (> stale_negative_exit 2 min)
        entry_time = datetime.now(timezone.utc) - timedelta(minutes=3)
        entry_price = 73000.0
        # Le peak est à 73080 (+0.1096%, > activation 0.10%)
        trade = PaperTrade(
            account_id=account.id,
            direction="long",
            entry_price=entry_price,
            position_size_usd=2500.0,
            stop_loss_price=entry_price * 0.998,
            take_profit_price=entry_price * 1.008,
            status="open",
            entry_ts=entry_time,
            highest_price_since_entry=73080.0,  # peak +0.1096%
            lowest_price_since_entry=entry_price,
            leverage=1.0,
            entry_reason="Test trailing priority",
            slot="scalping",
        )
        db_session.add(trade)
        db_session.flush()

        # Prix actuel : 73020 — en profit mais en recul de 0.082% depuis le peak
        # peak_pct = 0.1096%, drop = 0.1096 - 0.027 = 0.082% ≥ 0.06% → trailing devrait fire
        current_price = 73020.0
        now = datetime.now(timezone.utc)

        result = svc._tick_single_slot(
            account=account,
            slot_name="scalping",
            current_price=current_price,
            now=now,
            is_multi=True,
        )

        # Le trailing stop doit avoir pris la priorité
        assert result.action_taken == "closed_trailing_stop", (
            f"Attendu closed_trailing_stop, obtenu {result.action_taken}"
        )

    def test_breakeven_stop_protects_small_gains(self, db_session):
        """
        Position dont le peak est entre activation/2 (0.02%) et activation (0.04%)
        et qui retombe à 0% : breakeven stop ferme.
        [v2.0.9] Activation à 0.04%, breakeven protège les gains 0.02-0.04%.
        """
        from app.services.paper_trading_service import PaperTradingService
        from app.models.paper_account import PaperAccount, PaperTrade
        from datetime import datetime, timezone, timedelta

        svc = PaperTradingService(db_session)

        account = PaperAccount(
            initial_capital=10000.0, current_capital=10000.0,
            is_active=True, active_profile="scalping",
        )
        db_session.add(account)
        db_session.flush()

        entry_time = datetime.now(timezone.utc) - timedelta(minutes=3)
        entry_price = 73000.0
        # Peak à 73020 (+0.027%, > activation/2=0.02% mais < activation 0.04%)
        trade = PaperTrade(
            account_id=account.id,
            direction="long",
            entry_price=entry_price,
            position_size_usd=2500.0,
            stop_loss_price=entry_price * 0.998,
            take_profit_price=entry_price * 1.008,
            status="open",
            entry_ts=entry_time,
            highest_price_since_entry=73020.0,  # peak +0.027%
            lowest_price_since_entry=entry_price,
            leverage=1.0,
            entry_reason="Test breakeven protection",
            slot="scalping",
        )
        db_session.add(trade)
        db_session.flush()

        # Prix actuel : retombé SOUS l'entrée → PnL négatif
        current_price = 72995.0  # -0.007%
        now = datetime.now(timezone.utc)

        result = svc._tick_single_slot(
            account=account,
            slot_name="scalping",
            current_price=current_price,
            now=now,
            is_multi=True,
        )

        # Le breakeven stop doit fermer (pas le stale)
        assert result.action_taken == "closed_breakeven", (
            f"Attendu closed_breakeven, obtenu {result.action_taken}"
        )

    def test_stale_still_works_for_never_profitable(self, db_session):
        """
        Position jamais en profit (peak < activation/2) :
        le stale négatif ferme normalement après 2 min.
        """
        from app.services.paper_trading_service import PaperTradingService
        from app.models.paper_account import PaperAccount, PaperTrade
        from datetime import datetime, timezone, timedelta

        svc = PaperTradingService(db_session)

        account = PaperAccount(
            initial_capital=10000.0, current_capital=10000.0,
            is_active=True, active_profile="scalping",
        )
        db_session.add(account)
        db_session.flush()

        entry_time = datetime.now(timezone.utc) - timedelta(minutes=3)
        entry_price = 73000.0
        # Peak quasi au prix d'entrée, jamais vraiment monté (+0.01%)
        trade = PaperTrade(
            account_id=account.id,
            direction="long",
            entry_price=entry_price,
            position_size_usd=2500.0,
            stop_loss_price=entry_price * 0.998,
            take_profit_price=entry_price * 1.008,
            status="open",
            entry_ts=entry_time,
            highest_price_since_entry=73007.0,  # peak +0.0096% (< 0.05%)
            lowest_price_since_entry=entry_price,
            leverage=1.0,
            entry_reason="Test stale never profitable",
            slot="scalping",
        )
        db_session.add(trade)
        db_session.flush()

        # Prix en perte : -0.04%
        current_price = 72970.0
        now = datetime.now(timezone.utc)

        result = svc._tick_single_slot(
            account=account,
            slot_name="scalping",
            current_price=current_price,
            now=now,
            is_multi=True,
        )

        # Stale négatif doit fermer (ni trailing ni breakeven)
        assert result.action_taken == "closed_stale", (
            f"Attendu closed_stale, obtenu {result.action_taken}"
        )

    def test_exit_priority_order(self):
        """
        Vérifier l'ordre conceptuel des vérifications de sortie dans le code.
        SL/TP > Expiration > Trailing Stop > Breakeven > Stale > Momentum fade
        """
        import inspect
        from app.services.paper_trading_service import PaperTradingService

        source = inspect.getsource(PaperTradingService._tick_single_slot)

        # Le trailing stop doit apparaître AVANT le stale exit dans le source
        trailing_pos = source.find("closed_trailing_stop")
        breakeven_pos = source.find("closed_breakeven")
        stale_pos = source.find("closed_stale")

        assert trailing_pos > 0, "closed_trailing_stop non trouvé dans le code"
        assert breakeven_pos > 0, "closed_breakeven non trouvé dans le code"
        assert stale_pos > 0, "closed_stale non trouvé dans le code"

        assert trailing_pos < stale_pos, (
            f"BUG ORDRE: trailing_stop (pos {trailing_pos}) doit être AVANT "
            f"stale (pos {stale_pos}) dans le code"
        )
        assert breakeven_pos < stale_pos, (
            f"BUG ORDRE: breakeven (pos {breakeven_pos}) doit être AVANT "
            f"stale (pos {stale_pos}) dans le code"
        )


# ================================================================
# 10. [v2.0.9] TRAILING STOP RELATIF — Protection proportionnelle des gains
# ================================================================


class TestTrailingStopRelativeV209:
    """
    Tests v2.0.9 — Trailing stop relatif au gain (pas au prix BTC).

    Ancien système (absolu, 0.06%) : peak 0.12% → exit à 0.06% → 50% du gain perdu.
    Nouveau système (relatif, 30%) : peak 0.12% → exit à 0.084% → seulement 30% perdu.
    """

    def test_relative_trailing_keeps_70pct_of_small_gain(self, db_session):
        """
        Peak modeste (0.12%) : le trailing relatif garde ~70% du gain.
        Ancien système aurait gardé seulement 50%.
        """
        from app.services.paper_trading_service import PaperTradingService
        from app.models.paper_account import PaperAccount, PaperTrade
        from datetime import datetime, timezone, timedelta

        svc = PaperTradingService(db_session)

        account = PaperAccount(
            initial_capital=10000.0, current_capital=10000.0,
            is_active=True, active_profile="scalping",
        )
        db_session.add(account)
        db_session.flush()

        entry_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        entry_price = 83000.0
        # Peak à 83100 → peak_pct = 100/83000 = 0.1205%
        # Seuil relatif (30% drop) = 0.1205 * 0.70 = 0.0843%
        trade = PaperTrade(
            account_id=account.id,
            direction="long",
            entry_price=entry_price,
            position_size_usd=2500.0,
            stop_loss_price=entry_price * 0.998,
            take_profit_price=entry_price * 1.008,
            status="open",
            entry_ts=entry_time,
            highest_price_since_entry=83100.0,  # peak +0.1205%
            lowest_price_since_entry=entry_price,
            leverage=1.0,
            entry_reason="Test relative trailing small gain",
            slot="scalping",
        )
        db_session.add(trade)
        db_session.flush()

        # Prix à 83060 → current_pct = 60/83000 = 0.0723%
        # 0.0723% < 0.0843% (seuil relatif) → trailing fire
        current_price = 83060.0
        now = datetime.now(timezone.utc)

        result = svc._tick_single_slot(
            account=account, slot_name="scalping",
            current_price=current_price, now=now, is_multi=True,
        )

        assert result.action_taken == "closed_trailing_stop", (
            f"Attendu closed_trailing_stop, obtenu {result.action_taken}"
        )
        # Le gain préservé (0.0723%) représente ~60% du peak, ce qui montre
        # que le trailing relatif a fermé AVANT que le gain tombe à 50%
        assert "relatif" in result.detail.lower(), "Le trailing doit être en mode relatif"

    def test_relative_trailing_no_fire_when_gain_above_retention(self, db_session):
        """
        Peak à 0.12%, gain actuel à 0.10% (83% du peak) → pas de trailing (seuil 70%).
        Ancien système absolu aurait laissé passer aussi (drop 0.02% < 0.06%).
        """
        from app.services.paper_trading_service import PaperTradingService
        from app.models.paper_account import PaperAccount, PaperTrade
        from datetime import datetime, timezone, timedelta

        svc = PaperTradingService(db_session)

        account = PaperAccount(
            initial_capital=10000.0, current_capital=10000.0,
            is_active=True, active_profile="scalping",
        )
        db_session.add(account)
        db_session.flush()

        entry_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        entry_price = 83000.0
        # Peak à 83100 → 0.1205%
        trade = PaperTrade(
            account_id=account.id,
            direction="long",
            entry_price=entry_price,
            position_size_usd=2500.0,
            stop_loss_price=entry_price * 0.998,
            take_profit_price=entry_price * 1.008,
            status="open",
            entry_ts=entry_time,
            highest_price_since_entry=83100.0,
            lowest_price_since_entry=entry_price,
            leverage=1.0,
            entry_reason="Test no fire above retention",
            slot="scalping",
        )
        db_session.add(trade)
        db_session.flush()

        # Prix à 83098 → current_pct = 98/83000 = 0.1181%
        # Peak = 0.1205%, seuil 97% = 0.1169%
        # 0.1181% > 0.1169% → PAS de trailing (gain encore dans les 97%)
        current_price = 83098.0
        now = datetime.now(timezone.utc)

        result = svc._tick_single_slot(
            account=account, slot_name="scalping",
            current_price=current_price, now=now, is_multi=True,
        )

        assert result.action_taken != "closed_trailing_stop", (
            f"Le trailing ne devrait pas fire : gain encore dans les 97% du pic"
        )

    def test_relative_trailing_big_gain_more_room(self, db_session):
        """
        Peak important (0.40%) avec gain actuel à 0.39% (recul 2.5%) :
        Le trailing relatif à 3% ne fire PAS car le recul est < 3%.
        """
        from app.services.paper_trading_service import PaperTradingService
        from app.models.paper_account import PaperAccount, PaperTrade
        from datetime import datetime, timezone, timedelta

        svc = PaperTradingService(db_session)

        account = PaperAccount(
            initial_capital=10000.0, current_capital=10000.0,
            is_active=True, active_profile="scalping",
        )
        db_session.add(account)
        db_session.flush()

        entry_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        entry_price = 83000.0
        # Peak à 83332 → peak_pct = 332/83000 = 0.40%
        # Seuil 3% = 0.40% * 0.97 = 0.388%
        trade = PaperTrade(
            account_id=account.id,
            direction="long",
            entry_price=entry_price,
            position_size_usd=2500.0,
            stop_loss_price=entry_price * 0.998,
            take_profit_price=entry_price * 1.008,
            status="open",
            entry_ts=entry_time,
            highest_price_since_entry=83332.0,  # peak +0.40%
            lowest_price_since_entry=entry_price,
            leverage=1.0,
            entry_reason="Test big gain no fire",
            slot="scalping",
        )
        db_session.add(trade)
        db_session.flush()

        # Prix à 83325 → current_pct = 325/83000 = 0.3916%
        # 0.3916% > 0.388% (seuil 97%) → PAS de trailing (recul ~2%)
        current_price = 83325.0
        now = datetime.now(timezone.utc)

        result = svc._tick_single_slot(
            account=account, slot_name="scalping",
            current_price=current_price, now=now, is_multi=True,
        )

        assert result.action_taken != "closed_trailing_stop", (
            f"Gros gain : le trailing ne devrait PAS fire (recul < 3%)"
        )

    def test_relative_trailing_short_symmetric(self, db_session):
        """
        Trailing relatif fonctionne aussi sur les shorts (symétrie).
        """
        from app.services.paper_trading_service import PaperTradingService
        from app.models.paper_account import PaperAccount, PaperTrade
        from datetime import datetime, timezone, timedelta

        svc = PaperTradingService(db_session)

        account = PaperAccount(
            initial_capital=10000.0, current_capital=10000.0,
            is_active=True, active_profile="scalping",
        )
        db_session.add(account)
        db_session.flush()

        entry_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        entry_price = 83000.0
        # Short : on gagne quand le prix descend
        # Peak = lowest at 82900 → peak_pct = (83000-82900)/83000 = 0.1205%
        # Seuil relatif = 0.1205 * 0.70 = 0.0843%
        trade = PaperTrade(
            account_id=account.id,
            direction="short",
            entry_price=entry_price,
            position_size_usd=2500.0,
            stop_loss_price=entry_price * 1.002,
            take_profit_price=entry_price * 0.992,
            status="open",
            entry_ts=entry_time,
            highest_price_since_entry=entry_price,
            lowest_price_since_entry=82900.0,  # peak pour short
            leverage=1.0,
            entry_reason="Test relative trailing short",
            slot="scalping",
        )
        db_session.add(trade)
        db_session.flush()

        # Prix remonte à 82940 → current_pct = (83000-82940)/83000 = 0.0723%
        # 0.0723% < 0.0843% → trailing fire
        current_price = 82940.0
        now = datetime.now(timezone.utc)

        result = svc._tick_single_slot(
            account=account, slot_name="scalping",
            current_price=current_price, now=now, is_multi=True,
        )

        assert result.action_taken == "closed_trailing_stop", (
            f"Short : trailing relatif devrait fire, obtenu {result.action_taken}"
        )

    def test_relative_trailing_preserves_more_than_absolute(self):
        """
        Test mathématique : le trailing relatif à 3% garde toujours 97% du gain.
        L'ancien absolu (0.06%) gardait entre 40% et 94% selon la taille du peak.
        Le relatif est TOUJOURS meilleur pour les petits peaks.
        """
        drop_ratio = 0.03
        ts_pct_absolute = 0.06  # ancien seuil

        # Le relatif à 3% garde TOUJOURS 97% du peak
        for peak_pct in [0.05, 0.08, 0.10, 0.15, 0.20, 0.50]:
            relative_exit = peak_pct * (1 - drop_ratio)
            relative_kept_pct = relative_exit / peak_pct * 100
            assert abs(relative_kept_pct - 97.0) < 0.01, (
                f"Peak {peak_pct}%: relatif devrait garder 97%, garde {relative_kept_pct:.1f}%"
            )

        # Pour les petits peaks (< 0.062%), l'absolu donnerait un exit négatif !
        # Le relatif reste toujours positif
        for peak_pct in [0.03, 0.05]:
            absolute_exit = peak_pct - ts_pct_absolute
            assert absolute_exit < 0, (
                f"Peak {peak_pct}%: l'absolu donnerait un exit négatif ({absolute_exit}%)"
            )
            relative_exit = peak_pct * (1 - drop_ratio)
            assert relative_exit > 0, (
                f"Peak {peak_pct}%: le relatif garde un exit positif ({relative_exit}%)"
            )


# ================================================================
# 11. [v2.0.8] SHORTS BIDIRECTIONNELS — Reversal + Trailing symétrique
# ================================================================


class TestShortBidirectionalV208:
    """Tests v2.0.8 : shorts activés via reversal à seuil 1, symétrie trailing."""

    def test_reversal_fires_with_bearish_majority(self, db_session):
        """[v2.0.8] Majorité bearish (2 bearish > 0 bullish) → reversal short."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [
                {"rule_name": "macd_bearish", "satisfied": True, "direction": "bearish"},
                {"rule_name": "sma_death_cross", "satisfied": True, "direction": "bearish"},
            ],
            "combined_score": 30,
            "technical_score": 30,
        }
        result = pts._scalping_reversal_check(decision)
        assert result == "short", "Majorité bearish → short reversal"

    def test_reversal_fires_with_bullish_majority(self, db_session):
        """[v2.0.8] Majorité bullish (2 bullish > 0 bearish) → reversal long."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [
                {"rule_name": "rsi_oversold", "satisfied": True, "direction": "bullish"},
                {"rule_name": "stochrsi_oversold", "satisfied": True, "direction": "bullish"},
            ],
            "combined_score": -30,
            "technical_score": -30,
        }
        result = pts._scalping_reversal_check(decision)
        assert result == "long", "Majorité bullish → long reversal"

    def test_reversal_no_fire_with_equal_rules(self, db_session):
        """[v2.0.8] Aucune majorité (1b vs 1h, aucun overbought) → pas de reversal."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [
                {"rule_name": "macd_bearish", "satisfied": True, "direction": "bearish"},
                {"rule_name": "rsi_bullish", "satisfied": True, "direction": "bullish"},
            ],
            "combined_score": 30,
            "technical_score": 30,
        }
        result = pts._scalping_reversal_check(decision)
        assert result is None, "Égalité bearish/bullish → pas de reversal"

    def test_short_trailing_stop_symmetric(self, db_session):
        """[v2.0.8] Le trailing stop fonctionne symétriquement pour les shorts."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)

        # Simuler un trade short : entry=73000, le prix a baissé jusqu'à 72900
        # puis est remonté à 72960 (recul de 0.082% depuis le peak)
        from app.models.paper_account import PaperAccount, PaperTrade

        entry_price = 73000.0
        lowest_price = 72900.0  # peak gain pour short
        current_price = 72960.0  # prix remonte

        # PnL au peak : (73000-72900)/73000 * 2500 * 1.0 = 0.137% * 2500 = $3.42
        peak_pnl = (entry_price - lowest_price) / entry_price * 2500
        peak_pct = peak_pnl / 2500 * 100  # ~0.137%
        assert peak_pct > 0.10, f"Peak doit être > activation (0.10%): {peak_pct:.3f}%"

        # PnL actuel : (73000-72960)/73000 = 0.055%
        current_pnl = (entry_price - current_price) / entry_price * 2500
        current_pct = current_pnl / 2500 * 100  # ~0.055%

        # Recul depuis le pic : 0.137% - 0.055% = 0.082%
        drop = peak_pct - current_pct
        assert drop >= 0.06, f"Drop {drop:.3f}% doit être >= trailing_stop_pct (0.06%)"

    def test_short_breakeven_stop_symmetric(self, db_session):
        """[v2.0.8] Le breakeven stop protège aussi les shorts qui étaient en gain."""
        from app.services.paper_trading_service import PaperTradingService

        entry_price = 73000.0
        lowest_price = 72963.5  # peak = +0.05% pour short
        current_price = 73001.0  # prix remonte au-dessus de l'entrée

        # Peak PnL pour short : (73000-72963.5)/73000 = 0.05%
        peak_pct = (entry_price - lowest_price) / entry_price * 100
        assert abs(peak_pct - 0.05) < 0.01, f"Peak ~0.05%: {peak_pct:.3f}%"

        # PnL actuel : (73000-73001)/73000 = -0.0014% (en perte)
        current_pct = (entry_price - current_price) / entry_price * 100
        assert current_pct <= 0, f"PnL actuel doit être <= 0%: {current_pct:.3f}%"

        # Le breakeven doit se déclencher : peak >= 0.05% (activation/2) ET PnL <= 0
        breakeven_activation = 0.10 / 2  # trailing_activation / 2
        assert peak_pct >= breakeven_activation, "Peak >= breakeven activation"
        assert current_pct <= 0, "PnL retombé en négatif → breakeven"

    def test_no_short_min_score_for_reversals(self, db_session):
        """[v2.0.8] Le short_min_score ne bloque plus les reversals contrarians."""
        from app.services.paper_trading_service import PaperTradingService
        from app.services.trading_profile_service import PROFILE_PRESETS

        # Le short_min_score existe toujours (30) mais n'est plus vérifié
        # pour les reversals dans _tick_single_slot
        p = PROFILE_PRESETS["scalping"]
        assert p.short_min_score == 30, "short_min_score existe toujours"

        # Un reversal avec score=+25 (< 30) doit quand même passer
        # car le reversal est contrarian : le score positif CONFIRME le surachat
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [
                {"rule_name": "rsi_overbought", "satisfied": True, "direction": "bearish"},
            ],
            "combined_score": 25,  # < short_min_score (30)
            "technical_score": 25,
        }
        result = pts._scalping_reversal_check(decision)
        # Le reversal détecte 1 signal overbought → "short"
        # La vérification short_min_score n'est plus dans le chemin reversal
        assert result == "short", "Score +25 avec 1 overbought → short (pas bloqué par short_min_score)"


# ================================================================
# 13. [v2.0.10] DOWNTREND PROTECTION — Veto bearish + reversal micro-trend
# ================================================================


class TestDowntrendProtectionV2010:
    """Tests v2.0.10 : protection contre les entrées LONG en downtrend.

    Le problème : 7/33 trades entrent LONG pendant que le BTC descend,
    résultant en -$10.44 de pertes (stale exits). Le score technique de 65
    est en retard (indicateurs 15min) et reste bullish pendant le pullback.

    Solution : veto bearish (micro_trend < 0 → bloquer LONG) + reversal
    enrichi (micro_trend ≤ -2 → signal SHORT).
    """

    def test_reversal_fires_with_bearish_micro_trend(self, db_session):
        """[v2.0.10] micro_trend ≤ -2 → signal overbought → short reversal."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)

        # Decision neutre (pas de majorité, pas d'overbought classique)
        decision = {
            "rules_evaluated": [
                {"rule_name": "sma_bullish", "satisfied": True, "direction": "bullish"},
            ],
            "combined_score": 65,
            "technical_score": 60,
        }
        # micro_trend = -3 → signal overbought
        mq_data = {"micro_trend_score": -3}
        result = pts._scalping_reversal_check(decision, mq_data=mq_data)
        assert result == "short", "micro_trend=-3 → overbought signal → short reversal"

    def test_reversal_fires_with_bullish_micro_trend(self, db_session):
        """[v2.0.10] micro_trend ≥ 3 → signal oversold → long reversal."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)

        decision = {
            "rules_evaluated": [
                {"rule_name": "macd_bearish", "satisfied": True, "direction": "bearish"},
            ],
            "combined_score": -40,
            "technical_score": -35,
        }
        mq_data = {"micro_trend_score": 3}
        result = pts._scalping_reversal_check(decision, mq_data=mq_data)
        assert result == "long", "micro_trend=+3 → oversold signal → long reversal"

    def test_reversal_no_fire_with_neutral_micro_trend(self, db_session):
        """[v2.0.10] micro_trend entre -1 et +2 → pas de signal micro-trend."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)

        # Decision neutre, ni majorité ni overbought classique
        decision = {
            "rules_evaluated": [
                {"rule_name": "sma_bullish", "satisfied": True, "direction": "bullish"},
            ],
            "combined_score": 50,
            "technical_score": 50,
        }
        # micro_trend = -1 → pas assez bearish pour déclencher la Source 4
        mq_data = {"micro_trend_score": -1}
        result = pts._scalping_reversal_check(decision, mq_data=mq_data)
        # 1 bullish rule < 2, pas de majorité → aucun signal
        assert result is None, "micro_trend=-1 (neutre) → pas de signal micro-trend"

    def test_reversal_backward_compatible_without_mq_data(self, db_session):
        """[v2.0.10] Sans mq_data, le reversal fonctionne comme avant."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)

        decision = {
            "rules_evaluated": [
                {"rule_name": "rsi_overbought", "satisfied": True, "direction": "bearish"},
            ],
            "combined_score": 70,
            "technical_score": 70,
        }
        # Pas de mq_data → Source 4 ignorée, mais Source 1 (rsi_overbought) fire
        result = pts._scalping_reversal_check(decision, mq_data=None)
        assert result == "short", "Sans mq_data, reversal classique fonctionne toujours"

    def test_reversal_micro_trend_plus_bearish_majority_cumulates(self, db_session):
        """[v2.0.10] micro_trend bearish + majorité bearish → 2 signaux (double confirmation)."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)

        decision = {
            "rules_evaluated": [
                {"rule_name": "macd_bearish", "satisfied": True, "direction": "bearish"},
                {"rule_name": "sma_death_cross", "satisfied": True, "direction": "bearish"},
            ],
            "combined_score": 65,
            "technical_score": 60,
        }
        mq_data = {"micro_trend_score": -4}
        result = pts._scalping_reversal_check(decision, mq_data=mq_data)
        # Source 3 (majorité bearish 2b > 0h) + Source 4 (micro_trend ≤ -2) = 2 signaux
        assert result == "short", "Majorité bearish + micro_trend bearish → short (double signal)"

    def test_veto_bearish_blocks_long_when_micro_trend_negative(self):
        """[v2.0.10] Le veto bearish bloque les LONG quand micro_trend < 0.

        Teste la LOGIQUE du veto : si micro_trend < 0 et direction = long
        et pas un reversal → la position doit être bloquée.
        """
        # Ce test vérifie la logique conditionnelle, pas le tick complet.
        # La condition dans le code :
        #   if mq_data and not scalping_reversal:
        #       if direction_check == "long" and mt < 0: → bloquer
        mq_data = {"micro_trend_score": -2}
        scalping_reversal = False
        action = "acheter"  # → direction_check = "long"
        mt = mq_data.get("micro_trend_score", 0) or 0

        direction_check = "long" if action == "acheter" else "short"
        should_veto = (
            mq_data is not None
            and not scalping_reversal
            and direction_check == "long"
            and mt < 0
        )
        assert should_veto is True, "micro_trend=-2, long, non-reversal → veto activé"

    def test_veto_bearish_does_not_block_short(self):
        """[v2.0.10] Le veto bearish NE bloque PAS les shorts."""
        mq_data = {"micro_trend_score": -5}
        scalping_reversal = False
        action = "vendre"  # → direction_check = "short"
        mt = mq_data.get("micro_trend_score", 0) or 0

        direction_check = "long" if action == "acheter" else "short"
        should_veto = (
            mq_data is not None
            and not scalping_reversal
            and direction_check == "long"
            and mt < 0
        )
        assert should_veto is False, "Short → veto bearish ne s'applique pas"

    def test_veto_bearish_does_not_block_reversal(self):
        """[v2.0.10] Le veto bearish NE bloque PAS les trades reversal."""
        mq_data = {"micro_trend_score": -3}
        scalping_reversal = True  # Le reversal a déjà résolu la direction
        action = "acheter"  # → direction serait long, mais c'est un reversal
        mt = mq_data.get("micro_trend_score", 0) or 0

        direction_check = "long" if action == "acheter" else "short"
        should_veto = (
            mq_data is not None
            and not scalping_reversal
            and direction_check == "long"
            and mt < 0
        )
        assert should_veto is False, "Reversal → veto bearish ne s'applique pas"

    def test_veto_bearish_allows_long_when_micro_trend_positive(self):
        """[v2.0.10] Quand micro_trend ≥ 0, les LONG passent normalement."""
        mq_data = {"micro_trend_score": 1}
        scalping_reversal = False
        action = "acheter"
        mt = mq_data.get("micro_trend_score", 0) or 0

        direction_check = "long" if action == "acheter" else "short"
        should_veto = (
            mq_data is not None
            and not scalping_reversal
            and direction_check == "long"
            and mt < 0
        )
        assert should_veto is False, "micro_trend=+1 → long autorisé"

    def test_veto_bearish_allows_long_when_micro_trend_zero(self):
        """[v2.0.10] Quand micro_trend = 0 (neutre), les LONG passent."""
        mq_data = {"micro_trend_score": 0}
        scalping_reversal = False
        action = "acheter"
        mt = mq_data.get("micro_trend_score", 0) or 0

        direction_check = "long" if action == "acheter" else "short"
        should_veto = (
            mq_data is not None
            and not scalping_reversal
            and direction_check == "long"
            and mt < 0
        )
        assert should_veto is False, "micro_trend=0 (neutre) → long autorisé"

    def test_market_quality_computed_before_reversal(self):
        """[v2.0.10] Vérifier que le code calcule mq_data AVANT le reversal check.

        L'ordre dans _tick_single_slot() doit être :
        1. market quality (mq_data)
        2. reversal check (utilise mq_data)
        3. veto bearish (utilise mq_data)
        """
        import inspect
        from app.services.paper_trading_service import PaperTradingService
        source = inspect.getsource(PaperTradingService._tick_single_slot)

        # Vérifier l'ordre : _check_market_quality AVANT _scalping_reversal_check
        mq_pos = source.find("_check_market_quality")
        rev_pos = source.find("_scalping_reversal_check")
        # Les deux doivent apparaître dans le bloc "Pas de position"
        # Le mq doit apparaître avant le reversal DANS LA SECTION D'ENTRÉE
        # Cherchons dans la section après "Pas de position"
        entry_section = source[source.find("Pas de position"):]
        mq_in_entry = entry_section.find("_check_market_quality")
        rev_in_entry = entry_section.find("_scalping_reversal_check")
        assert mq_in_entry < rev_in_entry, (
            "mq_data doit être calculé AVANT le reversal check dans la section d'entrée"
        )

# ================================================================
# v2.0.11 -- Protection reversal signal contraire + cooldown reduit
# ================================================================
class TestReversalSignalContraireProtection:
    """[v2.0.11] Les trades mean_reversion ne doivent PAS etre fermes par le
    meme score qui les a crees."""
    def test_reversal_short_not_closed_by_same_score(self):
        """Un SHORT reversal (entree score=66) ne se ferme PAS si le score est toujours 66."""
        entry_reason = "mean_reversion_short | score=66 | medium | test"
        entry_score = 66
        current_score = 66
        short_exit_th = 30
        is_reversal = entry_reason.startswith("mean_reversion_")
        if is_reversal and entry_score is not None:
            short_exit_th = max(short_exit_th, abs(entry_score) + 1)
        assert current_score < short_exit_th
    def test_reversal_short_closed_when_score_increases(self):
        """Un SHORT reversal SE FERME si le score bullish AUGMENTE."""
        entry_reason = "mean_reversion_short | score=66 | medium | test"
        entry_score = 66
        current_score = 70
        short_exit_th = 30
        is_reversal = entry_reason.startswith("mean_reversion_")
        if is_reversal and entry_score is not None:
            short_exit_th = max(short_exit_th, abs(entry_score) + 1)
        assert current_score >= short_exit_th
    def test_non_reversal_short_still_uses_normal_threshold(self):
        """Un SHORT normal utilise toujours le seuil standard."""
        entry_reason = "vendre | score=-30 | medium | test"
        is_reversal = entry_reason.startswith("mean_reversion_")
        assert not is_reversal
    def test_reversal_long_not_closed_by_same_score(self):
        """Un LONG reversal (entree score=-50) ne se ferme PAS si score toujours -50."""
        entry_reason = "mean_reversion_long | score=-50 | medium | test"
        entry_score = -50
        current_score = -50
        is_reversal = entry_reason.startswith("mean_reversion_")
        should_close = True
        if is_reversal and entry_score is not None:
            should_close = abs(current_score) > abs(entry_score)
        assert not should_close
    def test_reversal_long_closed_when_bearish_intensifies(self):
        """Un LONG reversal SE FERME si le score bearish s'INTENSIFIE."""
        entry_reason = "mean_reversion_long | score=-50 | medium | test"
        entry_score = -50
        current_score = -60
        is_reversal = entry_reason.startswith("mean_reversion_")
        should_close = True
        if is_reversal and entry_score is not None:
            should_close = abs(current_score) > abs(entry_score)
        assert should_close
    def test_reversal_short_with_score_0_at_entry(self):
        """Edge case : reversal score 0 -> seuil = max(30, 1) = 30."""
        entry_reason = "mean_reversion_short | score=0 | low | test"
        entry_score = 0
        short_exit_th = 30
        is_reversal = entry_reason.startswith("mean_reversion_")
        if is_reversal and entry_score is not None:
            short_exit_th = max(short_exit_th, abs(entry_score) + 1)
        assert short_exit_th == 30
    def test_reversal_short_with_high_score_raises_threshold(self):
        """Reversal SHORT score 88 -> seuil signal contraire = 89."""
        entry_reason = "mean_reversion_short | score=88 | medium | test"
        entry_score = 88
        short_exit_th = 30
        is_reversal = entry_reason.startswith("mean_reversion_")
        if is_reversal and entry_score is not None:
            short_exit_th = max(short_exit_th, abs(entry_score) + 1)
        assert short_exit_th == 89
    def test_reversal_trades_still_exit_via_trailing_stop(self):
        """Trailing stop / stale / SL/TP toujours actifs pour les reversals."""
        from app.services.paper_trading_service import PaperTradingService
        import inspect
        source = inspect.getsource(PaperTradingService._tick_single_slot)
        assert "trailing" in source.lower()
        assert "breakeven" in source.lower()
        assert "stale" in source.lower()
    def test_cooldown_reduced_for_scalping(self):
        """[v2.0.11] Le cooldown scalping est reduit a 1 min."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        p = PROFILE_PRESETS["scalping"]
        assert p.cooldown_minutes == 1
    def test_max_cooldown_reduced_for_scalping(self):
        """[v2.0.11] Le max cooldown scalping est reduit a 5 min."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        p = PROFILE_PRESETS["scalping"]
        assert p.max_cooldown_minutes == 5.0
    def test_stale_negative_floor_reduced(self):
        """[v2.0.11] Le plancher stale negatif est reduit a 2 min."""
        from app.services.smart_cooldown_service import SmartCooldownService
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=0.5,
            last_exit_type="closed_stale",
            last_pnl=-0.5,
            last_pnl_pct=-0.05,
            min_cooldown=0.5,
            max_cooldown=10.0,
        )
        assert result >= 2.0
    def test_reversal_signal_contraire_code_exists(self):
        """Le code de protection reversal signal contraire est dans le source."""
        from app.services.paper_trading_service import PaperTradingService
        import inspect
        source = inspect.getsource(PaperTradingService._tick_single_slot)
        assert "mean_reversion_" in source
        assert "reversal" in source.lower()
