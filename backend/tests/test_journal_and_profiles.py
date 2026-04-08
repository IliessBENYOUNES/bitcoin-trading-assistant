"""
Tests pour le Journal d'Évaluation, Profils de Trading,
Levier Automatique et Qualification du Style — v1.5.

Couvre :
- JournalService : log_tick, get_journal, agrégations, raisons de non-trade
- TradingProfileService : get/set profil, presets
- LeverageService : compute_leverage, vetos risk, facteurs
- TradingStyleResult : distribution durées
- Endpoints API : /paper/journal, /paper/profile, /paper/style
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.models.paper_account import PaperAccount, PaperTrade
from app.models.tick_activity_log import TickActivityLog
from app.services.journal_service import JournalService, REASON_LABELS
from app.services.trading_profile_service import TradingProfileService, PROFILE_PRESETS
from app.services.leverage_service import LeverageService
from app.schemas.journal import (
    TradingProfileType,
    TradingProfileParams,
    LeverageRecommendation,
    JournalPeriodSummary,
    JournalDaySummary,
    JournalActivityStats,
    JournalNonTradeReasons,
    JournalResponse,
    TradingStyleResult,
    DurationBucket,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def paper_account(db_session):
    """Crée un compte paper actif."""
    account = PaperAccount(
        initial_capital=10000.0,
        current_capital=10500.0,
        peak_capital=11000.0,
        is_active=True,
        active_profile="conservative",
        btc_price_at_start=80000.0,
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def closed_trades(db_session, paper_account):
    """Crée des trades fermés pour les tests."""
    now = datetime.now(timezone.utc)
    trades = []
    for i in range(5):
        t = PaperTrade(
            account_id=paper_account.id,
            status="closed_tp" if i % 2 == 0 else "closed_sl",
            direction="long" if i % 2 == 0 else "short",
            entry_price=80000 + i * 100,
            exit_price=80100 + i * 100 if i % 2 == 0 else 79900 + i * 100,
            stop_loss_price=79000,
            take_profit_price=82000,
            position_size_usd=1000.0,
            leverage=1.0 + (i * 0.5),
            effective_size_usd=1000.0 * (1.0 + i * 0.5),
            leverage_reason=f"test leverage x{1.0 + i * 0.5:.1f}",
            profile_type="conservative",
            pnl=50.0 if i % 2 == 0 else -30.0,
            pnl_pct=0.5 if i % 2 == 0 else -0.3,
            entry_reason=f"Test trade {i}",
            exit_reason=f"TP" if i % 2 == 0 else "SL",
            decision_score=40 + i * 5,
            entry_ts=now - timedelta(hours=i * 4 + 2),
            exit_ts=now - timedelta(hours=i * 4),
            duration_hours=2.0 + i * 0.5,
        )
        db_session.add(t)
        trades.append(t)
    db_session.commit()
    return trades


@pytest.fixture
def tick_logs(db_session, paper_account):
    """Crée des logs de ticks pour les tests."""
    now = datetime.now(timezone.utc)
    logs = []
    actions = ["hold", "hold", "opened_long", "hold", "closed_tp",
               "hold", "blocked", "hold", "opened_short", "closed_sl"]
    reasons = [
        "decision_wait", "score_too_low", None, "position_already_open", None,
        "decision_wait", "risk_blocked", "score_too_low", None, None,
    ]
    for i, (action, reason) in enumerate(zip(actions, reasons)):
        log = TickActivityLog(
            account_id=paper_account.id,
            timestamp=now - timedelta(minutes=i * 30),
            btc_price=80000 + i * 10,
            action_taken=action,
            decision_score=30 + i * 3 if action != "blocked" else None,
            decision_action="acheter" if i < 5 else "vendre",
            decision_confidence="medium",
            reason_no_trade=reason,
            reason_detail=f"Détail {i}" if reason else None,
            profile_type="conservative",
            had_open_position=1 if action == "hold" and reason == "position_already_open" else 0,
        )
        db_session.add(log)
        logs.append(log)
    db_session.commit()
    return logs


# ─────────────────────────────────────────────────────────────────────────────
# Tests JournalService — log_tick
# ─────────────────────────────────────────────────────────────────────────────

class TestJournalLogTick:
    """Tests pour log_tick."""

    def test_log_tick_basic(self, db_session, paper_account):
        """Enregistre un tick basique."""
        journal = JournalService(db_session)
        entry = journal.log_tick(
            account_id=paper_account.id,
            action_taken="hold",
            btc_price=80000.0,
        )
        assert entry.id is not None
        assert entry.action_taken == "hold"
        assert entry.btc_price == 80000.0
        assert entry.profile_type == "conservative"

    def test_log_tick_with_all_fields(self, db_session, paper_account):
        """Enregistre un tick avec tous les champs."""
        journal = JournalService(db_session)
        entry = journal.log_tick(
            account_id=paper_account.id,
            action_taken="opened_long",
            btc_price=81000.0,
            decision_score=55.0,
            decision_action="acheter",
            decision_confidence="high",
            profile_type="balanced",
            leverage_recommended=2.0,
            leverage_final=1.5,
            leverage_reason="risk caution",
            had_open_position=False,
            trade_id=42,
        )
        assert entry.decision_score == 55.0
        assert entry.leverage_recommended == 2.0
        assert entry.leverage_final == 1.5
        assert entry.trade_id == 42

    def test_log_tick_non_trade(self, db_session, paper_account):
        """Enregistre un tick non-trade avec raison."""
        journal = JournalService(db_session)
        entry = journal.log_tick(
            account_id=paper_account.id,
            action_taken="hold",
            btc_price=79000.0,
            reason_no_trade="score_too_low",
            reason_detail="Score 20 < seuil 35",
        )
        assert entry.reason_no_trade == "score_too_low"
        assert "Score 20" in entry.reason_detail


# ─────────────────────────────────────────────────────────────────────────────
# Tests JournalService — get_journal
# ─────────────────────────────────────────────────────────────────────────────

class TestJournalGetJournal:
    """Tests pour get_journal."""

    def test_journal_empty_no_account(self, db_session):
        """Journal sans compte retourne structure vide."""
        journal = JournalService(db_session)
        result = journal.get_journal()
        assert result.period.verdict == "N/A"
        assert result.daily == []

    def test_journal_no_trades(self, db_session, paper_account, tick_logs):
        """Journal avec ticks mais sans trades fermés."""
        journal = JournalService(db_session)
        result = journal.get_journal()
        assert result.period.total_ticks > 0
        assert result.period.total_trades == 0
        assert "Aucun trade" in result.period.verdict

    def test_journal_with_trades(self, db_session, paper_account, closed_trades, tick_logs):
        """Journal complet avec trades et ticks."""
        journal = JournalService(db_session)
        result = journal.get_journal()
        assert result.period.total_trades == 5
        assert result.period.win_rate > 0
        assert result.period.pnl_realized != 0
        assert result.activity.total_ticks > 0
        assert result.profile_type == "conservative"

    def test_journal_date_filter(self, db_session, paper_account, closed_trades, tick_logs):
        """Filtrage par date."""
        journal = JournalService(db_session)
        # Filtre futur → 0 trades
        future_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        result = journal.get_journal(date_from=future_date)
        assert result.period.total_trades == 0

    def test_journal_daily_summaries(self, db_session, paper_account, closed_trades, tick_logs):
        """Vérification des agrégations journalières."""
        journal = JournalService(db_session)
        result = journal.get_journal()
        # Au minimum un jour doit exister
        assert len(result.daily) >= 1
        for day in result.daily:
            assert day.date
            assert day.total_ticks >= 0 or day.total_trades >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests JournalService — Period Summary
# ─────────────────────────────────────────────────────────────────────────────

class TestJournalPeriodSummary:
    """Tests pour _compute_period_summary."""

    def test_period_pnl_calculation(self, db_session, paper_account, closed_trades):
        """Vérifie le calcul du PnL."""
        journal = JournalService(db_session)
        now = datetime.now(timezone.utc)
        period = journal._compute_period_summary(
            paper_account.id,
            now - timedelta(days=7),
            now,
        )
        # 3 wins à 50, 2 losses à -30 → net = 90
        assert period.pnl_realized == 90.0
        assert period.total_trades == 5

    def test_period_win_rate(self, db_session, paper_account, closed_trades):
        """Vérifie le win rate."""
        journal = JournalService(db_session)
        now = datetime.now(timezone.utc)
        period = journal._compute_period_summary(
            paper_account.id, now - timedelta(days=7), now,
        )
        # 3 wins / 5 trades = 60%
        assert period.win_rate == 60.0

    def test_period_verdict_prometteur(self, db_session, paper_account, closed_trades):
        """Vérifie le verdict."""
        journal = JournalService(db_session)
        now = datetime.now(timezone.utc)
        period = journal._compute_period_summary(
            paper_account.id, now - timedelta(days=7), now,
        )
        # win_rate=60, pnl>0, pf>1.5 → prometteur
        assert "prometteur" in period.verdict


# ─────────────────────────────────────────────────────────────────────────────
# Tests JournalService — Activity Stats
# ─────────────────────────────────────────────────────────────────────────────

class TestJournalActivity:
    """Tests pour _compute_activity_stats."""

    def test_activity_stats(self, db_session, paper_account, tick_logs):
        """Vérifie les stats d'activité."""
        journal = JournalService(db_session)
        now = datetime.now(timezone.utc)
        activity = journal._compute_activity_stats(
            paper_account.id, now - timedelta(days=7), now,
        )
        assert activity.total_ticks == 10
        assert activity.ticks_opened == 2  # opened_long + opened_short
        assert activity.ticks_closed == 2  # closed_tp + closed_sl
        assert activity.ticks_blocked_risk == 1

    def test_activity_empty(self, db_session, paper_account):
        """Stats d'activité sans ticks."""
        journal = JournalService(db_session)
        now = datetime.now(timezone.utc)
        activity = journal._compute_activity_stats(
            paper_account.id, now - timedelta(days=7), now,
        )
        assert activity.total_ticks == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests JournalService — Non-Trade Reasons
