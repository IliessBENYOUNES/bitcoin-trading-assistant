"""
Tests pour le Risk Management Engine (v1.3).

Couvre :
1. Configuration CRUD (defaults, create, update partiel)
2. Évaluation de trades (SL/TP calcul, position sizing, blocage)
3. Perte journalière (accumulation, reset, kill switch auto)
4. Kill switch (activation, désactivation, blocage des trades)
5. Mode ATR stop-loss
6. Endpoints HTTP (status codes, structure réponse)
7. Intégration (status, risk_level)
"""

import pytest
from datetime import date, datetime, timezone

from app.models.risk_config import RiskConfig
from app.services.risk_service import RiskService
from app.schemas.risk import (
    RiskConfigCreate,
    RiskConfigUpdate,
    RiskEvaluation,
    RiskStatus,
    StopLossType,
)


# ============================================================
# 1. CONFIG — DEFAULTS & CRUD
# ============================================================

class TestRiskConfigDefaults:
    """Tests pour la configuration par défaut."""

    def test_get_config_creates_default(self, db_session):
        """get_config() crée une config par défaut si aucune n'existe."""
        service = RiskService(db_session)
        config = service.get_config()
        assert config is not None
        assert config.id is not None
        assert config.stop_loss_pct == 5.0
        assert config.take_profit_pct == 10.0
        assert config.max_position_pct == 25.0
        assert config.total_portfolio_value == 10000.0
        assert config.max_daily_loss_pct == 3.0
        assert config.kill_switch_active is False
        assert config.stop_loss_type == "fixed"

    def test_get_config_returns_same_instance(self, db_session):
        """get_config() retourne toujours la même config (singleton)."""
        service = RiskService(db_session)
        config1 = service.get_config()
        config2 = service.get_config()
        assert config1.id == config2.id

    def test_get_config_default_daily_loss_zero(self, db_session):
        """La perte journalière est à 0 par défaut."""
        service = RiskService(db_session)
        config = service.get_config()
        assert config.daily_loss_current == 0.0


class TestRiskConfigCRUD:
    """Tests CRUD pour la configuration de risque."""

    def test_create_config_with_custom_values(self, db_session):
        """Créer une config avec des valeurs personnalisées."""
        service = RiskService(db_session)
        data = RiskConfigCreate(
            stop_loss_type=StopLossType.TRAILING,
            stop_loss_pct=3.0,
            take_profit_pct=15.0,
            max_position_pct=50.0,
            total_portfolio_value=50000.0,
            max_daily_loss_pct=5.0,
        )
        config = service.create_or_update_config(data)
        assert config.stop_loss_type == "trailing"
        assert config.stop_loss_pct == 3.0
        assert config.take_profit_pct == 15.0
        assert config.max_position_pct == 50.0
        assert config.total_portfolio_value == 50000.0
        assert config.max_daily_loss_pct == 5.0

    def test_update_config_upsert(self, db_session):
        """create_or_update_config met à jour si config existe déjà."""
        service = RiskService(db_session)
        # Créer d'abord
        service.get_config()
        # Mettre à jour
        data = RiskConfigCreate(stop_loss_pct=7.0, take_profit_pct=20.0)
        config = service.create_or_update_config(data)
        assert config.stop_loss_pct == 7.0
        assert config.take_profit_pct == 20.0
        # Vérifier qu'il n'y a qu'une seule ligne
        count = db_session.query(RiskConfig).count()
        assert count == 1

    def test_update_config_partial(self, db_session):
        """update_config ne modifie que les champs fournis."""
        service = RiskService(db_session)
        service.get_config()
        data = RiskConfigUpdate(stop_loss_pct=8.0)
        config = service.update_config(data)
        assert config.stop_loss_pct == 8.0
        # Les autres champs restent par défaut
        assert config.take_profit_pct == 10.0
        assert config.max_position_pct == 25.0

    def test_update_config_stop_loss_type(self, db_session):
        """Mise à jour du type de stop-loss."""
        service = RiskService(db_session)
        service.get_config()
        data = RiskConfigUpdate(stop_loss_type=StopLossType.ATR)
        config = service.update_config(data)
        assert config.stop_loss_type == "atr"


