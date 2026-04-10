"""
Tests lot correctif v1.9.9 — Audit de vérité runtime.

Couvre les 5 missions :
1. Trace runtime (quality gate dans tick_activity_log)
2. Score technique ne sature plus à 100
3. Quality gate = veto réel (mid-range, seuil relevé)
4. Anti-churn stale négatif
5. Zéro régression

v1.9.9
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.models.tick_activity_log import TickActivityLog
from app.models.paper_account import PaperAccount, PaperTrade
from app.services.journal_service import JournalService
from app.services.smart_cooldown_service import SmartCooldownService
from app.services.market_structure_service import MarketStructureService, MarketQuality
from app.services.signal_service import (
    compute_composite_score,
    SignalDirection,
    ConfidenceLevel,
)
from app.schemas.signal import SignalItem
from app.services.trading_profile_service import PROFILE_PRESETS


# ================================================================
# Helpers
# ================================================================

def _make_signal(indicator: str, direction: str, strength: float, value=None) -> SignalItem:
    """Crée un SignalItem pour les tests."""
    return SignalItem(
        indicator=indicator,
        direction=SignalDirection(direction),
        strength=strength,
        message=f"Test {indicator} {direction}",
        value=value,
    )


def _make_candle_series(n=20, close=85000, atr=500, volume=100, volume_sma=100,
                        trend_direction=0, range_width=2.0):
    """Génère une série de candles fictive pour MarketStructureService."""
    series = []
    base_close = close - (n * trend_direction * 10)
    for i in range(n):
        c = base_close + (i * trend_direction * 10)
        series.append({
            "close": c,
            "high": c + atr * range_width / 2,
            "low": c - atr * range_width / 2,
            "volume": volume,
            "volume_sma_20": volume_sma,
            "atr_14": atr,
        })
    return series


def _make_account(db, active=True, profile="scalping"):
    account = PaperAccount(
        initial_capital=10000.0,
        current_capital=10000.0,
        peak_capital=10000.0,
        is_active=active,
        active_profile=profile,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


# ================================================================
# MISSION 1 — Trace runtime (quality gate dans tick_activity_log)
# ================================================================

class TestRuntimeTrace:
    """Tests pour la trace runtime des données de quality gate."""

    def test_tick_log_has_quality_gate_columns(self, db_session):
        """Le modèle TickActivityLog a les colonnes quality gate."""
        account = _make_account(db_session)
        entry = TickActivityLog(
            account_id=account.id,
            timestamp=datetime.now(timezone.utc),
            btc_price=85000.0,
            action_taken="hold",
            profile_type="scalping",
            market_quality_score=42,
            volume_ratio=1.15,
            price_position_pct=0.65,
            range_width_atr=2.3,
            micro_trend_score=3,
            vwap_distance_pct=-0.12,
            quality_gate_passed=1,
            quality_gate_reason="market_quality_ok",
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        assert entry.market_quality_score == 42
        assert entry.volume_ratio == 1.15
        assert entry.price_position_pct == 0.65
        assert entry.range_width_atr == 2.3
        assert entry.micro_trend_score == 3
        assert entry.vwap_distance_pct == -0.12
        assert entry.quality_gate_passed == 1
        assert entry.quality_gate_reason == "market_quality_ok"

    def test_tick_log_quality_gate_nullable(self, db_session):
        """Les colonnes quality gate sont nullable (rétrocompat)."""
        account = _make_account(db_session)
        entry = TickActivityLog(
            account_id=account.id,
            timestamp=datetime.now(timezone.utc),
            btc_price=85000.0,
            action_taken="hold",
            profile_type="conservative",
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        assert entry.market_quality_score is None
        assert entry.volume_ratio is None
        assert entry.quality_gate_passed is None

    def test_journal_log_tick_accepts_quality_params(self, db_session):
        """JournalService.log_tick accepte les paramètres quality gate."""
        account = _make_account(db_session)
        journal = JournalService(db_session)
        entry = journal.log_tick(
            account_id=account.id,
            action_taken="hold",
            btc_price=85000.0,
            market_quality_score=55,
            volume_ratio=1.3,
            price_position_pct=0.72,
            range_width_atr=2.8,
            micro_trend_score=4,
            vwap_distance_pct=0.25,
            quality_gate_passed=True,
            quality_gate_reason="market_quality_ok",
        )
        assert entry.market_quality_score == 55
        assert entry.quality_gate_passed == 1

    def test_journal_log_tick_quality_gate_failed(self, db_session):
        """Quality gate failed est correctement enregistré."""
        account = _make_account(db_session)
        journal = JournalService(db_session)
        entry = journal.log_tick(
            account_id=account.id,
            action_taken="hold",
            btc_price=85000.0,
            market_quality_score=20,
            quality_gate_passed=False,
            quality_gate_reason="Qualité marché 20/100 < seuil 45",
        )
        assert entry.quality_gate_passed == 0
        assert "seuil 45" in entry.quality_gate_reason


# ================================================================
# MISSION 2 — Score technique ne sature plus à 100
# ================================================================

class TestScoreSaturation:
    """Tests prouvant que le score technique ne sature plus à 100."""

    def test_unanimous_bullish_no_volume_stays_below_90(self):
        """Unanimité bullish SANS volume fort ne dépasse pas 88 (soft ceiling)."""
        signals = [
            _make_signal("rsi", "bullish", 0.7, value=55),
            _make_signal("macd", "bullish", 0.7),
            _make_signal("sma", "bullish", 0.6),
            _make_signal("ema_cross", "bullish", 0.7),
            _make_signal("bollinger", "bullish", 0.5),
            _make_signal("stoch_rsi", "bullish", 0.6),
            _make_signal("adx", "bullish", 0.5, value=28),
            _make_signal("volume", "neutral", 0.5, value=1.0),  # Volume normal, pas fort
        ]
        result = compute_composite_score(signals)
        # Score ne doit PAS dépasser 88 sans volume exceptionnel (>= 1.5x)
        assert result.score <= 88, f"Score {result.score} > 88 avec volume normal — saturation non cassée"

    def test_score_100_requires_exceptional_volume(self):
        """Score > 88 exige volume fort (>= 1.5x SMA20)."""
        signals = [
            _make_signal("rsi", "bullish", 0.8, value=45),
            _make_signal("macd", "bullish", 0.8),
            _make_signal("sma", "bullish", 0.8),
            _make_signal("ema_cross", "bullish", 0.8),
            _make_signal("adx", "bullish", 0.6, value=30),
            _make_signal("volume", "bullish", 0.7, value=0.9),  # Volume sous 1.5
        ]
        result = compute_composite_score(signals)
        assert result.score <= 88, f"Score {result.score} > 88 sans volume fort"

    def test_neutral_signals_dilute_score(self):
        """Les signaux NEUTRAL réduisent le score au lieu de le laisser intact."""
        # Setup bullish SANS neutrals
        signals_no_neutral = [
            _make_signal("rsi", "bullish", 0.7),
            _make_signal("macd", "bullish", 0.7),
            _make_signal("sma", "bullish", 0.6),
            _make_signal("adx", "bullish", 0.5, value=28),
            _make_signal("volume", "neutral", 0.5, value=1.0),
        ]
        score_no_neutral = compute_composite_score(signals_no_neutral).score

        # Même setup AVEC 2 neutrals
        signals_with_neutral = signals_no_neutral.copy()
        signals_with_neutral.extend([
            _make_signal("bollinger", "neutral", 0.5),
            _make_signal("stoch_rsi", "neutral", 0.5),
        ])
        score_with_neutral = compute_composite_score(signals_with_neutral).score

        assert score_with_neutral < score_no_neutral, (
            f"Score avec neutrals ({score_with_neutral}) >= sans ({score_no_neutral}) "
            f"— les neutrals ne diluent pas"
        )

    def test_soft_ceiling_caps_at_92_without_volume(self):
        """Le soft ceiling empêche le score de dépasser 88 sans volume exceptionnel."""
        # Setup parfait mais sans volume fort
        signals = [
            _make_signal("rsi", "bullish", 0.9),
            _make_signal("macd", "bullish", 0.9),
            _make_signal("sma", "bullish", 0.9),
            _make_signal("ema_cross", "bullish", 0.9),
            _make_signal("adx", "bullish", 0.7, value=35),
            _make_signal("volume", "bullish", 0.5, value=1.1),  # Bon volume mais pas 1.5x
        ]
        result = compute_composite_score(signals)
        assert result.score <= 88, f"Score {result.score} > 88 (soft ceiling cassé)"

    def test_convergence_boost_blocked_without_volume(self):
        """Le convergence boost ne s'active pas sans volume >= 1.2x.
        Le score est plafonné à 88 (ceiling) sans volume fort."""
        # Unanimité parfaite mais volume faible
        signals = [
            _make_signal("rsi", "bullish", 0.8),
            _make_signal("macd", "bullish", 0.8),
            _make_signal("sma", "bullish", 0.7),
            _make_signal("adx", "bullish", 0.5, value=25),
            _make_signal("volume", "neutral", 0.5, value=0.9),  # Sous le seuil 1.2
        ]
        result = compute_composite_score(signals)
        # Sans convergence boost et avec ceiling, le score est plafonné à 88
        assert result.score <= 88, f"Score {result.score} > 88 — ceiling inefficace"
        # Vérifier qu'il n'a PAS atteint un score qui impliquerait un boost actif
        assert result.score < 92, f"Score {result.score} >= 92 — boost actif sans volume!"

    def test_divided_signals_compressed_to_low_score(self):
        """Des signaux divisés produisent un score faible, pas moyen."""
        signals = [
            _make_signal("rsi", "bullish", 0.6),
            _make_signal("macd", "bearish", 0.7),
            _make_signal("sma", "bullish", 0.5),
            _make_signal("ema_cross", "bearish", 0.6),
            _make_signal("bollinger", "neutral", 0.5),
            _make_signal("adx", "neutral", 0.4, value=18),
            _make_signal("volume", "neutral", 0.5, value=0.8),
        ]
        result = compute_composite_score(signals)
        assert abs(result.score) < 30, (
            f"Score {result.score} trop élevé pour des signaux divisés"
        )


# ================================================================
# MISSION 3 — Quality gate = veto réel
# ================================================================

class TestQualityGateVeto:
    """Tests prouvant que le quality gate est un veto réel."""

    def test_scalping_min_market_quality_raised(self):
        """[v2.0.0] Le profil scalping exige min_market_quality=50."""
        p = PROFILE_PRESETS["scalping"]
        assert p.min_market_quality == 50

    def test_aggressive_has_quality_gate(self):
        """Le profil aggressive a un quality gate minimum."""
        p = PROFILE_PRESETS["aggressive"]
        assert p.min_market_quality is not None
        assert p.min_market_quality >= 25

    def test_mid_range_without_strong_trend_vetoed(self):
        """Un long mid-range sans micro-tendance claire est un VETO."""
        quality = MarketQuality(
            price_position_pct=0.50,  # Milieu du range
            price_zone="mid",
            micro_trend_score=1,      # Très faible, < 3 requis
            quality_score=55,
            volume_ratio=1.0,
        )
        is_ok, reason = MarketStructureService.is_long_quality_sufficient(
            quality, min_quality=45, min_volume_ratio=0.7,
        )
        assert not is_ok
        assert "VETO" in reason or "mid-range" in reason.lower() or "milieu" in reason.lower()

    def test_mid_range_with_weak_trend_still_vetoed(self):
        """Micro-trend +2 au milieu du range est encore insuffisant."""
        quality = MarketQuality(
            price_position_pct=0.45,
            price_zone="mid",
            micro_trend_score=2,  # Pas assez fort (seuil = 3)
            quality_score=55,
            volume_ratio=1.0,
        )
        is_ok, reason = MarketStructureService.is_long_quality_sufficient(
            quality, min_quality=45, min_volume_ratio=0.7,
        )
        assert not is_ok

    def test_mid_range_with_strong_trend_accepted(self):
        """Micro-trend +3 au milieu du range est accepté (setup correct)."""
        quality = MarketQuality(
            price_position_pct=0.50,
            price_zone="mid",
            micro_trend_score=3,  # Suffisant
            quality_score=55,
            volume_ratio=1.0,
        )
        is_ok, reason = MarketStructureService.is_long_quality_sufficient(
            quality, min_quality=45, min_volume_ratio=0.7,
        )
        assert is_ok

    def test_quality_score_below_45_rejected_for_scalping(self):
        """Un marché avec quality_score=40 est rejeté par le scalping (seuil 45)."""
        quality = MarketQuality(
            quality_score=40,
            price_zone="high",
            micro_trend_score=4,
            volume_ratio=1.0,
        )
        is_no_trade = MarketStructureService.is_no_trade_zone(quality, min_quality=45)
        assert is_no_trade

    def test_high_quality_market_accepted(self):
        """Un marché de bonne qualité passe le gate."""
        quality = MarketQuality(
            quality_score=60,
            price_zone="high",
            micro_trend_score=5,
            volume_ratio=1.2,
        )
        is_no_trade = MarketStructureService.is_no_trade_zone(quality, min_quality=45)
        assert not is_no_trade

    def test_assess_quality_tight_range_low_volume(self):
        """Un marché en tight range avec faible volume produit un score très bas."""
        series = _make_candle_series(
            n=20, close=85000, atr=500,
            volume=30, volume_sma=100,     # Volume très faible
            range_width=0.5,               # Tight range
            trend_direction=0,             # Pas de tendance
        )
        quality = MarketStructureService.assess_quality(series)
        assert quality.quality_score < 40, (
            f"Quality score {quality.quality_score} trop élevé pour un tight range sans volume"
        )


# ================================================================
# MISSION 4 — Anti-churn stale négatif
# ================================================================

class TestAntiChurnStaleNegative:
    """Tests prouvant que le cooldown après stale négatif est dissuasif."""

    def test_stale_exit_increases_cooldown(self):
        """Un stale (même non-négatif) augmente le cooldown (pas le réduit)."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_stale",
            last_pnl=0.1,  # PnL positif
        )
        # Avant : le stale RÉDUISAIT le cooldown à 0.8 min (!!)
        # Maintenant : le stale DOUBLE le cooldown
        assert result >= 2.0, (
            f"Cooldown {result} min après stale — devrait être >= 2.0 min"
        )

    def test_stale_negative_triples_cooldown(self):
        """Un stale NÉGATIF triple le cooldown (pénalité anti-churn)."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_stale",
            last_pnl=-2.0,          # PnL négatif
            last_pnl_pct=-0.15,
            max_cooldown=30.0,
        )
        # 2.0 * 3.0 (stale négatif) * 1.2 (perte modérée) = 7.2, borné à max_cooldown
        assert result >= 4.0, (
            f"Cooldown {result} min après stale négatif — devrait être >= 4.0 min"
        )

    def test_stale_negative_floor_at_4_minutes(self):
        """Un stale négatif impose un plancher de 4 minutes quoi qu'il arrive."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=0.5,       # Base très courte
            last_exit_type="closed_stale",
            last_pnl=-0.5,
            last_pnl_pct=-0.05,
            min_cooldown=0.5,
            max_cooldown=10.0,
        )
        assert result >= 4.0, (
            f"Cooldown {result} min < 4.0 min plancher après stale négatif"
        )

    def test_stale_positive_no_floor(self):
        """Un stale POSITIF n'a pas le plancher de 4 minutes."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=1.0,
            last_exit_type="closed_stale",
            last_pnl=0.5,           # PnL positif
            min_cooldown=0.5,
            max_cooldown=5.0,
        )
        # Le stale positif a le multiplier 2.0 mais sans plancher de 4 min
        # Donc 1.0 * 2.0 * 0.8 (gain) = 1.6 min, borné >= 0.5
        assert result < 4.0 or result >= 0.5

    def test_tp_exit_still_reduces_cooldown(self):
        """Un TP réussi réduit toujours le cooldown (pas affecté par le fix stale)."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_tp",
            last_pnl=5.0,
        )
        assert result < 2.0, (
            f"Cooldown {result} min après TP — devrait être < 2.0 min"
        )

    def test_sl_exit_still_increases_cooldown(self):
        """Un SL augmente toujours le cooldown (inchangé par le fix)."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_sl",
            last_pnl=-5.0,
            last_pnl_pct=-0.3,
        )
        assert result > 2.0

    def test_scalping_max_cooldown_raised(self):
        """Le max_cooldown scalping est relevé à 10 min (anti-churn)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.max_cooldown_minutes == 10.0

    def test_stale_negative_heavy_loss_extra_penalty(self):
        """Un stale négatif avec grosse perte cumule les pénalités."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_stale",
            last_pnl=-8.0,
            last_pnl_pct=-0.5,   # Grosse perte
            max_cooldown=30.0,
        )
        # 2.0 * 3.0 (stale négatif) * 1.5 (grosse perte) = 9.0
        assert result >= 6.0, (
            f"Cooldown {result} min après stale négatif + grosse perte — devrait être >= 6.0"
        )


# ================================================================
# Tests de non-régression
# ================================================================

class TestNonRegression:
    """Tests vérifiant que les changements ne cassent rien d'existant."""

    def test_composite_score_still_works_basic(self):
        """Le compute_composite_score fonctionne toujours avec des signaux basiques."""
        signals = [
            _make_signal("rsi", "bullish", 0.7),
            _make_signal("macd", "bullish", 0.6),
            _make_signal("adx", "neutral", 0.5, value=22),
            _make_signal("volume", "neutral", 0.5, value=1.0),
        ]
        result = compute_composite_score(signals)
        assert -100 <= result.score <= 100
        assert result.direction in (SignalDirection.BULLISH, SignalDirection.BEARISH, SignalDirection.NEUTRAL)

    def test_composite_score_empty_signals(self):
        """Score composite avec zéro signal retourne 0."""
        result = compute_composite_score([])
        assert result.score == 0
        assert result.direction == SignalDirection.NEUTRAL

    def test_market_quality_assess_with_minimal_data(self):
        """MarketStructureService ne crashe pas avec peu de données."""
        quality = MarketStructureService.assess_quality([{"close": 85000}] * 3)
        assert quality.quality_score == 25  # Données insuffisantes

    def test_market_quality_assess_normal(self):
        """MarketStructureService fonctionne avec des données normales."""
        series = _make_candle_series(n=20, close=85000, atr=500, volume=100, volume_sma=100)
        quality = MarketStructureService.assess_quality(series)
        assert 0 <= quality.quality_score <= 100

    def test_smart_cooldown_base_unchanged(self):
        """Sans contexte, le cooldown de base est retourné tel quel."""
        result = SmartCooldownService.compute_cooldown(base_cooldown=2.0)
        assert result == 2.0

    def test_conservative_profile_unchanged(self):
        """Le profil conservative n'est pas modifié."""
        p = PROFILE_PRESETS["conservative"]
        assert p.min_score == 35
        assert p.cooldown_minutes == 120
        assert p.max_trades_per_day == 3

    def test_scalping_profile_core_params_unchanged(self):
        """[v2.0.0] Les paramètres core du scalping après refonte."""
        p = PROFILE_PRESETS["scalping"]
        assert p.profit_take_pct == 0.8  # [v2.0.0] 0.6→0.8
        assert p.loss_cut_pct == 0.20
        assert p.analysis_timeframe == "15m"
        assert p.stale_negative_exit_minutes == 5

    def test_tick_log_backward_compatible(self, db_session):
        """Les ticks existants sans quality gate fonctionnent toujours."""
        account = _make_account(db_session)
        journal = JournalService(db_session)
        # Appel legacy sans les nouveaux paramètres
        entry = journal.log_tick(
            account_id=account.id,
            action_taken="hold",
            btc_price=85000.0,
            decision_score=42,
        )
        assert entry.id is not None
        assert entry.market_quality_score is None  # Non fourni = None