# ─────────────────────────────────────────────────────────────────────────────

class TestJournalNonTradeReasons:
    """Tests pour _compute_non_trade_reasons."""

    def test_non_trade_aggregation(self, db_session, paper_account, tick_logs):
        """Vérifie l'agrégation des raisons."""
        journal = JournalService(db_session)
        now = datetime.now(timezone.utc)
        reasons = journal._compute_non_trade_reasons(
            paper_account.id, now - timedelta(days=7), now,
        )
        assert reasons.total_non_trade_ticks > 0
        reason_keys = [r.reason for r in reasons.reasons]
        assert "decision_wait" in reason_keys
        assert "score_too_low" in reason_keys

    def test_non_trade_labels(self, db_session, paper_account, tick_logs):
        """Vérifie les labels humains."""
        journal = JournalService(db_session)
        now = datetime.now(timezone.utc)
        reasons = journal._compute_non_trade_reasons(
            paper_account.id, now - timedelta(days=7), now,
        )
        for r in reasons.reasons:
            assert r.label != ""  # Tous doivent avoir un label

    def test_non_trade_percentages(self, db_session, paper_account, tick_logs):
        """Vérifie les pourcentages."""
        journal = JournalService(db_session)
        now = datetime.now(timezone.utc)
        reasons = journal._compute_non_trade_reasons(
            paper_account.id, now - timedelta(days=7), now,
        )
        if reasons.reasons:
            total_pct = sum(r.pct for r in reasons.reasons)
            assert abs(total_pct - 100.0) < 1.0  # ~100%


