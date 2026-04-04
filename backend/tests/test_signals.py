"""
Tests pour le moteur de signaux (v0.7).

Tests couverts :
1. Interpréteur RSI : surachat, survente, neutre, None
2. Interpréteur MACD : croisements haussier/baissier, neutre, None
3. Interpréteur SMA : au-dessus/dessous, mixte, None
4. Interpréteur Bollinger : hors bandes, dans bandes, None
5. Score composite : convergence, divergence, vide
6. Résumé lisible
7. Intégration avec vraie DB
8. Endpoint API /market/signals
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.signal_service import (
    interpret_rsi,
    interpret_macd,
    interpret_sma,
    interpret_bollinger,
    interpret_adx,
    interpret_volume_trend,
    compute_composite_score,
    generate_summary,
    SignalService,
)
from app.schemas.signal import (
    SignalItem,
    SignalDirection,
    CompositeScore,
    ConfidenceLevel,
)


# ============================================================
# TESTS INTERPRÉTEUR RSI
# ============================================================

class TestInterpretRsi:
    """Tests pour interpret_rsi."""

    def test_rsi_none_returns_none(self):
        """RSI None → pas de signal."""
        assert interpret_rsi(None) is None

    def test_rsi_strongly_overbought(self):
        """RSI >= 80 → bearish fort."""
        signal = interpret_rsi(85.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH
        assert signal.strength >= 0.8
        assert signal.indicator == "rsi"
        assert "85" in signal.message

    def test_rsi_overbought(self):
        """RSI 70-80 → bearish modéré."""
        signal = interpret_rsi(72.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH
        assert 0.5 <= signal.strength <= 0.8
        assert "72" in signal.message

    def test_rsi_strongly_oversold(self):
        """RSI <= 20 → bullish fort."""
        signal = interpret_rsi(15.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH
        assert signal.strength >= 0.8

    def test_rsi_oversold(self):
        """RSI 20-30 → bullish modéré."""
        signal = interpret_rsi(25.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH
        assert 0.5 <= signal.strength <= 0.8

    def test_rsi_neutral(self):
        """RSI 45-55 → neutre."""
        signal = interpret_rsi(50.0)
        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.strength <= 0.3

    def test_rsi_slightly_bearish(self):
        """RSI 30-45 → légèrement baissier."""
        signal = interpret_rsi(40.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH
        assert signal.strength <= 0.5

    def test_rsi_slightly_bullish(self):
        """RSI 55-70 → légèrement haussier."""
        signal = interpret_rsi(60.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH
        assert signal.strength <= 0.5

    def test_rsi_boundary_70(self):
        """RSI = 70 exactement → overbought."""
        signal = interpret_rsi(70.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH

    def test_rsi_boundary_30(self):
        """RSI = 30 exactement → oversold."""
        signal = interpret_rsi(30.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH


# ============================================================
# TESTS INTERPRÉTEUR MACD
# ============================================================

class TestInterpretMacd:
    """Tests pour interpret_macd."""

    def test_macd_none_returns_none(self):
        """MACD None → pas de signal."""
        assert interpret_macd(None, None, None) is None

    def test_macd_signal_none_returns_none(self):
        """Signal None → pas de signal."""
        assert interpret_macd(100.0, None, 50.0) is None

    def test_macd_bullish_crossover(self):
        """MACD > Signal, hist > 0 → bullish."""
        signal = interpret_macd(150.0, 100.0, 50.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH
        assert signal.indicator == "macd"

    def test_macd_bearish_crossover(self):
        """MACD < Signal, hist < 0 → bearish."""
        signal = interpret_macd(-50.0, 100.0, -150.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH

    def test_macd_strong_divergence(self):
        """Grand écart MACD-Signal → haute force."""
        signal = interpret_macd(600.0, 0.0, 600.0)
        assert signal is not None
        assert signal.strength >= 0.8

    def test_macd_weak_divergence(self):
        """Petit écart MACD-Signal → faible force."""
        signal = interpret_macd(5.0, 0.0, 5.0)
        assert signal is not None
        assert signal.strength <= 0.3

    def test_macd_equal_neutral(self):
        """MACD = Signal → neutre."""
        signal = interpret_macd(100.0, 100.0, 0.0)
        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL

    def test_macd_transition_bullish(self):
        """MACD > Signal mais hist < 0 → bullish atténué."""
        signal = interpret_macd(110.0, 100.0, -5.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH
        # La force doit être réduite (transition)

    def test_macd_transition_bearish(self):
        """MACD < Signal mais hist > 0 → bearish atténué."""
        signal = interpret_macd(90.0, 100.0, 5.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH


# ============================================================
# TESTS INTERPRÉTEUR SMA
# ============================================================

class TestInterpretSma:
    """Tests pour interpret_sma."""

    def test_sma_none_close_returns_none(self):
        """Close None → pas de signal."""
        assert interpret_sma(None, 100.0, 100.0, 100.0) is None

    def test_sma_none_sma20_returns_none(self):
        """SMA20 None → pas de signal."""
        assert interpret_sma(100.0, None, 100.0, 100.0) is None

    def test_sma_above_all(self):
        """Prix au-dessus de toutes les SMA → bullish fort."""
        signal = interpret_sma(100000.0, 99000.0, 98000.0, 95000.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH
        assert signal.strength >= 0.6

    def test_sma_below_all(self):
        """Prix en dessous de toutes les SMA → bearish fort."""
        signal = interpret_sma(90000.0, 95000.0, 98000.0, 100000.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH
        assert signal.strength >= 0.6

    def test_sma_above_20_below_50_200(self):
        """Prix au-dessus SMA20, sous SMA50 et SMA200 → bearish modéré."""
        signal = interpret_sma(97000.0, 96000.0, 98000.0, 100000.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH

    def test_sma_only_sma20_bullish(self):
        """Seulement SMA20 disponible, prix au-dessus → bullish."""
        signal = interpret_sma(100000.0, 99000.0, None, None)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH

    def test_sma_only_sma20_bearish(self):
        """Seulement SMA20 disponible, prix en dessous → bearish."""
        signal = interpret_sma(98000.0, 99000.0, None, None)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH


# ============================================================
# TESTS INTERPRÉTEUR BOLLINGER
# ============================================================

class TestInterpretBollinger:
    """Tests pour interpret_bollinger."""

    def test_bollinger_none_returns_none(self):
        """Paramètres None → pas de signal."""
        assert interpret_bollinger(None, 100.0, 95.0, 90.0) is None
        assert interpret_bollinger(95.0, None, 95.0, 90.0) is None
        assert interpret_bollinger(95.0, 100.0, None, 90.0) is None
        assert interpret_bollinger(95.0, 100.0, 95.0, None) is None

    def test_bollinger_above_upper(self):
        """Prix >= bande supérieure → bearish."""
        signal = interpret_bollinger(101000.0, 100000.0, 97000.0, 94000.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH
        assert signal.strength >= 0.5

    def test_bollinger_below_lower(self):
        """Prix <= bande inférieure → bullish."""
        signal = interpret_bollinger(93000.0, 100000.0, 97000.0, 94000.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH
        assert signal.strength >= 0.5

    def test_bollinger_upper_half(self):
        """Prix entre mid et upper → légèrement bullish."""
        signal = interpret_bollinger(98500.0, 100000.0, 97000.0, 94000.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH
        assert signal.strength <= 0.6

    def test_bollinger_lower_half(self):
        """Prix entre lower et mid → légèrement bearish."""
        signal = interpret_bollinger(95500.0, 100000.0, 97000.0, 94000.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH
        assert signal.strength <= 0.6

    def test_bollinger_at_mid(self):
        """Prix = mid → neutre."""
        signal = interpret_bollinger(97000.0, 100000.0, 97000.0, 94000.0)
        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL

    def test_bollinger_zero_width(self):
        """Bandes de largeur 0 → neutre."""
        signal = interpret_bollinger(100.0, 100.0, 100.0, 100.0)
        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL


# ============================================================
# TESTS INTERPRÉTEUR ADX (v1.2)
# ============================================================

class TestInterpretAdx:
    """Tests pour interpret_adx — filtre de tendance."""

    def test_adx_none_returns_none(self):
        """ADX None → pas de signal."""
        assert interpret_adx(None) is None

    def test_adx_very_strong_trend_bullish(self):
        """ADX >= 40 + DI+ > DI- → tendance haussière très forte."""
        signal = interpret_adx(45.0, plus_di=30.0, minus_di=15.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH
        assert signal.strength >= 0.7
        assert "très" in signal.message.lower()

    def test_adx_very_strong_trend_bearish(self):
        """ADX >= 40 + DI- > DI+ → tendance baissière très forte."""
        signal = interpret_adx(42.0, plus_di=12.0, minus_di=28.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BEARISH
        assert signal.strength >= 0.7

    def test_adx_strong_trend(self):
        """ADX 25-40 → tendance confirmée."""
        signal = interpret_adx(30.0, plus_di=25.0, minus_di=15.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH
        assert 0.3 <= signal.strength <= 0.7

    def test_adx_weak_trend(self):
        """ADX 20-25 → tendance faible émergente."""
        signal = interpret_adx(22.0, plus_di=18.0, minus_di=16.0)
        assert signal is not None
        assert signal.strength <= 0.3

    def test_adx_no_trend(self):
        """ADX < 20 → pas de tendance, signal neutre."""
        signal = interpret_adx(15.0)
        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL
        assert "sans tendance" in signal.message

    def test_adx_no_di_defaults(self):
        """Sans DI, le signal utilise le défaut bullish."""
        signal = interpret_adx(35.0)
        assert signal is not None
        assert signal.direction == SignalDirection.BULLISH


# ============================================================
# TESTS INTERPRÉTEUR VOLUME (v1.2)
# ============================================================

class TestInterpretVolumeTrend:
    """Tests pour interpret_volume_trend — confirmation par volume."""

    def test_volume_none_returns_none(self):
        """Volume None → pas de signal."""
        assert interpret_volume_trend(None, 1000.0) is None
        assert interpret_volume_trend(1000.0, None) is None

    def test_volume_very_high(self):
        """Volume > 2x SMA → signal de confirmation."""
        signal = interpret_volume_trend(2500.0, 1000.0)
        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL  # Volume n'a pas de direction
        assert "très élevé" in signal.message

    def test_volume_above_average(self):
        """Volume 1.5-2x SMA → confirmation modérée."""
        signal = interpret_volume_trend(1700.0, 1000.0)
        assert signal is not None
        assert "supérieur" in signal.message

    def test_volume_very_low(self):
        """Volume < 0.5x SMA → méfiance."""
        signal = interpret_volume_trend(300.0, 1000.0)
        assert signal is not None
        assert "faible" in signal.message

    def test_volume_normal_returns_none(self):
        """Volume normal (0.5-1.5x) → pas de signal particulier."""
        assert interpret_volume_trend(1000.0, 1000.0) is None
        assert interpret_volume_trend(800.0, 1000.0) is None

    def test_volume_sma_zero_returns_none(self):
        """Volume SMA = 0 → pas de signal."""
        assert interpret_volume_trend(1000.0, 0.0) is None


# ============================================================
# TESTS MACD RELATIF AU PRIX (v1.2)
# ============================================================

class TestMacdRelativeThresholds:
    """Tests pour le MACD avec seuils en % du prix."""

    def test_macd_at_low_price_moderate_diff(self):
        """A $3000, un MACD diff de 50 = 1.67% → force élevée."""
        signal = interpret_macd(150.0, 100.0, 50.0, close=3000.0)
        assert signal is not None
        assert signal.strength >= 0.7  # 50/3000 = 1.67% > 1.5% threshold

    def test_macd_at_high_price_same_diff(self):
        """A $100000, un MACD diff de 50 = 0.05% → force très faible."""
        signal = interpret_macd(150.0, 100.0, 50.0, close=100000.0)
        assert signal is not None
        assert signal.strength <= 0.3  # 50/100000 = 0.05% < 0.1% threshold

    def test_macd_at_high_price_strong_diff(self):
        """A $100000, un MACD diff de 2000 = 2% → force élevée."""
        signal = interpret_macd(3000.0, 1000.0, 2000.0, close=100000.0)
        assert signal is not None
        assert signal.strength >= 0.9  # 2000/100000 = 2% > 1.5%

    def test_macd_without_close_uses_absolute(self):
        """Sans close, les seuils absolus sont utilisés (compatibilité)."""
        signal = interpret_macd(600.0, 0.0, 600.0)
        assert signal is not None
        assert signal.strength >= 0.8  # 600 > 500 threshold absolute


# ============================================================
# TESTS SCORE COMPOSITE
# ============================================================

class TestCompositeScore:
    """Tests pour compute_composite_score."""

    def test_empty_signals(self):
        """Aucun signal → score 0, neutre."""
        result = compute_composite_score([])
        assert result.score == 0
        assert result.direction == SignalDirection.NEUTRAL
        assert result.consensus == "no_data"

    def test_all_bullish(self):
        """Tous signaux bullish → score positif, consensus unanime.
        Note v1.2 : Sans ADX >= 25, la confiance plafonne a MEDIUM (plus conservateur)."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.7, value=25.0, message="RSI oversold"),
            SignalItem(indicator="macd", direction=SignalDirection.BULLISH, strength=0.6, value=100.0, message="MACD bullish"),
            SignalItem(indicator="sma", direction=SignalDirection.BULLISH, strength=0.8, value=100000.0, message="Above SMA"),
            SignalItem(indicator="bollinger", direction=SignalDirection.BULLISH, strength=0.5, value=93000.0, message="Below lower"),
        ]
        result = compute_composite_score(signals)
        assert result.score > 0
        assert result.direction == SignalDirection.BULLISH
        assert result.consensus == "unanimous"
        assert result.confidence == ConfidenceLevel.MEDIUM  # v1.2: MEDIUM sans ADX
        assert result.bullish_count == 4
        assert result.bearish_count == 0

    def test_all_bullish_with_adx_confirmation(self):
        """Tous signaux bullish + ADX fort → confiance HIGH (v1.2)."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.7, value=25.0, message="RSI oversold"),
            SignalItem(indicator="macd", direction=SignalDirection.BULLISH, strength=0.6, value=100.0, message="MACD bullish"),
            SignalItem(indicator="sma", direction=SignalDirection.BULLISH, strength=0.8, value=100000.0, message="Above SMA"),
            SignalItem(indicator="bollinger", direction=SignalDirection.BULLISH, strength=0.5, value=93000.0, message="Below lower"),
            SignalItem(indicator="adx", direction=SignalDirection.BULLISH, strength=0.8, value=35.0, message="ADX confirme"),
        ]
        result = compute_composite_score(signals)
        assert result.score > 0
        assert result.direction == SignalDirection.BULLISH
        assert result.confidence == ConfidenceLevel.HIGH  # ADX confirme → HIGH

    def test_all_bearish(self):
        """Tous signaux bearish → score négatif."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BEARISH, strength=0.8, value=80.0, message="RSI overbought"),
            SignalItem(indicator="macd", direction=SignalDirection.BEARISH, strength=0.7, value=-100.0, message="MACD bearish"),
            SignalItem(indicator="sma", direction=SignalDirection.BEARISH, strength=0.6, value=90000.0, message="Below SMA"),
        ]
        result = compute_composite_score(signals)
        assert result.score < 0
        assert result.direction == SignalDirection.BEARISH
        assert result.consensus == "unanimous"
        assert result.bearish_count == 3

    def test_mixed_signals_divided(self):
        """Signaux mixtes → divided."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.7, value=25.0, message="RSI oversold"),
            SignalItem(indicator="macd", direction=SignalDirection.BEARISH, strength=0.7, value=-100.0, message="MACD bearish"),
        ]
        result = compute_composite_score(signals)
        assert result.consensus in ("divided", "majority")

    def test_score_bounded(self):
        """Le score est toujours entre -100 et +100."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=1.0, value=10.0, message="Very strong"),
        ]
        result = compute_composite_score(signals)
        assert -100 <= result.score <= 100

    def test_neutral_signals_low_confidence(self):
        """Signaux neutres → confiance basse."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.NEUTRAL, strength=0.1, value=50.0, message="RSI neutral"),
            SignalItem(indicator="macd", direction=SignalDirection.NEUTRAL, strength=0.1, value=0.0, message="MACD neutral"),
        ]
        result = compute_composite_score(signals)
        assert result.direction == SignalDirection.NEUTRAL
        assert result.neutral_count == 2

    def test_strong_majority(self):
        """3 bullish + 1 bearish → strong_majority."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.7, value=25.0, message="RSI oversold"),
            SignalItem(indicator="macd", direction=SignalDirection.BULLISH, strength=0.6, value=100.0, message="MACD bullish"),
            SignalItem(indicator="sma", direction=SignalDirection.BULLISH, strength=0.8, value=100000.0, message="Above SMA"),
            SignalItem(indicator="bollinger", direction=SignalDirection.BEARISH, strength=0.3, value=101000.0, message="Above upper"),
        ]
        result = compute_composite_score(signals)
        assert result.consensus == "strong_majority"
        assert result.direction == SignalDirection.BULLISH


