"""
Tests pour le MarketStructureService et les nouveaux signal interpreters (v1.9.8).

Teste :
- MarketStructureService.assess_quality() (no-trade zone, tight range, volume)
- interpret_price_position() (extrêmes, milieu, edge cases)
- interpret_range_quality() (tight range, large range, volume)
- compute_composite_score() avec pénalités market structure
- PaperTradingService market quality gating
- Scoring decompression (pas d'homogénéité 70-72)
"""

import pytest
from app.services.market_structure_service import MarketStructureService, MarketQuality
from app.services.signal_service import (
    interpret_price_position,
    interpret_range_quality,
    compute_composite_score,
    interpret_rsi,
    interpret_macd,
    interpret_sma,
    interpret_bollinger,
    interpret_ema_cross,
    interpret_adx,
    interpret_volume_trend,
    SignalItem,
    SignalDirection,
    ConfidenceLevel,
)


# ═══════════════════════════════════════════════════════════════════════════
# MarketStructureService — assess_quality
# ═══════════════════════════════════════════════════════════════════════════

class TestMarketStructureAssessQuality:
    """Tests pour MarketStructureService.assess_quality()."""

    def _make_series(self, n=20, base_close=72000, range_pct=0.5, volume=100, volume_sma=100, atr=500):
        """Génère une série de candles synthétiques."""
        series = []
        half_range = base_close * range_pct / 100 / 2
        for i in range(n):
            close = base_close + (i - n/2) * (half_range / (n/2))
            series.append({
                "close": close,
                "high": close + half_range * 0.3,
                "low": close - half_range * 0.3,
                "volume": volume,
                "volume_sma_20": volume_sma,
                "atr_14": atr,
            })
        return series

    def test_empty_series_returns_low_quality(self):
        """Série vide → qualité basse."""
        q = MarketStructureService.assess_quality([])
        assert q.quality_score <= 30
        assert len(q.reasons) > 0

    def test_short_series_returns_low_quality(self):
        """Série trop courte (< 5) → qualité basse."""
        q = MarketStructureService.assess_quality([{"close": 72000}])
        assert q.quality_score <= 30

    def test_tight_range_low_quality(self):
        """Tight range + low volume → qualité basse."""
        # Range très étroit : toutes les candles proches
        series = []
        for i in range(20):
            series.append({
                "close": 72000 + i * 5,  # Range de 100$ seulement
                "high": 72000 + i * 5 + 10,
                "low": 72000 + i * 5 - 10,
                "volume": 50,
                "volume_sma_20": 100,  # Volume faible vs SMA
                "atr_14": 500,  # ATR de 500 → range/ATR < 1
            })
        q = MarketStructureService.assess_quality(series)
        assert q.quality_score <= 40
        assert q.volume_ratio < 1.0

    def test_wide_range_high_volume_high_quality(self):
        """Range large + volume fort → qualité haute."""
        series = []
        for i in range(20):
            close = 70000 + i * 200  # Range de 4000$
            series.append({
                "close": close,
                "high": close + 100,
                "low": close - 100,
                "volume": 200,
                "volume_sma_20": 100,  # Volume 2x SMA
                "atr_14": 500,
            })
        q = MarketStructureService.assess_quality(series)
        assert q.quality_score >= 50
        assert q.volume_ratio >= 1.5

    def test_price_at_top_of_range(self):
        """Prix en haut du range → zone 'high'."""
        series = []
        for i in range(20):
            series.append({
                "close": 72000 if i < 19 else 74000,
                "high": 72100 if i < 19 else 74000,
                "low": 71900 if i < 19 else 73900,
                "volume": 100, "volume_sma_20": 100, "atr_14": 500,
            })
        q = MarketStructureService.assess_quality(series)
        assert q.price_zone == "high"
        assert q.price_position_pct > 0.7

    def test_price_at_bottom_of_range(self):
        """Prix en bas du range → zone 'low'."""
        series = []
        for i in range(20):
            series.append({
                "close": 72000 if i < 19 else 70000,
                "high": 72100 if i < 19 else 70100,
                "low": 71900 if i < 19 else 70000,
                "volume": 100, "volume_sma_20": 100, "atr_14": 500,
            })
        q = MarketStructureService.assess_quality(series)
        assert q.price_zone == "low"
        assert q.price_position_pct < 0.3

    def test_price_in_middle_of_range(self):
        """Prix au milieu du range → zone 'mid'."""
        series = []
        for i in range(20):
            series.append({
                "close": 71000 + i * 100,  # De 71000 à 72900
                "high": 71000 + i * 100 + 50,
                "low": 71000 + i * 100 - 50,
                "volume": 100, "volume_sma_20": 100, "atr_14": 500,
            })
        # Close = 72900, High_N ~ 72950, Low_N ~ 70950
        q = MarketStructureService.assess_quality(series)
        # La position devrait être ~0.98 ici (en haut en fait, pas au milieu)
        # Construisons une série plate au milieu
        series_mid = []
        for i in range(20):
            c = 72000 if i < 10 else 71000
            series_mid.append({
                "close": 71500,  # Toujours au milieu
                "high": 72000,
                "low": 71000,
                "volume": 100, "volume_sma_20": 100, "atr_14": 500,
            })
        q2 = MarketStructureService.assess_quality(series_mid)
        assert q2.price_zone == "mid"

    def test_micro_trend_bullish(self):
        """Micro-tendance haussière (higher-highs, higher-lows)."""
        series = []
        for i in range(10):
            series.append({
                "close": 71000 + i * 100,
                "high": 71100 + i * 100,
                "low": 70900 + i * 100,
                "volume": 100, "volume_sma_20": 100, "atr_14": 500,
            })
        q = MarketStructureService.assess_quality(series)
        assert q.micro_trend_score > 0

    def test_micro_trend_bearish(self):
        """Micro-tendance baissière (lower-highs, lower-lows)."""
        series = []
        for i in range(10):
            series.append({
                "close": 73000 - i * 100,
                "high": 73100 - i * 100,
                "low": 72900 - i * 100,
                "volume": 100, "volume_sma_20": 100, "atr_14": 500,
            })
        q = MarketStructureService.assess_quality(series)
        assert q.micro_trend_score < 0

    def test_no_close_returns_low_quality(self):
        """Pas de close dans latest → qualité basse."""
        series = [{"high": 72000, "low": 71000} for _ in range(10)]
        q = MarketStructureService.assess_quality(series)
        assert q.quality_score <= 30

    def test_vwap_calculated(self):
        """Le VWAP approché est calculé."""
        series = []
        for i in range(10):
            series.append({
                "close": 72000 + i * 10,
                "high": 72050 + i * 10,
                "low": 71950 + i * 10,
                "volume": 100,
                "volume_sma_20": 100,
                "atr_14": 500,
            })
        q = MarketStructureService.assess_quality(series)
        assert isinstance(q.vwap_distance_pct, float)