# ─────────────────────────────────────────────────────────────────────────────
# Tests JournalService — Trading Style
# ─────────────────────────────────────────────────────────────────────────────

class TestJournalTradingStyle:
    """Tests pour get_trading_style."""

    def test_trading_style_no_trades(self, db_session, paper_account):
        """Style sans trades → N/A."""
        journal = JournalService(db_session)
        result = journal.get_trading_style()
        assert result.total_closed_trades == 0
        assert result.dominant_style == "N/A"

    def test_trading_style_with_trades(self, db_session, paper_account, closed_trades):
        """Style avec trades → qualification."""
        journal = JournalService(db_session)
        result = journal.get_trading_style()
        assert result.total_closed_trades == 5
        assert result.dominant_style in ("scalping-like", "intraday", "swing_intraday")
        assert len(result.duration_distribution) == 5
        assert result.avg_duration_minutes > 0

    def test_trading_style_buckets_complete(self, db_session, paper_account, closed_trades):
        """Vérifie que tous les buckets sont présents."""
        journal = JournalService(db_session)
        result = journal.get_trading_style()
        labels = [b.label for b in result.duration_distribution]
        assert "< 1 min" in labels
        assert "1h+" in labels


# ─────────────────────────────────────────────────────────────────────────────
# Tests JournalService — Helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestJournalHelpers:
    """Tests pour les méthodes utilitaires."""

    def test_calc_streaks_all_wins(self):
        """Série de gains."""
        best, worst = JournalService._calc_streaks([10, 20, 30])
        assert best == 3
        assert worst == 0

    def test_calc_streaks_all_losses(self):
        """Série de pertes."""
        best, worst = JournalService._calc_streaks([-10, -20, -30])
        assert best == 0
        assert worst == 3

    def test_calc_streaks_mixed(self):
        """Séries mixtes."""
        best, worst = JournalService._calc_streaks([10, 20, -5, -10, 30])
        assert best == 2
        assert worst == 2

    def test_calc_sharpe_insufficient(self):
        """Sharpe avec < 2 données → None."""
        assert JournalService._calc_sharpe([]) is None
        assert JournalService._calc_sharpe([1.0]) is None

    def test_calc_sharpe_valid(self):
        """Sharpe valide."""
        result = JournalService._calc_sharpe([1.0, 2.0, -0.5, 1.5, 0.8])
        assert result is not None
        assert isinstance(result, float)

    def test_compute_verdict_few_trades(self):
        """Verdict avec < 3 trades."""
        v = JournalService._compute_verdict(60, 1.5, 100, 2)
        assert "Pas assez" in v

    def test_compute_verdict_prometteur(self):
        """Verdict prometteur."""
        v = JournalService._compute_verdict(60, 1.8, 100, 10)
        assert v == "prometteur"

    def test_compute_verdict_mittige(self):
        """Verdict mitigé."""
        v = JournalService._compute_verdict(50, 1.2, 50, 10)
        assert v == "mitigé"

    def test_compute_verdict_critique(self):
        """Verdict critique."""
        v = JournalService._compute_verdict(20, 0.5, -100, 10)
        assert v == "critique"

    def test_parse_date_range_defaults(self, db_session, paper_account):
        """Parse range avec defaults."""
        journal = JournalService(db_session)
        dt_from, dt_to = journal._parse_date_range(None, None)
        assert dt_from < dt_to

    def test_parse_date_range_explicit(self, db_session, paper_account):
        """Parse range explicite."""
        journal = JournalService(db_session)
        dt_from, dt_to = journal._parse_date_range("2026-01-01", "2026-12-31")
        assert dt_from.year == 2026
        assert dt_to.month == 12