# ============================================================
# 2. TRADE EVALUATION — SL/TP, POSITION SIZING
# ============================================================

class TestTradeEvaluation:
    """Tests pour l'évaluation des trades."""

    def test_evaluate_buy_trade_basic(self, db_session):
        """Évaluation d'un achat basique avec SL et TP."""
        service = RiskService(db_session)
        result = service.evaluate_trade("acheter", current_price=85000.0)
        assert result.allowed is True
        assert result.original_action == "acheter"
        assert result.adjusted_action == "acheter"
        # SL = 85000 * (1 - 0.05) = 80750
        assert result.stop_loss_price == 80750.0
        # TP = 85000 * (1 + 0.10) = 93500
        assert result.take_profit_price == 93500.0
        assert result.max_position_size_usd > 0

    def test_evaluate_sell_trade_basic(self, db_session):
        """Évaluation d'une vente (short) avec SL et TP."""
        service = RiskService(db_session)
        result = service.evaluate_trade("vendre", current_price=85000.0)
        assert result.allowed is True
        # SL short = 85000 * (1 + 0.05) = 89250
        assert result.stop_loss_price == 89250.0
        # TP short = 85000 * (1 - 0.10) = 76500
        assert result.take_profit_price == 76500.0

    def test_evaluate_hold_always_allowed(self, db_session):
        """L'action 'attendre' est toujours autorisée."""
        service = RiskService(db_session)
        result = service.evaluate_trade("attendre", current_price=85000.0)
        assert result.allowed is True
        assert result.adjusted_action == "attendre"
        assert result.stop_loss_price is None
        assert result.take_profit_price is None

    def test_evaluate_custom_stop_loss_pct(self, db_session):
        """SL personnalisé (3%) correctement calculé."""
        service = RiskService(db_session)
        data = RiskConfigCreate(stop_loss_pct=3.0, take_profit_pct=6.0)
        service.create_or_update_config(data)
        result = service.evaluate_trade("acheter", current_price=100000.0)
        assert result.stop_loss_price == 97000.0
        assert result.take_profit_price == 106000.0

    def test_evaluate_position_sizing(self, db_session):
        """La taille de position respecte le % max."""
        service = RiskService(db_session)
        # Portfolio 10000, max 25% → 2500 USD
        result = service.evaluate_trade("acheter", current_price=85000.0)
        assert result.max_position_size_usd == 2500.0

    def test_evaluate_position_sizing_custom(self, db_session):
        """Position sizing avec config personnalisée."""
        service = RiskService(db_session)
        data = RiskConfigCreate(
            total_portfolio_value=100000.0,
            max_position_pct=10.0,
        )
        service.create_or_update_config(data)
        result = service.evaluate_trade("acheter", current_price=85000.0)
        assert result.max_position_size_usd == 10000.0

    def test_evaluate_risk_reward_ratio(self, db_session):
        """Le ratio risque/récompense est calculé."""
        service = RiskService(db_session)
        # SL=5%, TP=10% → R/R = 10/5 = 2.0
        result = service.evaluate_trade("acheter", current_price=85000.0)
        assert result.risk_reward_ratio == 2.0

    def test_evaluate_risk_reward_warning_unfavorable(self, db_session):
        """Warning si R/R < 1.0."""
        service = RiskService(db_session)
        data = RiskConfigCreate(stop_loss_pct=10.0, take_profit_pct=5.0)
        service.create_or_update_config(data)
        result = service.evaluate_trade("acheter", current_price=85000.0)
        assert result.risk_reward_ratio == 0.5
        assert any("défavorable" in w for w in result.warnings)


# ============================================================
# 3. ATR-BASED STOP-LOSS
# ============================================================

