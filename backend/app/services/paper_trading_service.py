"""
Service Paper Trading — Simulation de trading en temps réel.

Ce service :
1. Gère un compte paper trading fictif (capital, PnL, positions)
2. Exécute des "ticks" : à chaque tick, il interroge le DecisionService et RiskService
3. Ouvre/ferme des positions selon les recommandations
4. Vérifie les SL/TP/expiration à chaque tick
5. Calcule des métriques de performance en continu
6. [v1.5] Journalise CHAQUE tick (y compris non-trades)
7. [v1.5] Applique les paramètres du profil actif (Conservative/Balanced/Aggressive)
8. [v1.5] Calcule et applique le levier automatique intelligent
9. [v1.5] Respecte cooldown et max_trades_per_day du profil

Mode simple : 1 seule position ouverte à la fois (pas de hedging).

Le service ne trade PAS avec de l'argent réel. Il simule :
- Pas de slippage (exécution au prix exact)
- Pas de frais de transaction
- Pas de problème de liquidité
"""

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.paper_account import PaperAccount, PaperTrade
from app.models.candle import Candle
from app.services.decision_service import DecisionService
from app.services.risk_service import RiskService
from app.services.trading_profile_service import TradingProfileService
from app.services.leverage_service import LeverageService
from app.services.journal_service import JournalService
from app.schemas.paper_trading import (
    PaperAccountResponse,
    PaperTradeResponse,
    PaperMetrics,
    PaperStatus,
    PaperTickResult,
)

logger = logging.getLogger(__name__)