# ─────────────────────────────────────────────────────────────────────────────
# Tests TradingProfileService
# ─────────────────────────────────────────────────────────────────────────────

class TestTradingProfileService:
    """Tests pour TradingProfileService."""

    def test_get_default_profile(self, db_session, paper_account):
        """Profil par défaut = conservative."""
        svc = TradingProfileService(db_session)
        result = svc.get_active_profile()
        assert result.active_profile == TradingProfileType.conservative
        assert result.params.min_score == 35

    def test_set_profile_balanced(self, db_session, paper_account):
        """Changement vers balanced."""
        svc = TradingProfileService(db_session)
        result = svc.set_profile("balanced")
        assert result.active_profile == TradingProfileType.balanced
        assert result.params.min_score == 20
        assert result.params.leverage_enabled is True

    def test_set_profile_aggressive(self, db_session, paper_account):
        """Changement vers aggressive."""
        svc = TradingProfileService(db_session)
        result = svc.set_profile("aggressive")
        assert result.active_profile == TradingProfileType.aggressive
        assert result.params.max_leverage == 3.0

    def test_set_invalid_profile(self, db_session, paper_account):
        """Profil invalide → erreur."""
        svc = TradingProfileService(db_session)
        with pytest.raises(ValueError, match="Profil inconnu"):
            svc.set_profile("yolo")

    def test_get_active_params(self, db_session, paper_account):
        """get_active_params retourne directement les params."""
        svc = TradingProfileService(db_session)
        params = svc.get_active_params()
        assert isinstance(params, TradingProfileParams)

    def test_get_all_presets(self):
        """Retourne les 3 presets."""
        presets = TradingProfileService.get_all_presets()
        assert len(presets) == 3
        labels = [p.label for p in presets]
        assert "Conservative" in labels
        assert "Balanced" in labels
        assert "Aggressive" in labels

    def test_profile_presets_have_correct_keys(self):
        """Tous les presets ont les bons champs."""
        for name, params in PROFILE_PRESETS.items():
            assert params.min_score >= 0
            assert params.max_trades_per_day > 0
            assert params.cooldown_minutes >= 0
            assert params.max_position_duration_hours > 0

    def test_create_account_if_absent(self, db_session):
        """Crée un compte si absent lors du set_profile."""
        svc = TradingProfileService(db_session)
        result = svc.set_profile("balanced")
        assert result.active_profile == TradingProfileType.balanced
        # Un compte doit avoir été créé
        account = db_session.query(PaperAccount).first()
        assert account is not None
        assert account.active_profile == "balanced"