class TestATRStopLoss:
    """Tests pour le stop-loss basé sur l'ATR."""

    def test_atr_stop_loss_buy(self, db_session):
        """ATR stop-loss pour un achat."""
        service = RiskService(db_session)
        data = RiskConfigCreate(stop_loss_type=StopLossType.ATR)
        service.create_or_update_config(data)
        # ATR = 2000 → SL = 85000 - 2×2000 = 81000
        result = service.evaluate_trade("acheter", current_price=85000.0, atr_value=2000.0)
        assert result.stop_loss_price == 81000.0

    def test_atr_stop_loss_sell(self, db_session):
        """ATR stop-loss pour une vente (short)."""
        service = RiskService(db_session)
        data = RiskConfigCreate(stop_loss_type=StopLossType.ATR)
        service.create_or_update_config(data)
        # ATR = 2000 → SL = 85000 + 2×2000 = 89000
        result = service.evaluate_trade("vendre", current_price=85000.0, atr_value=2000.0)
        assert result.stop_loss_price == 89000.0

    def test_atr_fallback_to_fixed_if_no_atr(self, db_session):
        """Si ATR est None, on utilise le % fixe même en mode ATR."""
        service = RiskService(db_session)
        data = RiskConfigCreate(stop_loss_type=StopLossType.ATR, stop_loss_pct=5.0)
        service.create_or_update_config(data)
        result = service.evaluate_trade("acheter", current_price=100000.0)
        # Fallback au % fixe : 100000 - 5% = 95000
        assert result.stop_loss_price == 95000.0


# ============================================================
# 4. DAILY LOSS TRACKING
# ============================================================

class TestDailyLoss:
    """Tests pour le suivi de perte journalière."""

    def test_record_loss_accumulates(self, db_session):
        """Les pertes s'accumulent dans le compteur journalier."""
        service = RiskService(db_session)
        service.record_loss(50.0)
        config = service.get_config()
        assert config.daily_loss_current == 50.0
        service.record_loss(30.0)
        config = service.get_config()
        assert config.daily_loss_current == 80.0

    def test_record_loss_triggers_kill_switch(self, db_session):
        """Le kill switch est déclenché quand la limite est atteinte."""
        service = RiskService(db_session)
        # Limite : 10000 * 3% = 300 USD
        result = service.record_loss(350.0)
        assert result is True  # Limite atteinte
        config = service.get_config()
        assert config.kill_switch_active is True
        assert "Perte journalière" in (config.kill_switch_reason or "")

    def test_record_loss_below_limit(self, db_session):
        """Pas de kill switch si sous la limite."""
        service = RiskService(db_session)
        result = service.record_loss(100.0)
        assert result is False
        config = service.get_config()
        assert config.kill_switch_active is False

    def test_daily_loss_blocks_trades(self, db_session):
        """Un trade est bloqué si la perte journalière est atteinte."""
        service = RiskService(db_session)
        # Atteindre la limite
        service.record_loss(350.0)
        # Tenter un trade
        result = service.evaluate_trade("acheter", current_price=85000.0)
        assert result.allowed is False
        assert result.adjusted_action == "attendre"

    def test_daily_loss_warning_near_limit(self, db_session):
        """Warning quand on approche de la limite (>80%)."""
        service = RiskService(db_session)
        # Limite = 300, enregistrer 250 → >80%
        service.record_loss(250.0)
        result = service.evaluate_trade("acheter", current_price=85000.0)
        assert result.allowed is True
        assert any("Proche de la limite" in w for w in result.warnings)

    def test_daily_reset_on_new_day(self, db_session):
        """Le compteur est remis à zéro quand la date change."""
        service = RiskService(db_session)
        config = service.get_config()
        # Simuler une perte hier
        config.daily_loss_current = 200.0
        from datetime import timedelta
        config.daily_loss_reset_date = date.today() - timedelta(days=1)
        db_session.commit()
        # L'appel suivant doit reset
        service._ensure_daily_reset(config)
        assert config.daily_loss_current == 0.0
        assert config.daily_loss_reset_date == date.today()