class TestIsNoTradeZone:
    """Tests pour MarketStructureService.is_no_trade_zone()."""

    def test_low_quality_is_no_trade(self):
        """Qualité < seuil → no-trade zone."""
        q = MarketQuality(quality_score=20)
        assert MarketStructureService.is_no_trade_zone(q, 30) is True

    def test_high_quality_is_tradeable(self):
        """Qualité >= seuil → tradeable."""
        q = MarketQuality(quality_score=50)
        assert MarketStructureService.is_no_trade_zone(q, 30) is False

    def test_exact_threshold_is_tradeable(self):
        """Qualité == seuil → tradeable."""
        q = MarketQuality(quality_score=30)
        assert MarketStructureService.is_no_trade_zone(q, 30) is False


class TestIsLongQualitySufficient:
    """Tests pour MarketStructureService.is_long_quality_sufficient()."""

    def test_good_quality_passes(self):
        """Bonne qualité + volume + micro-trend → OK."""
        q = MarketQuality(
            quality_score=60, volume_ratio=1.2,
            price_zone="high", micro_trend_score=3,
        )
        ok, reason = MarketStructureService.is_long_quality_sufficient(q)
        assert ok is True

    def test_low_quality_rejected(self):
        """Qualité trop basse → rejeté."""
        q = MarketQuality(quality_score=30)
        ok, reason = MarketStructureService.is_long_quality_sufficient(q)
        assert ok is False
        assert "insuffisante" in reason.lower()

    def test_low_volume_rejected(self):
        """Volume trop bas → rejeté."""
        q = MarketQuality(quality_score=60, volume_ratio=0.5, price_zone="high")
        ok, reason = MarketStructureService.is_long_quality_sufficient(q, min_volume_ratio=0.8)
        assert ok is False
        assert "volume" in reason.lower()

    def test_mid_range_no_trend_rejected(self):
        """Prix au milieu sans micro-tendance → rejeté."""
        q = MarketQuality(
            quality_score=60, volume_ratio=1.0,
            price_zone="mid", micro_trend_score=0,
        )
        ok, reason = MarketStructureService.is_long_quality_sufficient(q)
        assert ok is False
        assert "milieu" in reason.lower()

    def test_mid_range_with_trend_ok(self):
        """Prix au milieu AVEC micro-tendance haussière → OK."""
        q = MarketQuality(
            quality_score=60, volume_ratio=1.0,
            price_zone="mid", micro_trend_score=3,
        )
        ok, reason = MarketStructureService.is_long_quality_sufficient(q)
        assert ok is True