# ─────────────────────────────────────────────────────────────────────────────
# Tests LeverageService
# ─────────────────────────────────────────────────────────────────────────────

class TestLeverageService:
    """Tests pour le calcul de levier automatique."""

    @pytest.fixture
    def conservative_params(self):
        return PROFILE_PRESETS["conservative"]

    @pytest.fixture
    def balanced_params(self):
        return PROFILE_PRESETS["balanced"]

    @pytest.fixture
    def aggressive_params(self):
        return PROFILE_PRESETS["aggressive"]

    def test_conservative_always_x1(self, conservative_params):
        """Conservative → toujours x1 (levier désactivé)."""
        rec = LeverageService.compute_leverage(
            score=80, confidence="high",
            profile_params=conservative_params,
            risk_level="safe",
        )
        assert rec.final == 1.0
        assert rec.recommended == 1.0

    def test_balanced_score_high(self, balanced_params):
        """Balanced avec score élevé → levier > 1."""
        rec = LeverageService.compute_leverage(
            score=65, confidence="high",
            profile_params=balanced_params,
            risk_level="safe",
        )
        assert rec.final >= 1.0
        assert rec.final <= balanced_params.max_leverage
        assert rec.recommended >= 1.0

    def test_balanced_score_low(self, balanced_params):
        """Balanced avec score faible → levier bas."""
        rec = LeverageService.compute_leverage(
            score=15, confidence="low",
            profile_params=balanced_params,
            risk_level="safe",
        )
        assert rec.final <= 1.5

    def test_aggressive_max_all_conditions(self, aggressive_params):
        """Aggressive avec tout au max → levier élevé."""
        rec = LeverageService.compute_leverage(
            score=80, confidence="high",
            profile_params=aggressive_params,
            risk_level="safe",
        )
        assert rec.final >= 2.0
        assert rec.final <= aggressive_params.max_leverage

    def test_risk_blocked_forces_x1(self, balanced_params):
        """Kill switch actif → toujours x1."""
        rec = LeverageService.compute_leverage(
            score=80, confidence="high",
            profile_params=balanced_params,
            risk_level="blocked",
        )
        assert rec.final == 1.0
        assert rec.risk_adjusted is True

    def test_risk_danger_forces_x1(self, balanced_params):
        """Danger → toujours x1."""
        rec = LeverageService.compute_leverage(
            score=80, confidence="high",
            profile_params=balanced_params,
            risk_level="danger",
        )
        assert rec.final == 1.0

    def test_risk_caution_caps_leverage(self, aggressive_params):
        """Caution → cap à 50% du max."""
        rec = LeverageService.compute_leverage(
            score=80, confidence="high",
            profile_params=aggressive_params,
            risk_level="caution",
        )
        max_cap = 1.0 + (aggressive_params.max_leverage - 1.0) * 0.5
        assert rec.final <= max_cap + 0.5  # arrondi au 0.5

    def test_daily_loss_low_forces_x1(self, balanced_params):
        """Marge daily loss < 30% → x1."""
        rec = LeverageService.compute_leverage(
            score=80, confidence="high",
            profile_params=balanced_params,
            risk_level="safe",
            daily_loss_remaining=20.0,
            daily_loss_limit=100.0,
        )
        assert rec.final == 1.0
        assert rec.risk_adjusted is True

    def test_daily_loss_moderate_caps(self, balanced_params):
        """Marge daily loss 30-50% → cap à x2."""
        rec = LeverageService.compute_leverage(
            score=80, confidence="high",
            profile_params=balanced_params,
            risk_level="safe",
            daily_loss_remaining=40.0,
            daily_loss_limit=100.0,
        )
        assert rec.final <= 2.0

    def test_volatility_high_reduces(self, aggressive_params):
        """Haute volatilité → réduit le levier."""
        rec_calm = LeverageService.compute_leverage(
            score=60, confidence="high",
            profile_params=aggressive_params,
            risk_level="safe",
            current_volatility_pct=0.5,
        )
        rec_wild = LeverageService.compute_leverage(
            score=60, confidence="high",
            profile_params=aggressive_params,
            risk_level="safe",
            current_volatility_pct=6.0,
        )
        assert rec_calm.final >= rec_wild.final

    def test_leverage_has_reasons(self, balanced_params):
        """La recommandation inclut des raisons."""
        rec = LeverageService.compute_leverage(
            score=50, confidence="medium",
            profile_params=balanced_params,
            risk_level="safe",
        )
        assert len(rec.reasons) > 0
        assert "final" in rec.reasons[-1].lower()

    def test_leverage_factors_recorded(self, balanced_params):
        """Les facteurs sont enregistrés."""
        rec = LeverageService.compute_leverage(
            score=50, confidence="medium",
            profile_params=balanced_params,
            risk_level="safe",
        )
        assert "score_factor" in rec.factors
        assert "confidence_factor" in rec.factors
        assert "volatility_factor" in rec.factors