# ============================================================
# 5. KILL SWITCH
# ============================================================

class TestKillSwitch:
    """Tests pour le kill switch."""

    def test_activate_kill_switch(self, db_session):
        """Activation du kill switch."""
        service = RiskService(db_session)
        config = service.activate_kill_switch(reason="Test urgent")
        assert config.kill_switch_active is True
        assert config.kill_switch_reason == "Test urgent"
        assert config.kill_switch_triggered_at is not None

    def test_deactivate_kill_switch(self, db_session):
        """Désactivation du kill switch."""
        service = RiskService(db_session)
        service.activate_kill_switch()
        config = service.deactivate_kill_switch()
        assert config.kill_switch_active is False
        assert config.kill_switch_reason is None

    def test_kill_switch_blocks_buy(self, db_session):
        """Le kill switch bloque les achats."""
        service = RiskService(db_session)
        service.activate_kill_switch(reason="Test")
        result = service.evaluate_trade("acheter", current_price=85000.0)
        assert result.allowed is False
        assert result.adjusted_action == "attendre"
        assert any("Kill switch" in r for r in result.reasons)

    def test_kill_switch_blocks_sell(self, db_session):
        """Le kill switch bloque les ventes."""
        service = RiskService(db_session)
        service.activate_kill_switch(reason="Test")
        result = service.evaluate_trade("vendre", current_price=85000.0)
        assert result.allowed is False
        assert result.adjusted_action == "attendre"

    def test_kill_switch_allows_hold(self, db_session):
        """Le kill switch n'empêche pas l'action 'attendre'."""
        service = RiskService(db_session)
        service.activate_kill_switch(reason="Test")
        result = service.evaluate_trade("attendre", current_price=85000.0)
        assert result.allowed is True  # 'attendre' n'est pas un trade


# ============================================================
# 6. STATUS
# ============================================================

class TestRiskStatus:
    """Tests pour l'état du risk engine."""

    def test_status_default_safe(self, db_session):
        """L'état par défaut est 'safe'."""
        service = RiskService(db_session)
        status = service.get_status()
        assert status.risk_level == "safe"
        assert status.kill_switch_active is False
        assert status.daily_loss_current == 0.0

    def test_status_caution_near_limit(self, db_session):
        """L'état passe en 'caution' quand on approche de la limite."""
        service = RiskService(db_session)
        # 70% de la limite → caution
        service.record_loss(220.0)  # 220/300 = 73%
        status = service.get_status()
        assert status.risk_level == "caution"

    def test_status_danger_at_limit(self, db_session):
        """L'état passe en 'danger' quand la limite est atteinte."""
        service = RiskService(db_session)
        service.record_loss(350.0)
        # Le kill switch est activé, on le désactive pour tester 'danger' sans kill switch
        config = service.get_config()
        config.kill_switch_active = False
        config.kill_switch_reason = None
        db_session.commit()
        status = service.get_status()
        assert status.risk_level == "danger"

    def test_status_blocked_kill_switch(self, db_session):
        """L'état est 'blocked' quand le kill switch est actif."""
        service = RiskService(db_session)
        service.activate_kill_switch(reason="Test")
        status = service.get_status()
        assert status.risk_level == "blocked"

    def test_status_daily_loss_limit_usd(self, db_session):
        """La limite de perte journalière est correctement calculée."""
        service = RiskService(db_session)
        status = service.get_status()
        # 10000 * 3% = 300
        assert status.daily_loss_limit_usd == 300.0

    def test_status_max_position_size(self, db_session):
        """La taille max de position est correcte."""
        service = RiskService(db_session)
        status = service.get_status()
        # 10000 * 25% = 2500
        assert status.max_position_size_usd == 2500.0

    def test_status_remaining_usd(self, db_session):
        """Le montant restant avant limite est correct."""
        service = RiskService(db_session)
        service.record_loss(100.0)
        status = service.get_status()
        assert status.daily_loss_remaining_usd == 200.0

    def test_status_config_included(self, db_session):
        """Le status inclut la config complète."""
        service = RiskService(db_session)
        status = service.get_status()
        assert status.config is not None
        assert status.config.stop_loss_pct == 5.0