# ============================================================
# TESTS RÉSUMÉ
# ============================================================

class TestGenerateSummary:
    """Tests pour generate_summary."""

    def test_empty_signals_summary(self):
        """Pas de signaux → message par défaut."""
        composite = CompositeScore(
            score=0, direction=SignalDirection.NEUTRAL,
            confidence=ConfidenceLevel.LOW, consensus="no_data",
            bullish_count=0, bearish_count=0, neutral_count=0,
        )
        summary = generate_summary([], composite)
        assert "insuffisantes" in summary.lower() or "données" in summary.lower()

    def test_summary_contains_score(self):
        """Le résumé contient le score."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BEARISH, strength=0.7, value=72.0,
                       message="RSI en surachat (72) — zone de prudence"),
        ]
        composite = CompositeScore(
            score=-70, direction=SignalDirection.BEARISH,
            confidence=ConfidenceLevel.MEDIUM, consensus="unanimous",
            bullish_count=0, bearish_count=1, neutral_count=0,
        )
        summary = generate_summary(signals, composite)
        assert "-70" in summary
        assert "baissier" in summary

    def test_summary_contains_confidence(self):
        """Le résumé contient le niveau de confiance."""
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.9, value=15.0,
                       message="RSI fortement survendu (15) — rebond probable"),
        ]
        composite = CompositeScore(
            score=90, direction=SignalDirection.BULLISH,
            confidence=ConfidenceLevel.HIGH, consensus="unanimous",
            bullish_count=1, bearish_count=0, neutral_count=0,
        )
        summary = generate_summary(signals, composite)
        assert "confiance" in summary.lower()


# ============================================================
# TESTS SERVICE INTÉGRATION (avec vraie DB)
# ============================================================

class TestSignalServiceIntegration:
    """Tests d'intégration du SignalService avec DB SQLite."""

    def test_analyze_no_data(self, db_session):
        """Analyse sans données → réponse vide."""
        service = SignalService(db_session)
        result = service.analyze(symbol="BTC/USD", timeframe="4h")

        assert result["meta"]["global_status"] == "NO_DATA"
        assert result["signals"] == []
        assert result["composite"]["score"] == 0
        assert result["composite"]["consensus"] == "no_data"

    def test_analyze_with_candles(self, db_session):
        """Analyse avec des candles insérés → signaux générés."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Insérer 30 candles avec une tendance haussière
        for i in range(30):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=95000 + i * 200,
                high_price=95500 + i * 200,
                low_price=94700 + i * 200,
                close_price=95200 + i * 200,
                volume=1000.0,
                source="test",
            )
            db_session.add(candle)

        db_session.commit()

        service = SignalService(db_session)
        result = service.analyze(symbol="BTC/USD", timeframe="4h", history_days=30)

        # Vérifier la structure de la réponse
        assert "meta" in result
        assert "signals" in result
        assert "composite" in result
        assert "summary" in result

        # Au moins un signal doit être généré (RSI après warmup de 14 + SMA20 après 20 points)
        assert len(result["signals"]) >= 1

        # Le composite doit être structuré
        assert "score" in result["composite"]
        assert "direction" in result["composite"]
        assert "confidence" in result["composite"]
        assert -100 <= result["composite"]["score"] <= 100

        # Le résumé ne doit pas être vide
        assert len(result["summary"]) > 0

    def test_analyze_response_structure(self, db_session):
        """Vérifie la structure complète de la réponse."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(25):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=100000 + i * 100,
                high_price=100500 + i * 100,
                low_price=99700 + i * 100,
                close_price=100200 + i * 100,
                volume=1000.0,
                source="test",
            )
            db_session.add(candle)

        db_session.commit()

        service = SignalService(db_session)
        result = service.analyze(symbol="BTC/USD", timeframe="4h", history_days=30)

        # Chaque signal doit avoir la bonne structure
        for signal in result["signals"]:
            assert "indicator" in signal
            assert "direction" in signal
            assert "strength" in signal
            assert "message" in signal
            assert signal["indicator"] in ("rsi", "macd", "sma", "bollinger", "adx", "volume")
            assert signal["direction"] in ("bullish", "bearish", "neutral")
            assert 0 <= signal["strength"] <= 1

    def test_analyze_invalid_timeframe(self, db_session):
        """Timeframe invalide → ValueError."""
        service = SignalService(db_session)
        with pytest.raises(ValueError):
            service.analyze(timeframe="4d")