# ─────────────────────────────────────────────────────────────────────────────
# Tests Endpoints API
# ─────────────────────────────────────────────────────────────────────────────

class TestJournalEndpoints:
    """Tests des endpoints /paper/journal, /paper/style, /paper/profile."""

    def test_journal_endpoint(self, client, db_session):
        """GET /paper/journal retourne un JournalResponse."""
        resp = client.get("/paper/journal")
        assert resp.status_code == 200
        data = resp.json()
        assert "period" in data
        assert "activity" in data
        assert "non_trade_reasons" in data

    def test_journal_with_dates(self, client, db_session):
        """GET /paper/journal avec dates."""
        resp = client.get("/paper/journal?date_from=2026-01-01&date_to=2026-12-31")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"]["date_from"] == "2026-01-01"

    def test_style_endpoint(self, client, db_session):
        """GET /paper/style retourne un TradingStyleResult."""
        resp = client.get("/paper/style")
        assert resp.status_code == 200
        data = resp.json()
        assert "dominant_style" in data
        assert "duration_distribution" in data

    def test_profile_get(self, client, db_session):
        """GET /paper/profile retourne le profil actif."""
        # Créer un compte d'abord
        client.post("/paper/account", json={"initial_capital": 10000})
        resp = client.get("/paper/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_profile"] in ("conservative", "balanced", "aggressive")
        assert "params" in data

    def test_profile_set(self, client, db_session):
        """POST /paper/profile change le profil."""
        client.post("/paper/account", json={"initial_capital": 10000})
        resp = client.post("/paper/profile", json={"profile": "balanced"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_profile"] == "balanced"

    def test_profile_presets(self, client, db_session):
        """GET /paper/profile/presets retourne les 3 presets."""
        resp = client.get("/paper/profile/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        types = [p["profile_type"] for p in data]
        assert "conservative" in types
        assert "balanced" in types
        assert "aggressive" in types


# ─────────────────────────────────────────────────────────────────────────────
# Tests REASON_LABELS
# ─────────────────────────────────────────────────────────────────────────────

class TestReasonLabels:
    """Vérifie la complétude des labels de raisons."""

    def test_all_reasons_have_labels(self):
        """Toutes les raisons connues ont un label."""
        for key in [
            "score_too_low", "confidence_too_low", "scenario_weak",
            "sentiment_contradictory", "adx_too_low", "volume_insufficient",
            "position_already_open", "risk_blocked", "daily_loss_protection",
            "kill_switch_active", "cooldown_active", "max_trades_reached",
            "decision_wait", "no_decision_available", "inactive", "no_price", "other",
        ]:
            assert key in REASON_LABELS
            assert REASON_LABELS[key] != ""

    def test_labels_are_french(self):
        """Labels en français."""
        assert "Score" in REASON_LABELS["score_too_low"]
        assert "Confiance" in REASON_LABELS["confidence_too_low"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests Schemas
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemas:
    """Tests des schémas Pydantic."""

    def test_journal_period_summary_defaults(self):
        """JournalPeriodSummary avec defaults."""
        s = JournalPeriodSummary(date_from="2026-01-01", date_to="2026-01-31")
        assert s.total_trades == 0
        assert s.verdict == "N/A"

    def test_leverage_recommendation_defaults(self):
        """LeverageRecommendation avec defaults."""
        r = LeverageRecommendation()
        assert r.final == 1.0
        assert r.risk_adjusted is False
        assert r.reasons == []

    def test_trading_style_result_defaults(self):
        """TradingStyleResult avec defaults."""
        s = TradingStyleResult()
        assert s.total_closed_trades == 0
        assert s.dominant_style == "N/A"

    def test_duration_bucket(self):
        """DurationBucket."""
        b = DurationBucket(label="< 1 min", count=5, pct=25.0)
        assert b.label == "< 1 min"
        assert b.pct == 25.0

    def test_trading_profile_params_conservative(self):
        """Paramètres Conservative."""
        p = PROFILE_PRESETS["conservative"]
        assert p.leverage_enabled is False
        assert p.max_leverage == 1.0
        assert p.min_score == 35

    def test_trading_profile_params_aggressive(self):
        """Paramètres Aggressive."""
        p = PROFILE_PRESETS["aggressive"]
        assert p.leverage_enabled is True
        assert p.max_leverage == 3.0
        assert p.min_score == 10

