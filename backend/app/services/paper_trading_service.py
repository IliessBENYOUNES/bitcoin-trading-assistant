"""
Service Paper Trading — Simulation de trading en temps réel.

Ce service :
1. Gère un compte paper trading fictif (capital, PnL, positions)
2. Exécute des "ticks" : à chaque tick, il interroge le DecisionService et RiskService
3. Ouvre/ferme des positions selon les recommandations
4. Vérifie les SL/TP/expiration à chaque tick
5. Calcule des métriques de performance en continu

Mode simple : 1 seule position ouverte à la fois (pas de hedging).

Le service ne trade PAS avec de l'argent réel. Il simule :
- Pas de slippage (exécution au prix exact)
- Pas de frais de transaction
- Pas de problème de liquidité
"""

import logging
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paper_account import PaperAccount, PaperTrade
from app.models.candle import Candle
from app.services.decision_service import DecisionService
from app.services.risk_service import RiskService
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
                is_active=False,  # Inactif par défaut, l'utilisateur doit l'activer
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
        # Supprimer tous les trades existants
        self.db.query(PaperTrade).delete()

        # Supprimer le compte existant
        self.db.query(PaperAccount).delete()
        self.db.commit()

        # Récupérer le prix BTC actuel pour le buy & hold
        btc_price = self._get_current_price()

        # Créer un nouveau compte
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
        """
        now = datetime.now(timezone.utc)
        account = self.get_or_create_account()

        # Vérification : compte actif
        if not account.is_active:
            return PaperTickResult(
                action_taken="inactive",
                detail="Paper trading désactivé. Activez-le via POST /paper/account.",
                current_price=0.0,
                timestamp=now.isoformat(),
            )

        # Récupérer le prix courant
        current_price = self._get_current_price()
        if current_price is None or current_price <= 0:
            return PaperTickResult(
                action_taken="no_price",
                detail="Prix BTC indisponible. Vérifiez que les données sont chargées.",
                current_price=0.0,
                timestamp=now.isoformat(),
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
                # Déterminer le prix de sortie (SL ou TP exact, sinon prix courant)
                exit_price = current_price
                status = close_reason

                closed = self._close_position(open_pos, exit_price, close_reason, status)
                return PaperTickResult(
                    action_taken=close_reason,
                    detail=f"Position fermée : {close_reason} @ {exit_price:.2f}",
                    position_closed=PaperTradeResponse.model_validate(closed),
                    current_price=current_price,
                    timestamp=now.isoformat(),
                )

            # Mettre à jour le highest_price pour trailing stop (long)
            # ou lowest_price pour trailing stop (short)
            if open_pos.direction == "long":
                if open_pos.highest_price_since_entry is None or current_price > open_pos.highest_price_since_entry:
                    open_pos.highest_price_since_entry = current_price
                    self.db.commit()
            elif open_pos.direction == "short":
                if open_pos.lowest_price_since_entry is None or current_price < open_pos.lowest_price_since_entry:
                    open_pos.lowest_price_since_entry = current_price
                    self.db.commit()

            # Vérifier si le DecisionService recommande de fermer (signal contraire ou affaibli)
            decision_result = self._get_decision()
            if decision_result:
                action = decision_result.get("recommendation", {}).get("action", "attendre")
                score = decision_result.get("combined_score", 0)
                unrealized_pnl = self._calc_unrealized_pnl(open_pos, current_price)
                unrealized_pnl_pct = (unrealized_pnl / open_pos.position_size_usd * 100) if open_pos.position_size_usd > 0 else 0

                close_signal = False
                signal_reason = ""

                if open_pos.direction == "long":
                    # Fermer un LONG si :
                    # 1. Signal contraire "vendre" (peu importe la force)
                    if action == "vendre":
                        close_signal = True
                        signal_reason = f"Signal contraire : vendre (score={score})"
                    # 2. Signal "attendre" avec score devenu négatif (le signal bullish s'est dissipé)
                    elif action == "attendre" and score <= 0:
                        close_signal = True
                        signal_reason = f"Signal affaibli : attendre (score={score})"

                elif open_pos.direction == "short":
                    # Fermer un SHORT si :
                    # 1. Signal contraire "acheter"
                    if action == "acheter":
                        close_signal = True
                        signal_reason = f"Signal contraire : acheter (score={score})"
                    # 2. Signal "attendre" avec score devenu positif
                    elif action == "attendre" and score >= 0:
                        close_signal = True
                        signal_reason = f"Signal affaibli : attendre (score={score})"

                # Profit taking : fermer si PnL latent > 2% (prendre les gains sans attendre le TP)
                if not close_signal and unrealized_pnl_pct >= 2.0:
                    close_signal = True
                    signal_reason = f"Prise de profit : PnL latent {unrealized_pnl_pct:.1f}%"

                # Loss cut : fermer si PnL latent < -1.5% et le signal n'est plus fort
                if not close_signal and unrealized_pnl_pct <= -1.5:
                    entry_direction_score = score if open_pos.direction == "long" else -score
                    if entry_direction_score < 30:  # Le signal n'est plus assez fort pour justifier la perte
                        close_signal = True
                        signal_reason = f"Couper les pertes : PnL {unrealized_pnl_pct:.1f}%, signal faible (score={score})"

                if close_signal:
                    closed = self._close_position(
                        open_pos, current_price,
                        signal_reason,
                        "closed_signal"
                    )
                    return PaperTickResult(
                        action_taken="closed_signal",
                        detail=f"Position fermée : {signal_reason}",
                        position_closed=PaperTradeResponse.model_validate(closed),
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        decision_score=score,
                        decision_action=action,
                    )

            # Rien à faire, on conserve la position
            return PaperTickResult(
                action_taken="hold",
                detail=f"Position ouverte conservée. PnL latent : {self._calc_unrealized_pnl(open_pos, current_price):.2f} USD",
                current_price=current_price,
                timestamp=now.isoformat(),
            )

        else:
            # --- Pas de position : évaluer une nouvelle entrée ---
            decision_result = self._get_decision()
            if decision_result is None:
                return PaperTickResult(
                    action_taken="no_decision",
                    detail="Moteur de décision indisponible.",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                )

            action = decision_result.get("recommendation", {}).get("action", "attendre")
            score = decision_result.get("combined_score", 0)
            confidence = decision_result.get("recommendation", {}).get("confidence", "low")
            summary = decision_result.get("summary", "")

            if action == "attendre":
                return PaperTickResult(
                    action_taken="hold",
                    detail=f"Décision : attendre (score={score}, confiance={confidence})",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    decision_score=score,
                    decision_action=action,
                )

            # Évaluer via le RiskService
            risk_service = RiskService(self.db)
            evaluation = risk_service.evaluate_trade(action, current_price)

            if not evaluation.allowed:
                return PaperTickResult(
                    action_taken="blocked",
                    detail=f"Trade bloqué par le risk engine : {'; '.join(evaluation.reasons)}",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    decision_score=score,
                    decision_action=action,
                    risk_allowed=False,
                )

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
            )

            return PaperTickResult(
                action_taken=f"opened_{direction}",
                detail=f"Position {direction} ouverte @ {current_price:.2f} | SL={evaluation.stop_loss_price:.2f} | TP={evaluation.take_profit_price:.2f}",
                position_opened=PaperTradeResponse.model_validate(position),
                current_price=current_price,
                timestamp=now.isoformat(),
                decision_score=score,
                decision_action=action,
                risk_allowed=True,
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
    ) -> PaperTrade:
        """Ouvre une position paper."""
        if now is None:
            now = datetime.now(timezone.utc)

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
            entry_reason=reason[:500],
            decision_score=score,
            entry_ts=now,
        )
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)
        logger.info(
            f"📈 Position {direction} ouverte @ {price:.2f} | "
            f"SL={sl:.2f} | TP={tp:.2f} | Size={trade.position_size_usd:.2f} USD"
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

        # Calcul PnL
        if trade.direction == "long":
            pnl_pct = (exit_price - trade.entry_price) / trade.entry_price * 100
        else:
            pnl_pct = (trade.entry_price - exit_price) / trade.entry_price * 100

        pnl = trade.position_size_usd * pnl_pct / 100

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
            # Mise à jour peak capital et drawdown
            if account.current_capital > account.peak_capital:
                account.peak_capital = account.current_capital
            if account.peak_capital > 0:
                dd = (account.peak_capital - account.current_capital) / account.peak_capital * 100
                if dd > account.max_drawdown_pct:
                    account.max_drawdown_pct = round(dd, 2)

            # Enregistrer la perte dans le RiskService si perte
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
            f"PnL={pnl:+.2f} USD ({pnl_pct:+.2f}%) | Durée={duration:.1f}h"
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
            # Buy & hold
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

        # Sharpe ratio (simplifié sur PnL % des trades)
        pnl_pcts = [t.pnl_pct for t in closed_trades if t.pnl_pct is not None]
        sharpe = self._calc_sharpe(pnl_pcts)

        # Buy & hold
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

        # Construire le PaperAccountResponse avec la position ouverte
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
        """
        Récupère le prix BTC le plus récent possible.

        Priorité :
        1. API Binance en temps réel (ticker/price — latence ~100ms)
        2. Fallback : dernier close_price en DB (peut être vieux de plusieurs heures)
        """
        # Tentative 1 : prix live via Binance
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

        # Tentative 2 : fallback DB
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
        if trade.direction == "long":
            pnl_pct = (current_price - trade.entry_price) / trade.entry_price
        else:
            pnl_pct = (trade.entry_price - current_price) / trade.entry_price
        return trade.position_size_usd * pnl_pct

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
        # Annualisation approximative (supposons ~250 trades/an)
        sharpe = (mean / std) * math.sqrt(min(len(pnl_pcts), 250))
        return round(sharpe, 2)