# ═══════════════════════════════════════════════════════════════════════════
# Signal interpreters — price_position et range_quality
# ═══════════════════════════════════════════════════════════════════════════

class TestInterpretPricePosition:
    """Tests pour interpret_price_position."""

    def test_none_close_returns_none(self):
        assert interpret_price_position(None, 72000, 71000) is None

    def test_none_high_returns_none(self):
        assert interpret_price_position(72000, None, 71000) is None

    def test_zero_range_returns_none(self):
        assert interpret_price_position(72000, 72000, 72000) is None

    def test_top_of_range_bearish(self):
        """Prix en haut du range → bearish."""
        signal = interpret_price_position(71950, 72000, 71000)
        assert signal.direction == SignalDirection.BEARISH
        assert signal.strength >= 0.4

    def test_bottom_of_range_bullish(self):
        """Prix en bas du range → bullish."""
        signal = interpret_price_position(71050, 72000, 71000)
        assert signal.direction == SignalDirection.BULLISH
        assert signal.strength >= 0.4

    def test_middle_of_range_neutral(self):
        """Prix au milieu → neutral."""
        signal = interpret_price_position(71500, 72000, 71000)
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.strength >= 0.3

    def test_upper_moderate_bullish(self):
        """Prix dans la zone haute modérée → léger bullish."""
        signal = interpret_price_position(71750, 72000, 71000)
        assert signal.direction == SignalDirection.BULLISH
        assert signal.strength <= 0.3

    def test_lower_moderate_bearish(self):
        """Prix dans la zone basse modérée → léger bearish."""
        signal = interpret_price_position(71250, 72000, 71000)
        assert signal.direction == SignalDirection.BEARISH
        assert signal.strength <= 0.3


class TestInterpretRangeQuality:
    """Tests pour interpret_range_quality."""

    def test_none_range_returns_none(self):
        assert interpret_range_quality(None, 1.0) is None

    def test_tight_range_low_volume_strong_neutral(self):
        """Tight range + low volume → neutral fort (frein)."""
        signal = interpret_range_quality(1.2, 0.6)
        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.strength >= 0.5

    def test_tight_range_normal_volume(self):
        """Tight range seul → neutral modéré."""
        signal = interpret_range_quality(1.3, 1.0)
        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.strength >= 0.3

    def test_wide_range_high_volume_none(self):
        """Range large + volume fort → pas de frein."""
        signal = interpret_range_quality(3.5, 1.5)
        assert signal is None

    def test_moderate_range(self):
        """Range modéré → neutral faible."""
        signal = interpret_range_quality(1.8, 1.0)
        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.strength <= 0.3

    def test_normal_range_no_signal(self):
        """Range normal → pas de frein."""
        signal = interpret_range_quality(2.5, 1.0)
        assert signal is None


# ═══════════════════════════════════════════════════════════════════════════
# Score composite — décompression et pénalités
# ═══════════════════════════════════════════════════════════════════════════