def _ensure_aware(dt: datetime) -> datetime:
    """Garantit qu'un datetime est timezone-aware (SQLite retourne des naïfs)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class PaperTradingService:
    """
    Service de paper trading.

    Usage :
        service = PaperTradingService(db_session)
        account = service.get_or_create_account()
        result = service.tick()  # Exécute un cycle de trading
    """

    def __init__(self, db: Session):
        self.db = db

    # ================================================================
    # GESTION DU COMPTE
    # ================================================================

    def get_or_create_account(
        self, initial_capital: float = 10000.0
    ) -> PaperAccount:
        """Retourne le compte paper, le crée s'il n'existe pas."""
        account = self.db.query(PaperAccount).first()
        if account is None:
            account = PaperAccount(
                initial_capital=initial_capital,
                current_capital=initial_capital,
                peak_capital=initial_capital,
                is_active=False,
            )
            self.db.add(account)
            self.db.commit()
            self.db.refresh(account)
            logger.info(f"Compte paper créé avec capital={initial_capital}")
        return account

    def reset_account(self, initial_capital: float = 10000.0) -> PaperAccount:
        """
        Reset complet : supprime tous les trades, remet le capital à zéro.
        Capture le prix BTC actuel pour le calcul buy & hold.
        """
        self.db.query(PaperTrade).delete()
        self.db.query(PaperAccount).delete()
        self.db.commit()

        btc_price = self._get_current_price()

        account = PaperAccount(
            initial_capital=initial_capital,
            current_capital=initial_capital,
            peak_capital=initial_capital,
            btc_price_at_start=btc_price,
            is_active=False,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        logger.info(
            f"Compte paper réinitialisé : capital={initial_capital}, "
            f"btc_price_start={btc_price}"
        )
        return account

    def get_open_position(self) -> Optional[PaperTrade]:
        """Retourne la position ouverte (s'il y en a une)."""
        return (
            self.db.query(PaperTrade)
            .filter(PaperTrade.status == "open")
            .first()
        )

    # ================================================================
    # TICK — Boucle centrale du paper trading
    # ================================================================

    def tick(self) -> PaperTickResult:
        """
        Exécute un cycle du paper trading :
        1. Vérifie que le compte est actif
        2. Récupère le prix courant
        3. Si position ouverte → vérifie SL/TP/expiration
        4. Si pas de position → consulte DecisionService + RiskService
        5. Ouvre/ferme des positions selon les résultats
        6. [v1.5] Journalise le tick, applique profil et levier
        """
        now = datetime.now(timezone.utc)
        account = self.get_or_create_account()

        # [v1.5] Récupérer le profil actif
        try:
            profile_svc = TradingProfileService(self.db)
            profile_params = profile_svc.get_active_params()
            profile_name = profile_params.profile_type.value
        except Exception:
            profile_name = "conservative"
            profile_params = None

        # Helper pour journaliser (best-effort, ne bloque pas le tick)
        def _log_tick(**kwargs):
            try:
                journal = JournalService(self.db)
                journal.log_tick(account_id=account.id, profile_type=profile_name, **kwargs)
            except Exception as e:
                logger.debug(f"Journal log error (non-blocking): {e}")

        # Vérification : compte actif
        if not account.is_active:
            _log_tick(action_taken="inactive", reason_no_trade="inactive",
                      reason_detail="Paper trading désactivé")
            return PaperTickResult(
                action_taken="inactive",
                detail="Paper trading désactivé. Activez-le via POST /paper/account.",
                current_price=0.0,
                timestamp=now.isoformat(),
                profile_type=profile_name,
                non_trade_reason="inactive",
            )

        # Récupérer le prix courant
        current_price = self._get_current_price()
        if current_price is None or current_price <= 0:
            _log_tick(action_taken="no_price", reason_no_trade="no_price",
                      reason_detail="Prix BTC indisponible")
            return PaperTickResult(
                action_taken="no_price",
                detail="Prix BTC indisponible. Vérifiez que les données sont chargées.",
                current_price=0.0,
                timestamp=now.isoformat(),
                profile_type=profile_name,
                non_trade_reason="no_price",
            )

        # Capture le prix initial pour buy & hold (si pas encore fait)
        if account.btc_price_at_start is None:
            account.btc_price_at_start = current_price
            self.db.commit()

        # Vérifier la position ouverte
        open_pos = self.get_open_position()

        if open_pos is not None:
            # --- Position ouverte : vérifier SL/TP/expiration ---
            close_reason = self._check_sl_tp(open_pos, current_price)

            if close_reason is None:
                close_reason = self._check_expiration(open_pos, now)

            if close_reason is not None:
                exit_price = current_price
                status = close_reason

                closed = self._close_position(open_pos, exit_price, close_reason, status)
                _log_tick(action_taken=close_reason, btc_price=current_price,
                          had_open_position=True, trade_id=closed.id,
                          leverage_final=getattr(closed, "leverage", 1.0))
                return PaperTickResult(
                    action_taken=close_reason,
                    detail=f"Position fermée : {close_reason} @ {exit_price:.2f}",
                    position_closed=PaperTradeResponse.model_validate(closed),
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    leverage_used=getattr(closed, "leverage", 1.0),
                    profile_type=profile_name,
                )

            # Mettre à jour le highest/lowest price pour trailing stop
            if open_pos.direction == "long":
                if open_pos.highest_price_since_entry is None or current_price > open_pos.highest_price_since_entry:
                    open_pos.highest_price_since_entry = current_price
                    self.db.commit()
            elif open_pos.direction == "short":
                if open_pos.lowest_price_since_entry is None or current_price < open_pos.lowest_price_since_entry:
                    open_pos.lowest_price_since_entry = current_price
                    self.db.commit()

            # Vérifier si le DecisionService recommande de fermer
            decision_result = self._get_decision()
            if decision_result:
                action = decision_result.get("recommendation", {}).get("action", "attendre")
                score = decision_result.get("combined_score", 0)
                unrealized_pnl = self._calc_unrealized_pnl(open_pos, current_price)
                unrealized_pnl_pct = (unrealized_pnl / open_pos.position_size_usd * 100) if open_pos.position_size_usd > 0 else 0

                close_signal = False
                signal_reason = ""

                if open_pos.direction == "long":
                    if action == "vendre":
                        close_signal = True
                        signal_reason = f"Signal contraire : vendre (score={score})"
                    elif action == "attendre" and score <= 0:
                        close_signal = True
                        signal_reason = f"Signal affaibli : attendre (score={score})"

                elif open_pos.direction == "short":
                    if action == "acheter":
                        close_signal = True
                        signal_reason = f"Signal contraire : acheter (score={score})"
                    elif action == "attendre" and score >= 0:
                        close_signal = True
                        signal_reason = f"Signal affaibli : attendre (score={score})"

                # Profit taking : seuil piloté par le profil
                pt_pct = profile_params.profit_take_pct if profile_params else 2.0
                if not close_signal and unrealized_pnl_pct >= pt_pct:
                    close_signal = True
                    signal_reason = f"Prise de profit : PnL latent {unrealized_pnl_pct:.1f}%"

                # Loss cut : seuil piloté par le profil
                lc_pct = profile_params.loss_cut_pct if profile_params else 1.5
                lc_score = profile_params.loss_cut_score_threshold if profile_params else 30
                if not close_signal and unrealized_pnl_pct <= -lc_pct:
                    entry_direction_score = score if open_pos.direction == "long" else -score
                    if entry_direction_score < lc_score:
                        close_signal = True
                        signal_reason = f"Couper les pertes : PnL {unrealized_pnl_pct:.1f}%, signal faible (score={score})"

                if close_signal:
                    closed = self._close_position(
                        open_pos, current_price,
                        signal_reason,
                        "closed_signal"
                    )
                    _log_tick(action_taken="closed_signal", btc_price=current_price,
                              decision_score=score, decision_action=action,
                              had_open_position=True, trade_id=closed.id,
                              leverage_final=getattr(closed, "leverage", 1.0))
                    return PaperTickResult(
                        action_taken="closed_signal",
                        detail=f"Position fermée : {signal_reason}",
                        position_closed=PaperTradeResponse.model_validate(closed),
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        decision_score=score,
                        decision_action=action,
                        leverage_used=getattr(closed, "leverage", 1.0),
                        profile_type=profile_name,
                    )

            # Rien à faire, on conserve la position
            unrealized = self._calc_unrealized_pnl(open_pos, current_price)
            _log_tick(action_taken="hold", btc_price=current_price,
                      had_open_position=True, unrealized_pnl=unrealized,
                      reason_no_trade="position_already_open",
                      reason_detail=f"Position conservée, PnL latent={unrealized:.2f}")
            return PaperTickResult(
                action_taken="hold",
                detail=f"Position ouverte conservée. PnL latent : {unrealized:.2f} USD",
                current_price=current_price,
                timestamp=now.isoformat(),
                profile_type=profile_name,
                non_trade_reason="position_already_open",
            )

        else:
            # --- Pas de position : évaluer une nouvelle entrée ---
            decision_result = self._get_decision()
            if decision_result is None:
                _log_tick(action_taken="no_decision", btc_price=current_price,
                          reason_no_trade="no_decision_available",
                          reason_detail="Moteur de décision indisponible")
                return PaperTickResult(
                    action_taken="no_decision",
                    detail="Moteur de décision indisponible.",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    profile_type=profile_name,
                    non_trade_reason="no_decision_available",
                )

            action = decision_result.get("recommendation", {}).get("action", "attendre")
            score = decision_result.get("combined_score", 0)
            confidence = decision_result.get("recommendation", {}).get("confidence", "low")
            summary = decision_result.get("summary", "")

            if action == "attendre":
                _log_tick(action_taken="hold", btc_price=current_price,
                          decision_score=score, decision_action=action,
                          decision_confidence=confidence,
                          reason_no_trade="decision_wait",
                          reason_detail=f"attendre (score={score}, conf={confidence})")
                return PaperTickResult(
                    action_taken="hold",
                    detail=f"Décision : attendre (score={score}, confiance={confidence})",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    decision_score=score,
                    decision_action=action,
                    profile_type=profile_name,
                    non_trade_reason="decision_wait",
                )

            # [v1.5] Vérification profil — score minimum
            min_score = profile_params.min_score if profile_params else 35
            if abs(score) < min_score:
                reason = "score_too_low"
                detail = f"Score {score} < seuil profil {min_score}"
                _log_tick(action_taken="hold", btc_price=current_price,
                          decision_score=score, decision_action=action,
                          decision_confidence=confidence,
                          reason_no_trade=reason, reason_detail=detail)
                return PaperTickResult(
                    action_taken="hold",
                    detail=f"Signal insuffisant pour profil {profile_name} : {detail}",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    decision_score=score,
                    decision_action=action,
                    profile_type=profile_name,
                    non_trade_reason=reason,
                )

            # [v1.5] Vérification cooldown
            cooldown_min = profile_params.cooldown_minutes if profile_params else 120
            cooldown_reason = self._check_cooldown(account.id, cooldown_min)
            if cooldown_reason:
                _log_tick(action_taken="hold", btc_price=current_price,
                          decision_score=score, decision_action=action,
                          decision_confidence=confidence,
                          reason_no_trade="cooldown_active",
                          reason_detail=cooldown_reason)
                return PaperTickResult(
                    action_taken="hold",
                    detail=f"Cooldown actif : {cooldown_reason}",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    decision_score=score,
                    decision_action=action,
                    profile_type=profile_name,
                    non_trade_reason="cooldown_active",
                )

            # [v1.5] Vérification max trades/jour
            max_tpd = profile_params.max_trades_per_day if profile_params else 3
            max_check = self._check_max_trades_per_day(account.id, max_tpd)
            if max_check:
                _log_tick(action_taken="hold", btc_price=current_price,
                          decision_score=score, decision_action=action,
                          decision_confidence=confidence,
                          reason_no_trade="max_trades_reached",
                          reason_detail=max_check)
                return PaperTickResult(
                    action_taken="hold",
                    detail=f"Max trades/jour atteint : {max_check}",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    decision_score=score,
                    decision_action=action,
                    profile_type=profile_name,
                    non_trade_reason="max_trades_reached",
                )

            # Évaluer via le RiskService
            risk_service = RiskService(self.db)
            evaluation = risk_service.evaluate_trade(action, current_price)

            if not evaluation.allowed:
                reasons_str = "; ".join(evaluation.reasons)
                reason = "risk_blocked"
                if "kill switch" in reasons_str.lower():
                    reason = "kill_switch_active"
                elif "perte journalière" in reasons_str.lower():
                    reason = "daily_loss_protection"

                _log_tick(action_taken="blocked", btc_price=current_price,
                          decision_score=score, decision_action=action,
                          decision_confidence=confidence,
                          reason_no_trade=reason, reason_detail=reasons_str[:500])
                return PaperTickResult(
                    action_taken="blocked",
                    detail=f"Trade bloqué par le risk engine : {reasons_str}",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    decision_score=score,
                    decision_action=action,
                    risk_allowed=False,
                    profile_type=profile_name,
                    non_trade_reason=reason,
                )

            # [v1.5] Calcul levier automatique
            leverage_final = 1.0
            leverage_recommended = 1.0
            leverage_reasons = ""
            if profile_params:
                risk_status = risk_service.get_status()
                leverage_rec = LeverageService.compute_leverage(
                    score=score,
                    confidence=confidence,
                    profile_params=profile_params,
                    risk_level=risk_status.risk_level,
                    daily_loss_remaining=risk_status.daily_loss_remaining_usd,
                    daily_loss_limit=risk_status.daily_loss_limit_usd,
                )
                leverage_final = leverage_rec.final
                leverage_recommended = leverage_rec.recommended
                leverage_reasons = "; ".join(leverage_rec.reasons)[:200]

            # Ouvrir la position
            direction = "long" if action == "acheter" else "short"
            reason = f"{action} | score={score} | {confidence} | {summary[:100]}"
            position = self._open_position(
                account=account,
                price=current_price,
                sl=evaluation.stop_loss_price or current_price * 0.95,
                tp=evaluation.take_profit_price or current_price * 1.10,
                size_usd=evaluation.max_position_size_usd or 1000.0,
                reason=reason,
                score=score,
                direction=direction,
                now=now,
                leverage=leverage_final,
                leverage_reason=leverage_reasons,
                profile_type=profile_name,
            )

            _log_tick(action_taken=f"opened_{direction}", btc_price=current_price,
                      decision_score=score, decision_action=action,
                      decision_confidence=confidence,
                      leverage_recommended=leverage_recommended,
                      leverage_final=leverage_final,
                      leverage_reason=leverage_reasons,
                      trade_id=position.id)

            return PaperTickResult(
                action_taken=f"opened_{direction}",
                detail=f"Position {direction} ouverte @ {current_price:.2f} | SL={evaluation.stop_loss_price:.2f} | TP={evaluation.take_profit_price:.2f} | Levier x{leverage_final}",
                position_opened=PaperTradeResponse.model_validate(position),
                current_price=current_price,
                timestamp=now.isoformat(),
                decision_score=score,
                decision_action=action,
                risk_allowed=True,
                leverage_used=leverage_final,
                profile_type=profile_name,
            )

    # ================================================================
    # OUVERTURE / FERMETURE DE POSITION
    # ================================================================

    def _open_position(
        self,
        account: PaperAccount,
        price: float,
        sl: float,
        tp: float,
        size_usd: float,
        reason: str,
        score: float,
        direction: str = "long",
        now: Optional[datetime] = None,
        leverage: float = 1.0,
        leverage_reason: Optional[str] = None,
        profile_type: Optional[str] = None,
    ) -> PaperTrade:
        """Ouvre une position paper."""
        if now is None:
            now = datetime.now(timezone.utc)

        effective_size = size_usd * leverage

        trade = PaperTrade(
            account_id=account.id,
            status="open",
            direction=direction,
            entry_price=price,
            stop_loss_price=sl,
            take_profit_price=tp,
            highest_price_since_entry=price if direction == "long" else None,
            lowest_price_since_entry=price if direction == "short" else None,
            position_size_usd=min(size_usd, account.current_capital),
            leverage=leverage,
            effective_size_usd=round(effective_size, 2),
            leverage_reason=leverage_reason,
            profile_type=profile_type,
            entry_reason=reason[:500],
            decision_score=score,
            entry_ts=now,
        )
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)
        logger.info(
            f"📈 Position {direction} ouverte @ {price:.2f} | "
            f"SL={sl:.2f} | TP={tp:.2f} | Size={trade.position_size_usd:.2f} USD | "
            f"Levier=x{leverage}"
        )
        return trade

    def _close_position(
        self,
        trade: PaperTrade,
        exit_price: float,
        reason: str,
        status: str,
    ) -> PaperTrade:
        """Ferme une position et met à jour le compte."""
        now = datetime.now(timezone.utc)
        account = self.db.query(PaperAccount).get(trade.account_id)

        # Calcul PnL — le levier amplifie le PnL
        leverage = getattr(trade, "leverage", None) or 1.0
        if trade.direction == "long":
            pnl_pct = (exit_price - trade.entry_price) / trade.entry_price * 100
        else:
            pnl_pct = (trade.entry_price - exit_price) / trade.entry_price * 100

        # PnL = taille nominale × levier × variation %
        pnl = trade.position_size_usd * leverage * pnl_pct / 100

        # Durée
        entry_ts = _ensure_aware(trade.entry_ts)
        duration = (now - entry_ts).total_seconds() / 3600

        # Mise à jour du trade
        trade.exit_price = exit_price
        trade.pnl = round(pnl, 2)
        trade.pnl_pct = round(pnl_pct, 4)
        trade.exit_reason = reason[:500]
        trade.status = status
        trade.exit_ts = now
        trade.duration_hours = round(duration, 2)

        # Mise à jour du compte
        if account:
            account.current_capital += pnl
            account.total_pnl += pnl
            account.total_trades += 1
            if pnl >= 0:
                account.winning_trades += 1
            else:
                account.losing_trades += 1
            if account.total_trades > 0:
                account.win_rate = round(
                    account.winning_trades / account.total_trades * 100, 2
                )
            account.total_pnl_pct = round(
                (account.current_capital - account.initial_capital)
                / account.initial_capital * 100, 2
            )
            if account.current_capital > account.peak_capital:
                account.peak_capital = account.current_capital
            if account.peak_capital > 0:
                dd = (account.peak_capital - account.current_capital) / account.peak_capital * 100
                if dd > account.max_drawdown_pct:
                    account.max_drawdown_pct = round(dd, 2)

            if pnl < 0:
                try:
                    risk_service = RiskService(self.db)
                    risk_service.record_loss(abs(pnl))
                except Exception as e:
                    logger.error(f"Erreur enregistrement perte risk: {e}")

        self.db.commit()
        self.db.refresh(trade)

        emoji = "✅" if pnl >= 0 else "❌"
        logger.info(
            f"{emoji} Position fermée ({status}) @ {exit_price:.2f} | "
            f"PnL={pnl:+.2f} USD ({pnl_pct:+.2f}%) | Levier=x{leverage} | Durée={duration:.1f}h"
        )
        return trade

    def close_position_manual(self, reason: str = "Fermeture manuelle") -> Optional[PaperTrade]:
        """Ferme manuellement la position ouverte."""
        trade = self.get_open_position()
        if trade is None:
            return None
        price = self._get_current_price()
        if price is None or price <= 0:
            return None
        return self._close_position(trade, price, reason, "closed_manual")

    # ================================================================
    # VÉRIFICATIONS SL / TP / EXPIRATION
    # ================================================================

    def _check_sl_tp(self, trade: PaperTrade, current_price: float) -> Optional[str]:
        """Vérifie si le SL ou TP est touché. Retourne le status ou None."""
        if trade.direction == "long":
            if current_price <= trade.stop_loss_price:
                return "closed_sl"
            if current_price >= trade.take_profit_price:
                return "closed_tp"
        else:  # short
            if current_price >= trade.stop_loss_price:
                return "closed_sl"
            if current_price <= trade.take_profit_price:
                return "closed_tp"
        return None

    def _check_expiration(self, trade: PaperTrade, now: datetime) -> Optional[str]:
        """Vérifie si la position a dépassé la durée max."""
        account = self.db.query(PaperAccount).get(trade.account_id)
        if account is None:
            return None
        max_hours = account.max_open_duration_hours
        entry_ts = _ensure_aware(trade.entry_ts)
        elapsed = (now - entry_ts).total_seconds() / 3600
        if elapsed >= max_hours:
            return "closed_expired"
        return None

    # ================================================================
    # [v1.5] CONTRÔLES DE FRÉQUENCE
    # ================================================================

    def _check_cooldown(self, account_id: int, cooldown_minutes: int) -> Optional[str]:
        """Vérifie le cooldown entre deux trades. Retourne raison si bloqué."""
        if cooldown_minutes <= 0:
            return None
        last_trade = (
            self.db.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account_id,
                PaperTrade.status != "open",
            )
            .order_by(PaperTrade.exit_ts.desc())
            .first()
        )
        if last_trade and last_trade.exit_ts:
            exit_ts = _ensure_aware(last_trade.exit_ts)
            elapsed = (datetime.now(timezone.utc) - exit_ts).total_seconds() / 60
            if elapsed < cooldown_minutes:
                remaining = int(cooldown_minutes - elapsed)
                return f"Cooldown : {remaining} min restantes (profil exige {cooldown_minutes} min)"
        return None

    def _check_max_trades_per_day(self, account_id: int, max_trades: int) -> Optional[str]:
        """Vérifie le nombre max de trades par jour. Retourne raison si atteint."""
        if max_trades <= 0:
            return None
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        count = (
            self.db.query(func.count(PaperTrade.id))
            .filter(
                PaperTrade.account_id == account_id,
                PaperTrade.entry_ts >= today_start,
            )
            .scalar() or 0
        )
        if count >= max_trades:
            return f"{count}/{max_trades} trades aujourd'hui (max atteint)"
        return None

    # ================================================================
    # MÉTRIQUES
    # ================================================================

    def get_metrics(self) -> PaperMetrics:
        """Calcule les métriques de performance."""
        account = self.get_or_create_account()
        closed_trades = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.account_id == account.id)
            .filter(PaperTrade.status != "open")
            .order_by(PaperTrade.exit_ts.asc())
            .all()
        )

        if not closed_trades:
            bh = self._calc_buy_hold(account)
            return PaperMetrics(buy_hold_pnl_pct=bh)

        total = len(closed_trades)
        wins = [t for t in closed_trades if t.pnl is not None and t.pnl >= 0]
        losses = [t for t in closed_trades if t.pnl is not None and t.pnl < 0]
        win_rate = len(wins) / total * 100 if total > 0 else 0

        pnls = [t.pnl for t in closed_trades if t.pnl is not None]
        net_pnl = sum(pnls)
        avg_pnl = net_pnl / total if total > 0 else 0

        durations = [t.duration_hours for t in closed_trades if t.duration_hours is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0

        best = max(pnls) if pnls else 0
        worst = min(pnls) if pnls else 0

        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (
            float("inf") if gross_profit > 0 else 0
        )

        pnl_pcts = [t.pnl_pct for t in closed_trades if t.pnl_pct is not None]
        sharpe = self._calc_sharpe(pnl_pcts)

        bh = self._calc_buy_hold(account)

        return PaperMetrics(
            total_trades=total,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=round(win_rate, 2),
            net_pnl=round(net_pnl, 2),
            net_pnl_pct=round(account.total_pnl_pct, 2),
            sharpe_ratio=sharpe,
            max_drawdown_pct=round(account.max_drawdown_pct, 2),
            avg_trade_pnl=round(avg_pnl, 2),
            avg_trade_duration_hours=round(avg_duration, 2),
            best_trade_pnl=round(best, 2),
            worst_trade_pnl=round(worst, 2),
            profit_factor=round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
            buy_hold_pnl_pct=round(bh, 2),
        )

    def get_status(self) -> PaperStatus:
        """Retourne le statut complet du paper trading."""
        account = self.get_or_create_account()
        open_pos = self.get_open_position()
        metrics = self.get_metrics()

        current_price = self._get_current_price()
        unrealized = None
        if open_pos and current_price:
            unrealized = self._calc_unrealized_pnl(open_pos, current_price)

        account_resp = PaperAccountResponse.model_validate(account)
        if open_pos:
            account_resp.open_position = PaperTradeResponse.model_validate(open_pos)

        open_resp = PaperTradeResponse.model_validate(open_pos) if open_pos else None

        return PaperStatus(
            account=account_resp,
            open_position=open_resp,
            metrics=metrics,
            is_running=account.is_active,
            current_btc_price=current_price,
            unrealized_pnl=round(unrealized, 2) if unrealized is not None else None,
        )

    def get_trades(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None,
    ) -> tuple[list[PaperTrade], int]:
        """Liste les trades avec pagination et filtre optionnel."""
        account = self.get_or_create_account()
        query = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.account_id == account.id)
        )
        if status_filter:
            if status_filter == "closed":
                query = query.filter(PaperTrade.status != "open")
            else:
                query = query.filter(PaperTrade.status == status_filter)

        total = query.count()
        trades = (
            query.order_by(PaperTrade.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return trades, total

    # ================================================================
    # HELPERS INTERNES
    # ================================================================

    def _get_current_price(self) -> Optional[float]:
        """Récupère le prix BTC le plus récent (Binance → DB fallback)."""
        try:
            import httpx
            resp = httpx.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": "BTCUSDT"},
                timeout=5.0,
            )
            if resp.status_code == 200:
                price = float(resp.json()["price"])
                if price > 0:
                    return price
        except Exception as e:
            logger.debug(f"Prix live Binance indisponible: {e}")

        candle = (
            self.db.query(Candle)
            .filter(Candle.symbol == "BTC/USD")
            .order_by(Candle.timestamp.desc())
            .first()
        )
        if candle:
            return candle.close_price
        return None

    def _get_decision(self) -> Optional[dict]:
        """Appelle le DecisionService pour obtenir la recommandation."""
        try:
            service = DecisionService(self.db)
            return service.analyze(
                symbol="BTC/USD",
                timeframe="4h",
                history_days=7,
            )
        except Exception as e:
            logger.error(f"Erreur DecisionService: {e}")
            return None

    def _calc_unrealized_pnl(self, trade: PaperTrade, current_price: float) -> float:
        """Calcule le PnL non réalisé d'une position ouverte."""
        leverage = getattr(trade, "leverage", None) or 1.0
        if trade.direction == "long":
            pnl_pct = (current_price - trade.entry_price) / trade.entry_price
        else:
            pnl_pct = (trade.entry_price - current_price) / trade.entry_price
        return trade.position_size_usd * leverage * pnl_pct

    def _calc_buy_hold(self, account: PaperAccount) -> float:
        """Calcule le % de PnL buy & hold depuis le début."""
        if account.btc_price_at_start and account.btc_price_at_start > 0:
            current = self._get_current_price()
            if current:
                return (current - account.btc_price_at_start) / account.btc_price_at_start * 100
        return 0.0

    def _calc_sharpe(self, pnl_pcts: list[float]) -> Optional[float]:
        """Calcule le Sharpe ratio simplifié (annualisé)."""
        if len(pnl_pcts) < 2:
            return None
        mean = sum(pnl_pcts) / len(pnl_pcts)
        variance = sum((p - mean) ** 2 for p in pnl_pcts) / (len(pnl_pcts) - 1)
        std = math.sqrt(variance) if variance > 0 else 0
        if std == 0:
            return None
        sharpe = (mean / std) * math.sqrt(min(len(pnl_pcts), 250))
        return round(sharpe, 2)