# ============================================================
# TESTS ENDPOINT API /market/signals
# ============================================================

class TestSignalEndpoint:
    """Tests pour l'endpoint GET /market/signals."""

    def test_signals_endpoint_no_data(self, client):
        """Endpoint sans données → réponse valide."""
        response = client.get("/market/signals?timeframe=4h")
        assert response.status_code == 200

        data = response.json()
        assert data["meta"]["global_status"] == "NO_DATA"
        assert data["signals"] == []

    def test_signals_endpoint_with_data(self, client, db_session):
        """Endpoint avec données → signaux générés."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(30):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=95000 + i * 200,
                high_price=95500 + i * 200,
                low_price=94700 + i * 200,
                close_price=95200 + i * 200,
                volume=1000.0,
                source="test",
            )
            db_session.add(candle)

        db_session.commit()

        response = client.get("/market/signals?timeframe=4h&history_days=30")
        assert response.status_code == 200

        data = response.json()
        assert "signals" in data
        assert "composite" in data
        assert "summary" in data
        assert isinstance(data["signals"], list)
        assert -100 <= data["composite"]["score"] <= 100

    def test_signals_endpoint_invalid_timeframe(self, client):
        """Timeframe invalide → 422."""
        response = client.get("/market/signals?timeframe=4d")
        assert response.status_code == 422

    def test_signals_endpoint_days_alias(self, client):
        """Le paramètre 'days' fonctionne comme alias."""
        response = client.get("/market/signals?timeframe=4h&days=7")
        assert response.status_code == 200

    def test_signals_endpoint_default_params(self, client):
        """Paramètres par défaut fonctionnent."""
        response = client.get("/market/signals")
        assert response.status_code == 200
        data = response.json()
        assert "meta" in data

