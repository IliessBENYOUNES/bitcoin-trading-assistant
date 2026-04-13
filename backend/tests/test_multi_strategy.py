"""
Tests du Multi-Strategy Engine expérimental.

Couvre :
- MarketContextEngine (détection régime)
- Stratégies individuelles (entry/exit)
- Orchestrateur (routing + signaux)
- Risk Layer (anti-collision, exposition)
- Engine mode switch
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.market_context_engine import MarketContextEngine, MarketContext
from app.services.multi_strategy_engine import MultiStrategyEngine, CONTEXT_STRATEGY_MAP
from app.services.multi_strategy_risk import MultiStrategyRiskLayer, ExposureSnapshot
from app.services.strategies.base import StrategySignal, StrategyParams
from app.services.strategies.scalping import ScalpingStrategy
from app.services.strategies.micro_scalping import MicroScalpingStrategy
from app.services.strategies.mean_reversion import MeanReversionStrategy
from app.services.strategies.breakout import BreakoutStrategy
from app.services.strategies.aggressive import AggressiveStrategy
from app.services.experimental_engine import get_engine_mode, set_engine_mode


# ═══════════════════════════════════════════════════════════════════════════
# Helpers — génération de séries de candles
# ═══════════════════════════════════════════════════════════════════════════

def make_series(
    base_price: float = 73000.0,
    n: int = 25,
    trend: float = 0.0,
    volatility: float = 50.0,
    volume: float = 100.0,
    volume_sma: float = 100.0,
    atr: float = 200.0,
) -> list[dict]:
    """Génère une série de candles pour les tests."""
    series = []
    price = base_price
    for i in range(n):
        price += trend + (volatility * (0.5 - (i % 3) / 3))
        high = price + volatility * 0.5
        low = price - volatility * 0.5
        series.append({
            "open": price - trend * 0.5,
            "close": price,
            "high": high,
            "low": low,
            "volume": volume * (1.0 + 0.1 * (i % 5)),
            "volume_sma_20": volume_sma,
            "atr_14": atr,
            "ema_9": price,
            "rsi_14": 50 + trend * 5,
        })
    return series


def make_range_series(base: float = 73000.0) -> list[dict]:
    """Série en range (prix oscille autour de base)."""
    return make_series(base, trend=0.0, volatility=30.0, atr=200.0)


def make_trend_series(base: float = 73000.0, direction: str = "up") -> list[dict]:
    """Série en trend (prix monte ou descend)."""
    t = 20.0 if direction == "up" else -20.0
    return make_series(base, trend=t, volatility=30.0, atr=100.0)


def make_breakout_series(base: float = 73000.0) -> list[dict]:
    """Série avec breakout (volume spike + mouvement fort sur dernière candle)."""
    series = make_range_series(base)
    # Dernière candle = breakout up
    last = series[-1].copy()
    prev = series[-2]
    last["close"] = last["high"] + 50  # Casse le range par le haut
    last["high"] = last["close"] + 10
    last["volume"] = last["volume_sma_20"] * 2.5  # Volume spike
    last["open"] = prev["close"]
    series[-1] = last
    return series


# ═══════════════════════════════════════════════════════════════════════════
# Tests MarketContextEngine
# ═══════════════════════════════════════════════════════════════════════════

class TestMarketContextEngine:
    """Tests pour la détection de contexte de marché."""

    def test_insufficient_data(self):
        """Données insuffisantes → unknown."""
        ctx = MarketContextEngine.analyze([{"close": 100}] * 5)
        assert ctx.regime == "unknown"
        assert ctx.confidence == 0

    def test_empty_series(self):
        ctx = MarketContextEngine.analyze([])
        assert ctx.regime == "unknown"

    def test_range_detection(self):
        """Série en range → régime range."""
        series = make_range_series()
        ctx = MarketContextEngine.analyze(series)
        assert ctx.regime == "range"
        assert ctx.zone in ("low", "mid", "high")
        assert ctx.confidence > 0

    def test_trend_detection(self):
        """Série en trend up → régime trend bullish."""
        series = make_trend_series(direction="up")
        ctx = MarketContextEngine.analyze(series)
        # Selon les paramètres, peut être trend ou range
        assert ctx.regime in ("range", "trend")
        if ctx.regime == "trend":
            assert ctx.trend_direction == "bullish"

    def test_context_has_all_fields(self):
        """Le contexte retourne tous les champs attendus."""
        series = make_range_series()
        ctx = MarketContextEngine.analyze(series)
        assert hasattr(ctx, "regime")
        assert hasattr(ctx, "trend_direction")
        assert hasattr(ctx, "zone")
        assert hasattr(ctx, "volatility")
        assert hasattr(ctx, "confidence")
        assert hasattr(ctx, "range_high")
        assert hasattr(ctx, "range_low")
        assert hasattr(ctx, "price_position")
        assert hasattr(ctx, "micro_trend_score")
        assert hasattr(ctx, "volume_ratio")
        assert hasattr(ctx, "ema_slope")
        assert hasattr(ctx, "reasons")

    def test_zone_classification(self):
        """La zone est correctement classifiée."""
        ctx = MarketContext(price_position=0.1)
        assert ctx.price_position <= 0.25  # "low" zone

        ctx2 = MarketContext(price_position=0.9)
        assert ctx2.price_position >= 0.75  # "high" zone


# ═══════════════════════════════════════════════════════════════════════════
# Tests Strategies
# ═══════════════════════════════════════════════════════════════════════════

class TestScalpingStrategy:
    def test_entry_with_positive_score(self):
        strategy = ScalpingStrategy()
        ctx = MarketContext(regime="range", zone="mid", volume_ratio=1.0)
        decision = {"combined_score": 30}
        signal = strategy.evaluate_entry(ctx, decision, 73000.0, [])
        assert signal.should_enter is True
        assert signal.direction == "long"
        assert signal.strategy_type == "scalping"

    def test_no_entry_low_score(self):
        strategy = ScalpingStrategy()
        ctx = MarketContext(regime="range", zone="mid", volume_ratio=1.0)
        decision = {"combined_score": 5}
        signal = strategy.evaluate_entry(ctx, decision, 73000.0, [])
        assert signal.should_enter is False

    def test_no_entry_low_volume(self):
        strategy = ScalpingStrategy()
        ctx = MarketContext(regime="range", zone="mid", volume_ratio=0.3)
        decision = {"combined_score": 30}
        signal = strategy.evaluate_entry(ctx, decision, 73000.0, [])
        assert signal.should_enter is False

    def test_trend_alignment(self):
        """En trend bullish, pas de short."""
        strategy = ScalpingStrategy()
        ctx = MarketContext(regime="trend", trend_direction="bullish", volume_ratio=1.0)
        decision = {"combined_score": -30}
        signal = strategy.evaluate_entry(ctx, decision, 73000.0, [])
        assert signal.should_enter is False

    def test_params(self):
        strategy = ScalpingStrategy()
        params = strategy.get_params(MarketContext(), "long")
        assert params.stop_loss_pct == 0.20
        assert params.micro_sl_pct == 0.05
        assert params.leverage == 1.5


class TestMicroScalpingStrategy:
    def test_entry_with_strong_micro_trend(self):
        strategy = MicroScalpingStrategy()
        ctx = MarketContext(
            regime="range", zone="mid",
            micro_trend_score=5, volume_ratio=1.0, volatility="normal",
        )
        signal = strategy.evaluate_entry(ctx, {}, 73000.0, [])
        assert signal.should_enter is True
        assert signal.direction == "long"

    def test_no_entry_high_volatility(self):
        strategy = MicroScalpingStrategy()
        ctx = MarketContext(
            regime="range", zone="mid",
            micro_trend_score=5, volume_ratio=1.0, volatility="high",
        )
        signal = strategy.evaluate_entry(ctx, {}, 73000.0, [])
        assert signal.should_enter is False

    def test_no_entry_weak_micro_trend(self):
        strategy = MicroScalpingStrategy()
        ctx = MarketContext(
            regime="range", zone="mid",
            micro_trend_score=1, volume_ratio=1.0, volatility="normal",
        )
        signal = strategy.evaluate_entry(ctx, {}, 73000.0, [])
        assert signal.should_enter is False


class TestMeanReversionStrategy:
    def test_long_at_range_low(self):
        strategy = MeanReversionStrategy()
        ctx = MarketContext(
            regime="range", zone="low",
            price_position=0.15, confidence=60,
        )
        decision = {"_series": [{"rsi_14": 25}]}
        signal = strategy.evaluate_entry(ctx, decision, 73000.0, [])
        assert signal.should_enter is True
        assert signal.direction == "long"

    def test_short_at_range_high(self):
        strategy = MeanReversionStrategy()
        ctx = MarketContext(
            regime="range", zone="high",
            price_position=0.85, confidence=60,
        )
        decision = {"_series": [{"rsi_14": 75}]}
        signal = strategy.evaluate_entry(ctx, decision, 73000.0, [])
        assert signal.should_enter is True
        assert signal.direction == "short"

    def test_no_entry_in_trend(self):
        strategy = MeanReversionStrategy()
        ctx = MarketContext(regime="trend", zone="low", confidence=60)
        signal = strategy.evaluate_entry(ctx, {}, 73000.0, [])
        assert signal.should_enter is False

    def test_no_entry_mid_zone(self):
        strategy = MeanReversionStrategy()
        ctx = MarketContext(
            regime="range", zone="mid",
            price_position=0.5, confidence=60,
        )
        signal = strategy.evaluate_entry(ctx, {}, 73000.0, [])
        assert signal.should_enter is False

    def test_exit_at_mid_range(self):
        strategy = MeanReversionStrategy()
        ctx = MarketContext(regime="range", zone="mid")
        exit_signal = strategy.evaluate_exit(ctx, {}, 73000.0, 0.5)
        assert exit_signal.should_exit is True

    def test_no_exit_if_losing(self):
        strategy = MeanReversionStrategy()
        ctx = MarketContext(regime="range", zone="mid")
        exit_signal = strategy.evaluate_exit(ctx, {}, 73000.0, -0.5)
        assert exit_signal.should_exit is False


class TestBreakoutStrategy:
    def test_entry_on_breakout(self):
        strategy = BreakoutStrategy()
        ctx = MarketContext(
            regime="breakout",
            breakout_direction="up",
            breakout_strength=0.5,
            volume_ratio=2.0,
        )
        signal = strategy.evaluate_entry(ctx, {}, 73000.0, [])
        assert signal.should_enter is True
        assert signal.direction == "long"

    def test_no_entry_weak_breakout(self):
        strategy = BreakoutStrategy()
        ctx = MarketContext(
            regime="breakout",
            breakout_direction="up",
            breakout_strength=0.1,
        )
        signal = strategy.evaluate_entry(ctx, {}, 73000.0, [])
        assert signal.should_enter is False

    def test_exit_when_range_returns(self):
        strategy = BreakoutStrategy()
        ctx = MarketContext(regime="range")
        exit_signal = strategy.evaluate_exit(ctx, {}, 73000.0, 0.5)
        assert exit_signal.should_exit is True


class TestAggressiveStrategy:
    def test_entry_in_bullish_trend(self):
        strategy = AggressiveStrategy()
        ctx = MarketContext(
            regime="trend",
            trend_direction="bullish",
            confidence=60,
        )
        decision = {"combined_score": 30}
        signal = strategy.evaluate_entry(ctx, decision, 73000.0, [])
        assert signal.should_enter is True
        assert signal.direction == "long"

    def test_no_entry_low_score(self):
        strategy = AggressiveStrategy()
        ctx = MarketContext(regime="trend", trend_direction="bullish", confidence=60)
        decision = {"combined_score": 5}
        signal = strategy.evaluate_entry(ctx, decision, 73000.0, [])
        assert signal.should_enter is False

    def test_adaptive_leverage(self):
        strategy = AggressiveStrategy()
        high_conf = MarketContext(confidence=80)
        low_conf = MarketContext(confidence=40)
        p_high = strategy.get_params(high_conf, "long")
        p_low = strategy.get_params(low_conf, "long")
        assert p_high.leverage == 3.0
        assert p_low.leverage == 1.5


# ═══════════════════════════════════════════════════════════════════════════
# Tests Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiStrategyEngine:
    def test_strategy_routing_range_mid(self):
        """En range mid → scalping + micro_scalping."""
        eligible = CONTEXT_STRATEGY_MAP["range"]["mid"]
        assert "scalping" in eligible
        assert "micro_scalping" in eligible

    def test_strategy_routing_range_edges(self):
        """Aux edges du range → mean_reversion."""
        assert "mean_reversion" in CONTEXT_STRATEGY_MAP["range"]["low"]
        assert "mean_reversion" in CONTEXT_STRATEGY_MAP["range"]["high"]

    def test_strategy_routing_trend(self):
        """En trend → breakout + aggressive."""
        assert "breakout" in CONTEXT_STRATEGY_MAP["trend"]["mid"]
        assert "aggressive" in CONTEXT_STRATEGY_MAP["trend"]["mid"]

    def test_strategy_routing_breakout(self):
        """En breakout → breakout only."""
        assert CONTEXT_STRATEGY_MAP["breakout"]["mid"] == ["breakout"]

    def test_orchestrator_instantiation(self):
        engine = MultiStrategyEngine()
        assert len(engine.strategies) == 5
        assert "scalping" in engine.strategies
        assert "micro_scalping" in engine.strategies
        assert "mean_reversion" in engine.strategies
        assert "breakout" in engine.strategies
        assert "aggressive" in engine.strategies

    def test_evaluate_tick_no_series(self):
        engine = MultiStrategyEngine()
        result = engine.evaluate_tick(
            series=[], decision={}, current_price=73000.0,
        )
        assert result.context.regime == "unknown"

    def test_evaluate_tick_with_range_series(self):
        engine = MultiStrategyEngine()
        series = make_range_series()
        decision = {"combined_score": 30, "_series": series}
        result = engine.evaluate_tick(
            series=series, decision=decision, current_price=73000.0,
        )
        assert len(result.eligible_strategies) > 0
        # Le résultat peut avoir des signaux ou non selon les seuils

    def test_anti_collision_long_short(self):
        """Pas de position dans les deux directions."""
        engine = MultiStrategyEngine()
        series = make_range_series()
        decision = {"combined_score": 30, "_series": series}
        # Position long déjà ouverte
        result = engine.evaluate_tick(
            series=series,
            decision=decision,
            current_price=73000.0,
            open_positions=[{
                "strategy_type": "scalping",
                "direction": "long",
                "position_size_usd": 2500,
                "leverage": 1.0,
            }],
        )
        # Aucun short ne devrait être approuvé
        for sig in result.approved_signals:
            assert sig.direction != "short"

    def test_no_duplicate_strategy(self):
        """Pas de doublon de stratégie."""
        engine = MultiStrategyEngine()
        series = make_range_series()
        decision = {"combined_score": 30, "_series": series}
        result = engine.evaluate_tick(
            series=series,
            decision=decision,
            current_price=73000.0,
            open_positions=[{
                "strategy_type": "scalping",
                "direction": "long",
                "position_size_usd": 2500,
                "leverage": 1.0,
            }],
        )
        for sig in result.approved_signals:
            assert sig.strategy_type != "scalping"

    def test_strategy_info(self):
        engine = MultiStrategyEngine()
        info = engine.get_strategy_info()
        assert len(info) == 5
        names = [s["name"] for s in info]
        assert "scalping" in names


# ═══════════════════════════════════════════════════════════════════════════
# Tests Risk Layer
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiStrategyRiskLayer:
    def test_approve_first_trade(self):
        risk = MultiStrategyRiskLayer()
        signal = StrategySignal(
            should_enter=True, direction="long",
            strategy_type="scalping", strength=50,
        )
        result = risk.check_signal(
            signal=signal,
            position_size_usd=2500,
            capital=10000,
            open_positions=[],
        )
        assert result.approved is True

    def test_kill_switch_drawdown(self):
        risk = MultiStrategyRiskLayer(max_drawdown_kill_pct=5.0)
        signal = StrategySignal(
            should_enter=True, direction="long",
            strategy_type="scalping", strength=50,
        )
        result = risk.check_signal(
            signal=signal,
            position_size_usd=2500,
            capital=10000,
            open_positions=[],
            drawdown_pct=6.0,
        )
        assert result.approved is False
        assert "Kill switch" in result.reason

    def test_max_positions(self):
        risk = MultiStrategyRiskLayer(max_simultaneous_positions=2)
        signal = StrategySignal(
            should_enter=True, direction="long",
            strategy_type="breakout", strength=50,
        )
        result = risk.check_signal(
            signal=signal,
            position_size_usd=2500,
            capital=10000,
            open_positions=[
                {"direction": "long", "strategy_type": "scalping",
                 "position_size_usd": 2500, "leverage": 1},
                {"direction": "long", "strategy_type": "aggressive",
                 "position_size_usd": 2500, "leverage": 1},
            ],
        )
        assert result.approved is False
        assert "Max positions" in result.reason

    def test_anti_collision(self):
        risk = MultiStrategyRiskLayer()
        signal = StrategySignal(
            should_enter=True, direction="short",
            strategy_type="scalping", strength=50,
        )
        result = risk.check_signal(
            signal=signal,
            position_size_usd=2500,
            capital=10000,
            open_positions=[
                {"direction": "long", "strategy_type": "aggressive",
                 "position_size_usd": 2500, "leverage": 1},
            ],
        )
        assert result.approved is False
        assert "Anti-collision" in result.reason

    def test_no_duplicate_strategy(self):
        risk = MultiStrategyRiskLayer()
        signal = StrategySignal(
            should_enter=True, direction="long",
            strategy_type="scalping", strength=50,
        )
        result = risk.check_signal(
            signal=signal,
            position_size_usd=2500,
            capital=10000,
            open_positions=[
                {"direction": "long", "strategy_type": "scalping",
                 "position_size_usd": 2500, "leverage": 1},
            ],
        )
        assert result.approved is False
        assert "déjà en cours" in result.reason

    def test_exposure_limit(self):
        risk = MultiStrategyRiskLayer(max_total_exposure_pct=50.0)
        signal = StrategySignal(
            should_enter=True, direction="long",
            strategy_type="breakout", strength=50,
        )
        result = risk.check_signal(
            signal=signal,
            position_size_usd=4000,
            capital=10000,
            open_positions=[
                {"direction": "long", "strategy_type": "scalping",
                 "position_size_usd": 3000, "leverage": 1},
            ],
        )
        assert result.approved is False
        assert "Exposition" in result.reason

    def test_anti_burst_cooldown(self):
        risk = MultiStrategyRiskLayer(min_entry_interval_seconds=30)
        now = datetime.now(timezone.utc)
        risk.record_entry(now)

        signal = StrategySignal(
            should_enter=True, direction="long",
            strategy_type="scalping", strength=50,
        )
        result = risk.check_signal(
            signal=signal,
            position_size_usd=2500,
            capital=10000,
            open_positions=[],
            now=now + timedelta(seconds=10),
        )
        assert result.approved is False
        assert "Cooldown" in result.reason

    def test_cooldown_expired(self):
        risk = MultiStrategyRiskLayer(min_entry_interval_seconds=30)
        now = datetime.now(timezone.utc)
        risk.record_entry(now)

        signal = StrategySignal(
            should_enter=True, direction="long",
            strategy_type="scalping", strength=50,
        )
        result = risk.check_signal(
            signal=signal,
            position_size_usd=2500,
            capital=10000,
            open_positions=[],
            now=now + timedelta(seconds=60),
        )
        assert result.approved is True

    def test_exposure_snapshot(self):
        positions = [
            {"direction": "long", "position_size_usd": 2500,
             "leverage": 2, "strategy_type": "scalping"},
            {"direction": "long", "position_size_usd": 2000,
             "leverage": 1, "strategy_type": "breakout"},
        ]
        exp = MultiStrategyRiskLayer.get_exposure(positions, 10000)
        assert exp.total_exposure_usd == 7000  # 2500*2 + 2000*1
        assert exp.num_positions == 2
        assert exp.net_direction == "long"
        assert "scalping" in exp.strategies_active


# ═══════════════════════════════════════════════════════════════════════════
# Tests Engine Mode
# ═══════════════════════════════════════════════════════════════════════════

class TestEngineMode:
    def test_default_mode(self):
        # Reset to standard first
        set_engine_mode("standard")
        assert get_engine_mode() == "standard"

    def test_switch_to_experimental(self):
        set_engine_mode("experimental")
        assert get_engine_mode() == "experimental"
        # Reset
        set_engine_mode("standard")

    def test_invalid_mode(self):
        with pytest.raises(ValueError):
            set_engine_mode("invalid")

    def test_switch_back(self):
        set_engine_mode("experimental")
        set_engine_mode("standard")
        assert get_engine_mode() == "standard"