# ============================================================
# 7. ENDPOINTS HTTP
# ============================================================

class TestRiskEndpoints:
    """Tests des endpoints API."""

    def test_get_config_endpoint(self, client):
        """GET /risk/config retourne 200 et la config."""
        resp = client.get("/risk/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "stop_loss_pct" in data
        assert "kill_switch_active" in data
        assert data["stop_loss_pct"] == 5.0

    def test_post_config_endpoint(self, client):
        """POST /risk/config crée/met à jour la config."""
        resp = client.post("/risk/config", json={
            "stop_loss_pct": 7.0,
            "take_profit_pct": 14.0,
            "max_position_pct": 30.0,
            "total_portfolio_value": 20000.0,
            "max_daily_loss_pct": 4.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["stop_loss_pct"] == 7.0
        assert data["take_profit_pct"] == 14.0

    def test_put_config_endpoint(self, client):
        """PUT /risk/config met à jour partiellement."""
        # D'abord créer
        client.get("/risk/config")
        # Puis update
        resp = client.put("/risk/config", json={
            "stop_loss_pct": 8.5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["stop_loss_pct"] == 8.5

    def test_get_status_endpoint(self, client):
        """GET /risk/status retourne l'état complet."""
        resp = client.get("/risk/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_level" in data
        assert "kill_switch_active" in data
        assert "daily_loss_current" in data
        assert "config" in data
        assert data["risk_level"] == "safe"

    def test_evaluate_endpoint_buy(self, client):
        """POST /risk/evaluate pour un achat."""
        resp = client.post("/risk/evaluate?action=acheter&price=85000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True
        assert data["stop_loss_price"] is not None
        assert data["take_profit_price"] is not None

    def test_evaluate_endpoint_with_atr(self, client):
        """POST /risk/evaluate avec ATR."""
        # D'abord configurer en mode ATR
        client.post("/risk/config", json={
            "stop_loss_type": "atr",
        })
        resp = client.post("/risk/evaluate?action=acheter&price=85000&atr=2000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stop_loss_price"] == 81000.0

    def test_kill_switch_activate_endpoint(self, client):
        """POST /risk/kill-switch/activate."""
        resp = client.post("/risk/kill-switch/activate?reason=Test%20endpoint")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kill_switch_active"] is True
        assert data["kill_switch_reason"] == "Test endpoint"

    def test_kill_switch_deactivate_endpoint(self, client):
        """POST /risk/kill-switch/deactivate."""
        client.post("/risk/kill-switch/activate")
        resp = client.post("/risk/kill-switch/deactivate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kill_switch_active"] is False

    def test_record_loss_endpoint(self, client):
        """POST /risk/record-loss."""
        resp = client.post("/risk/record-loss?amount=150")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recorded"] == 150.0
        assert data["daily_loss_current"] == 150.0
        assert data["limit_reached"] is False

    def test_record_loss_triggers_kill_switch_endpoint(self, client):
        """POST /risk/record-loss déclenche le kill switch si limite atteinte."""
        resp = client.post("/risk/record-loss?amount=400")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit_reached"] is True
        assert data["kill_switch_active"] is True

    def test_evaluate_blocked_after_kill_switch(self, client):
        """Évaluation bloquée après activation du kill switch."""
        client.post("/risk/kill-switch/activate?reason=Test")
        resp = client.post("/risk/evaluate?action=acheter&price=85000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False
        assert data["adjusted_action"] == "attendre"

    def test_reset_daily_loss_endpoint(self, client):
        """POST /risk/reset-daily-loss remet le compteur à zéro."""
        # D'abord enregistrer une perte
        client.post("/risk/record-loss?amount=200")
        # Vérifier que la perte est enregistrée
        resp = client.get("/risk/config")
        assert resp.json()["daily_loss_current"] == 200.0
        # Reset
        resp = client.post("/risk/reset-daily-loss")
        assert resp.status_code == 200
        data = resp.json()
        assert data["daily_loss_current"] == 0.0
        assert "message" in data
        # Vérifier via config
        resp = client.get("/risk/config")
        assert resp.json()["daily_loss_current"] == 0.0

    def test_reset_daily_loss_deactivates_kill_switch(self, client):
        """POST /risk/reset-daily-loss désactive le kill switch si déclenché par la perte."""
        # Enregistrer une grosse perte pour déclencher le kill switch
        client.post("/risk/record-loss?amount=500")
        resp = client.get("/risk/config")
        assert resp.json()["kill_switch_active"] is True
        # Reset daily loss
        resp = client.post("/risk/reset-daily-loss")
        assert resp.status_code == 200
        assert resp.json()["kill_switch_active"] is False
        # Vérifier que le trading est de nouveau autorisé
        resp = client.post("/risk/evaluate?action=acheter&price=85000")
        assert resp.json()["allowed"] is True


# ============================================================
# 8. EDGE CASES
# ============================================================

class TestRiskEdgeCases:
    """Tests de cas limites."""

    def test_evaluate_zero_portfolio(self, db_session):
        """Portfolio à 0 ne cause pas de division par zéro."""
        service = RiskService(db_session)
        data = RiskConfigCreate(total_portfolio_value=0.0)
        service.create_or_update_config(data)
        result = service.evaluate_trade("acheter", current_price=85000.0)
        assert result.max_position_size_usd == 0.0

    def test_evaluate_very_small_price(self, db_session):
        """Évaluation avec un prix très petit."""
        service = RiskService(db_session)
        result = service.evaluate_trade("acheter", current_price=0.01)
        assert result.allowed is True
        assert result.stop_loss_price is not None

    def test_multiple_losses_then_reset(self, db_session):
        """Plusieurs pertes puis reset le lendemain."""
        service = RiskService(db_session)
        service.record_loss(100.0)
        service.record_loss(50.0)
        config = service.get_config()
        assert config.daily_loss_current == 150.0
        # Simuler un nouveau jour
        from datetime import timedelta
        config.daily_loss_reset_date = date.today() - timedelta(days=1)
        db_session.commit()
        service._ensure_daily_reset(config)
        assert config.daily_loss_current == 0.0

    def test_config_validation_min_values(self):
        """Les valeurs min sont respectées par Pydantic."""
        with pytest.raises(Exception):
            RiskConfigCreate(stop_loss_pct=0.0)  # min 0.1

    def test_config_validation_max_values(self):
        """Les valeurs max sont respectées par Pydantic."""
        with pytest.raises(Exception):
            RiskConfigCreate(stop_loss_pct=60.0)  # max 50.0

    def test_hold_not_blocked_by_daily_loss(self, db_session):
        """L'action 'attendre' n'est pas bloquée même si limite atteinte."""
        service = RiskService(db_session)
        service.record_loss(400.0)  # Dépasse la limite
        result = service.evaluate_trade("attendre", current_price=85000.0)
        assert result.allowed is True

    def test_position_size_adjusted_for_risk(self, db_session):
        """La taille de position est réduite si le risque journalier est limité."""
        service = RiskService(db_session)
        # Enregistrer 250 sur 300 de limite → il reste 50 USD
        service.record_loss(250.0)
        result = service.evaluate_trade("acheter", current_price=100000.0)
        # La position devrait être réduite car la perte max via SL
        # sur la position standard dépasserait les 50 USD restants
        assert result.allowed is True
        # SL = 5% → perte = position × 0.05
        # Si position = 2500 → perte = 125 USD > 50 restants
        # Position ajustée : 50 / 0.05 = 1000 USD
        assert result.max_position_size_usd == 1000.0