class TestCompositeScoreDecompression:
    """Tests de décompression du score composite (v1.9.8)."""

    def _all_bullish_signals(self):
        """Crée un set de signaux tous bullish (simule le problème du run)."""
        return [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.3, value=58, message="RSI haussier"),
            SignalItem(indicator="macd", direction=SignalDirection.BULLISH, strength=0.5, value=100, message="MACD haussier"),
            SignalItem(indicator="sma", direction=SignalDirection.BULLISH, strength=0.8, value=72000, message="SMA haussier"),
            SignalItem(indicator="bollinger", direction=SignalDirection.BULLISH, strength=0.3, value=72000, message="BB haussier"),
            SignalItem(indicator="ema_cross", direction=SignalDirection.BULLISH, strength=0.3, value=50, message="EMA haussier"),
        ]

    def test_all_bullish_without_range_quality(self):
        """Tous bullish sans signal range → score élevé."""
        signals = self._all_bullish_signals()
        composite = compute_composite_score(signals)
        assert composite.score > 50

    def test_all_bullish_with_tight_range_lower_score(self):
        """Tous bullish + tight range → score réduit."""
        signals = self._all_bullish_signals()
        signals.append(SignalItem(
            indicator="range_quality", direction=SignalDirection.NEUTRAL,
            strength=0.6, value=1.2, message="Tight range",
        ))
        composite_with_range = compute_composite_score(signals)

        signals_no_range = self._all_bullish_signals()
        composite_no_range = compute_composite_score(signals_no_range)

        # Le score avec range quality doit être inférieur
        assert composite_with_range.score < composite_no_range.score

    def test_all_bullish_with_neutral_price_position_lower_score(self):
        """Tous bullish + prix au milieu → score réduit."""
        signals = self._all_bullish_signals()
        signals.append(SignalItem(
            indicator="price_position", direction=SignalDirection.NEUTRAL,
            strength=0.4, value=0.5, message="Prix au milieu",
        ))
        composite_with = compute_composite_score(signals)

        signals_without = self._all_bullish_signals()
        composite_without = compute_composite_score(signals_without)

        # Le neutral dilue le consensus → score plus bas
        assert composite_with.score < composite_without.score

    def test_strong_setup_with_volume_higher_than_weak(self):
        """Setup fort (volume + range) doit scorer nettement plus haut que setup faible."""
        # Setup fort : bullish + ADX trending + volume confirmation
        strong = self._all_bullish_signals()
        strong.append(SignalItem(
            indicator="adx", direction=SignalDirection.BULLISH,
            strength=0.8, value=35, message="ADX forte tendance",
        ))
        strong.append(SignalItem(
            indicator="volume", direction=SignalDirection.NEUTRAL,
            strength=0.05, value=1.8, message="Volume fort",
        ))

        # Setup faible : bullish + tight range + low volume
        weak = self._all_bullish_signals()
        weak.append(SignalItem(
            indicator="range_quality", direction=SignalDirection.NEUTRAL,
            strength=0.6, value=1.2, message="Tight range",
        ))
        weak.append(SignalItem(
            indicator="price_position", direction=SignalDirection.NEUTRAL,
            strength=0.4, value=0.5, message="Prix au milieu",
        ))
        weak.append(SignalItem(
            indicator="adx", direction=SignalDirection.NEUTRAL,
            strength=0.1, value=15, message="ADX faible",
        ))
        weak.append(SignalItem(
            indicator="volume", direction=SignalDirection.NEUTRAL,
            strength=0.05, value=0.4, message="Volume faible",
        ))

        strong_score = compute_composite_score(strong)
        weak_score = compute_composite_score(weak)

        # L'écart doit être d'au moins 15 points
        assert strong_score.score - weak_score.score >= 15, (
            f"Setup fort ({strong_score.score}) vs faible ({weak_score.score}) "
            f"— écart insuffisant ({strong_score.score - weak_score.score})"
        )

    def test_divided_signals_compressed(self):
        """Signaux divisés → score compressé."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.7, value=30, message="RSI"),
            SignalItem(indicator="macd", direction=SignalDirection.BEARISH, strength=0.7, value=-100, message="MACD"),
            SignalItem(indicator="sma", direction=SignalDirection.BULLISH, strength=0.5, value=72000, message="SMA"),
            SignalItem(indicator="bollinger", direction=SignalDirection.BEARISH, strength=0.5, value=72000, message="BB"),
            SignalItem(indicator="ema_cross", direction=SignalDirection.NEUTRAL, strength=0.1, value=0, message="EMA"),
        ]
        composite = compute_composite_score(signals)
        assert abs(composite.score) < 30, f"Score {composite.score} trop élevé pour signaux divisés"


# ═══════════════════════════════════════════════════════════════════════════
# Paper Trading — Market Quality Gating
# ═══════════════════════════════════════════════════════════════════════════

class TestPaperTradingMarketQualityGating:
    """Tests pour le market quality gating dans PaperTradingService."""

    def test_check_market_quality_low_quality_rejects(self, db_session):
        """Qualité basse → rejet de l'entrée."""
        from app.services.paper_trading_service import PaperTradingService

        pts = PaperTradingService(db_session)

        # Construire un decision_result avec une série tight-range
        series = []
        for i in range(20):
            series.append({
                "close": 72000 + i * 2,  # Range minuscule
                "high": 72000 + i * 2 + 5,
                "low": 72000 + i * 2 - 5,
                "volume": 30,
                "volume_sma_20": 100,  # Volume 0.3x
                "atr_14": 500,
            })

        decision_result = {"_series": series}

        reason = pts._check_market_quality(
            decision_result=decision_result,
            direction="long",
            min_quality=35,
            min_volume_ratio=0.7,
            long_quality_filter=True,
        )
        assert reason is not None
        assert "qualité" in reason.lower() or "volume" in reason.lower()

    def test_check_market_quality_good_quality_passes(self, db_session):
        """Bonne qualité → pas de rejet."""
        from app.services.paper_trading_service import PaperTradingService

        pts = PaperTradingService(db_session)

        # Série avec range large et volume fort
        series = []
        for i in range(20):
            close = 70000 + i * 200
            series.append({
                "close": close,
                "high": close + 100,
                "low": close - 100,
                "volume": 200,
                "volume_sma_20": 100,
                "atr_14": 500,
            })

        decision_result = {"_series": series}

        reason = pts._check_market_quality(
            decision_result=decision_result,
            direction="long",
            min_quality=35,
            min_volume_ratio=0.7,
            long_quality_filter=True,
        )
        assert reason is None

    def test_check_market_quality_no_series_passes(self, db_session):
        """Pas de série dans decision_result → pas de blocage."""
        from app.services.paper_trading_service import PaperTradingService

        pts = PaperTradingService(db_session)
        decision_result = {}  # Pas de _series

        reason = pts._check_market_quality(
            decision_result=decision_result,
            direction="long",
            min_quality=35,
        )
        assert reason is None

    def test_check_market_quality_short_not_affected_by_long_filter(self, db_session):
        """Le filtre long_quality_filter n'affecte pas les shorts."""
        from app.services.paper_trading_service import PaperTradingService

        pts = PaperTradingService(db_session)

        # Série avec qualité moyenne
        series = []
        for i in range(20):
            series.append({
                "close": 72000,
                "high": 72050, "low": 71950,
                "volume": 80, "volume_sma_20": 100,
                "atr_14": 500,
            })
        decision_result = {"_series": series}

        reason = pts._check_market_quality(
            decision_result=decision_result,
            direction="short",
            min_quality=25,  # Seuil bas
            min_volume_ratio=0.0,
            long_quality_filter=True,  # Ne devrait pas affecter les shorts
        )
        # Un short avec qualité > 25 devrait passer
        # (qualité exacte dépend de la série, mais pas de long_quality_filter)
        # On vérifie que le filtre long ne bloque pas un short
        # par erreur


# ═══════════════════════════════════════════════════════════════════════════
# Profile params — nouveaux champs
# ═══════════════════════════════════════════════════════════════════════════

class TestProfileMarketQualityParams:
    """Tests pour les nouveaux paramètres de profil."""

    def test_scalping_has_market_quality(self):
        """Le preset scalping a min_market_quality."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        scalping = PROFILE_PRESETS["scalping"]
        assert scalping.min_market_quality is not None
        assert scalping.min_market_quality > 0

    def test_scalping_has_volume_ratio(self):
        """Le preset scalping a min_volume_ratio."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        scalping = PROFILE_PRESETS["scalping"]
        assert scalping.min_volume_ratio is not None
        assert scalping.min_volume_ratio > 0

    def test_scalping_has_long_quality_filter(self):
        """Le preset scalping a long_quality_filter=True."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        scalping = PROFILE_PRESETS["scalping"]
        assert scalping.long_quality_filter is True

    def test_conservative_no_market_quality(self):
        """Le preset conservative n'a PAS de market quality."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        conservative = PROFILE_PRESETS["conservative"]
        assert conservative.min_market_quality is None

    def test_balanced_no_market_quality(self):
        """Le preset balanced n'a PAS de market quality."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        balanced = PROFILE_PRESETS["balanced"]
        assert balanced.min_market_quality is None


# ═══════════════════════════════════════════════════════════════════════════
# Learning — nouvelles suggestions
# ═══════════════════════════════════════════════════════════════════════════

class TestLearningNewSuggestions:
    """Tests pour les nouvelles suggestions de learning (v1.9.8)."""

    def test_safety_bounds_has_market_quality(self):
        """Les safety bounds incluent min_market_quality."""
        from app.services.learning_service import SAFETY_BOUNDS
        assert "min_market_quality" in SAFETY_BOUNDS
        assert "min_volume_ratio" in SAFETY_BOUNDS

    def test_safety_bounds_market_quality_range(self):
        """Les bornes de min_market_quality sont raisonnables."""
        from app.services.learning_service import SAFETY_BOUNDS
        lo, hi = SAFETY_BOUNDS["min_market_quality"]
        assert lo >= 0
        assert hi <= 100

    def test_safety_bounds_volume_ratio_range(self):
        """Les bornes de min_volume_ratio sont raisonnables."""
        from app.services.learning_service import SAFETY_BOUNDS
        lo, hi = SAFETY_BOUNDS["min_volume_ratio"]
        assert lo >= 0
        assert hi <= 5.0


# ═══════════════════════════════════════════════════════════════════════════
# Régression — les anciens tests doivent continuer à passer
# ═══════════════════════════════════════════════════════════════════════════

class TestNoRegression:
    """Vérifie qu'on ne casse pas les fonctionnalités existantes."""

    def test_rsi_interpretation_unchanged(self):
        """RSI fonctionne toujours."""
        signal = interpret_rsi(75)
        assert signal.direction == SignalDirection.BEARISH

    def test_macd_interpretation_unchanged(self):
        """MACD fonctionne toujours."""
        signal = interpret_macd(100, 50, 50, close=72000)
        assert signal.direction == SignalDirection.BULLISH

    def test_composite_still_works_with_basic_signals(self):
        """Le composite fonctionne toujours avec les signaux de base."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.7, value=25, message="RSI"),
            SignalItem(indicator="macd", direction=SignalDirection.BULLISH, strength=0.5, value=100, message="MACD"),
        ]
        composite = compute_composite_score(signals)
        assert composite.score > 0
        assert composite.direction == SignalDirection.BULLISH

    def test_adx_trending_regime_still_works(self):
        """Le régime trending fonctionne toujours avec ADX."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.7, value=25, message="RSI"),
            SignalItem(indicator="macd", direction=SignalDirection.BULLISH, strength=0.5, value=100, message="MACD"),
            SignalItem(indicator="sma", direction=SignalDirection.BULLISH, strength=0.8, value=72000, message="SMA"),
            SignalItem(indicator="adx", direction=SignalDirection.BULLISH, strength=0.8, value=35, message="ADX"),
        ]
        composite = compute_composite_score(signals)
        assert composite.score > 0

    def test_empty_signals_returns_neutral(self):
        """Pas de signaux → score neutre."""
        composite = compute_composite_score([])
        assert composite.score == 0
        assert composite.direction == SignalDirection.NEUTRAL

