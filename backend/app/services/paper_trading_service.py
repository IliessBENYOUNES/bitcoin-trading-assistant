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
from app.services.trading_profile_service import TradingProfileService, PROFILE_PRESETS
from app.services.leverage_service import LeverageService
from app.services.journal_service import JournalService
from app.services.tick_momentum_service import TickMomentumService
from app.services.entry_sas_service import EntrySasService
from app.schemas.paper_trading import (
    PaperAccountResponse,
    PaperTradeResponse,
    PaperMetrics,
    PaperStatus,
    PaperTickResult,
    SlotTickResult,
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
        self, initial_capital: float = 10000.0, active_profile: str = None
    ) -> PaperAccount:
        """Retourne le compte paper, le crée s'il n'existe pas.

        [v2.0.5-fix] active_profile : si fourni et qu'un nouveau compte est créé,
        le profil est initialisé avec cette valeur au lieu du default "conservative".
        Si le compte existe déjà, son profil n'est PAS écrasé.
        """
        account = self.db.query(PaperAccount).first()
        if account is None:
            # [v2.0.5-fix] Utiliser le profil demandé, pas le default SQLAlchemy
            profile = active_profile or "conservative"
            account = PaperAccount(
                initial_capital=initial_capital,
                current_capital=initial_capital,
                peak_capital=initial_capital,
                is_active=False,
                active_profile=profile,
            )
            self.db.add(account)
            self.db.commit()
            self.db.refresh(account)
            logger.info(f"Compte paper créé avec capital={initial_capital}, active_profile={profile}")
        return account

    def reset_account(self, initial_capital: float = 10000.0, preserve_profile: str = None) -> tuple["PaperAccount", dict]:
        """
        FULL RESET — Hard reset total cohérent.

        Purge toutes les données liées au paper trading :
        - tick_activity_log (journal de ticks)
        - paper_trade (trades papier)
        - paper_account (compte)
        - learning_signal (échantillons d'apprentissage)
        - strategy_feedback (suggestions IA)
        - paper_run (campagnes de validation)
        - risk_config (daily loss, kill switch, portfolio value)

        Retourne le nouveau compte + le dictionnaire des compteurs de purge.

        Contrat métier : après full reset, aucun artefact de l'ancien
        état ne doit subsister dans aucun panneau.

        [v2.0.5-fix] preserve_profile : si fourni, le nouveau compte est créé
        avec ce profil. Sinon, le profil de l'ancien compte est préservé.
        Cela empêche la bascule silencieuse vers "conservative" (default SQLAlchemy)
        lors d'un full reset.
        """
        from app.models.tick_activity_log import TickActivityLog
        from app.models.risk_config import RiskConfig
        from app.models.learning import LearningSignal, StrategyFeedback
        from app.models.paper_run import PaperRun

        purged = {}

        # [v2.0.5-fix] Capturer le profil AVANT la purge.
        # Sans cela, le default SQLAlchemy "conservative" écrase le profil actif.
        old_account = self.db.query(PaperAccount).first()
        saved_profile = preserve_profile
        if not saved_profile and old_account:
            saved_profile = getattr(old_account, "active_profile", None)
        # Fallback ultime : "conservative" (ne devrait jamais arriver en pratique)
        if not saved_profile:
            saved_profile = "conservative"

        # 1. Purge tick_activity_log — évite pollution diagnostic
        purged["tick_activity_log"] = self.db.query(TickActivityLog).delete()

        # 2. Purge learning_signal — les trade_ids deviennent orphelins
        purged["learning_signal"] = self.db.query(LearningSignal).delete()

        # 3. Purge strategy_feedback — suggestions obsolètes
        purged["strategy_feedback"] = self.db.query(StrategyFeedback).delete()

        # 4. Purge paper_run — campagnes mortes
        purged["paper_run"] = self.db.query(PaperRun).delete()

        # 5. Purge trades et comptes
        purged["paper_trade"] = self.db.query(PaperTrade).delete()
        purged["paper_account"] = self.db.query(PaperAccount).delete()

        self.db.commit()

        # 6. Reset RiskConfig : daily loss, kill switch, portfolio value
        # Sans cela, un kill switch déclenché par l'ancien compte
        # continue de bloquer les trades du nouveau compte.
        risk_config = self.db.query(RiskConfig).first()
        if risk_config:
            risk_config.daily_loss_current = 0.0
            risk_config.kill_switch_active = False
            risk_config.kill_switch_reason = None
            risk_config.kill_switch_triggered_at = None
            risk_config.total_portfolio_value = initial_capital
            self.db.commit()
        purged["risk_config_reset"] = 1 if risk_config else 0

        btc_price = self._get_current_price()

        # [v2.0.5-fix] Le profil est explicitement restauré dans le nouveau compte.
        # Avant ce fix, le default SQLAlchemy "conservative" écrasait silencieusement
        # le profil demandé lors de chaque full reset.
        account = PaperAccount(
            initial_capital=initial_capital,
            current_capital=initial_capital,
            peak_capital=initial_capital,
            btc_price_at_start=btc_price,
            is_active=False,
            active_profile=saved_profile,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        logger.info(
            f"🔥 FULL RESET : capital={initial_capital}, "
            f"btc_price_start={btc_price}, active_profile={saved_profile}, purged={purged}"
        )

        # [v2.0.22] Nettoyer les SAS pending en mémoire (pas de trade fantôme)
        EntrySasService.clear()

        return account, purged

    def get_open_position(self) -> Optional[PaperTrade]:
        """Retourne la position ouverte (s'il y en a une). Rétrocompatible."""
        return (
            self.db.query(PaperTrade)
            .filter(PaperTrade.status == "open")
            .first()
        )

    def get_open_positions(self) -> list[PaperTrade]:
        """[v1.7] Retourne TOUTES les positions ouvertes."""
        return (
            self.db.query(PaperTrade)
            .filter(PaperTrade.status == "open")
            .all()
        )

    def get_open_position_for_slot(self, slot: str) -> Optional[PaperTrade]:
        """[v1.7] Retourne la position ouverte pour un slot donné."""
        return (
            self.db.query(PaperTrade)
            .filter(PaperTrade.status == "open", PaperTrade.slot == slot)
            .first()
        )

    def get_enabled_slots(self, account: PaperAccount) -> list[str]:
        """
        [v1.7] Retourne la liste des slots actifs.

        En mode mono (max_open_positions=1) : retourne [active_profile].
        En mode multi (max_open_positions>1) : retourne les profils parallèles.
        Le profil "auto" se résout en ["balanced", "scalping"] pour le multi-slot.
        """
        max_pos = getattr(account, "max_open_positions", 1) or 1
        profile = account.active_profile or "conservative"

        if max_pos <= 1:
            return [profile]

        # Mode multi : retourner des slots par stratégie
        # "auto" → balanced (tendance) + scalping (court terme)
        if profile == "auto":
            return ["balanced", "scalping"]

        # Si un profil spécifique est sélectionné en multi, on ajoute le scalping
        # pour permettre du trading haute fréquence en parallèle
        if profile == "scalping":
            return ["scalping", "aggressive"]
        elif profile in ("balanced", "aggressive"):
            return [profile, "scalping"]
        elif profile == "conservative":
            return ["conservative", "scalping"]
        else:
            return [profile]

    def _capital_for_slot(self, account: PaperAccount, num_slots: int) -> float:
        """[v1.7] Capital max alloué par slot (division égale)."""
        if num_slots <= 1:
            return account.current_capital
        return account.current_capital / num_slots

    # ================================================================
    # TICK — Boucle centrale du paper trading
    # ================================================================

    def tick(self) -> PaperTickResult:
        """
        [v1.7] Exécute un cycle du paper trading — multi-slot.

        En mode mono (max_open_positions=1) : comportement identique à avant.
        En mode multi (max_open_positions>1) : itère sur chaque slot (profil),
        monitore les positions ouvertes et en ouvre de nouvelles en parallèle.

        Chaque slot est un profil avec ses propres paramètres (SL/TP, durée, etc.).
        Exemple : slot "balanced" (trend long) + slot "scalping" (court terme).
        """
        now = datetime.now(timezone.utc)
        account = self.get_or_create_account()

        # Vérification : compte actif
        if not account.is_active:
            return PaperTickResult(
                action_taken="inactive",
                detail="Paper trading désactivé. Cliquez sur « Lancer le Robot » pour démarrer.",
                current_price=0.0,
                timestamp=now.isoformat(),
                non_trade_reason="inactive",
            )

        # Récupérer le prix courant
        current_price = self._get_current_price()
        if current_price is None or current_price <= 0:
            return PaperTickResult(
                action_taken="no_price",
                detail="Prix BTC indisponible. Vérifiez que les données sont chargées.",
                current_price=0.0,
                timestamp=now.isoformat(),
                non_trade_reason="no_price",
            )

        # Capture le prix initial pour buy & hold (si pas encore fait)
        if account.btc_price_at_start is None:
            account.btc_price_at_start = current_price
            self.db.commit()

        # [v1.7] Déterminer les slots actifs
        slots = self.get_enabled_slots(account)
        max_pos = getattr(account, "max_open_positions", 1) or 1

        # Mode mono-slot (rétrocompatible) : exécuter un seul tick
        if max_pos <= 1 or len(slots) <= 1:
            slot_name = slots[0] if slots else "conservative"
            return self._tick_single_slot(
                account=account,
                slot_name=slot_name,
                current_price=current_price,
                now=now,
                is_multi=False,
            )

        # [v1.7] Mode multi-slot : itérer sur chaque slot
        slot_results: list[SlotTickResult] = []
        primary_result: Optional[PaperTickResult] = None

        for slot_name in slots:
            result = self._tick_single_slot(
                account=account,
                slot_name=slot_name,
                current_price=current_price,
                now=now,
                is_multi=True,
            )

            slot_results.append(SlotTickResult(
                slot=slot_name,
                action_taken=result.action_taken,
                detail=result.detail,
                profile_type=result.profile_type or slot_name,
                position_opened=result.position_opened,
                position_closed=result.position_closed,
            ))

            # Garder le résultat le plus "intéressant" comme résultat principal
            if primary_result is None or result.action_taken not in ("hold", "inactive", "no_price"):
                primary_result = result

        if primary_result is None:
            primary_result = PaperTickResult(
                action_taken="hold",
                detail=f"Multi-slot : {len(slots)} slots actifs, rien à faire",
                current_price=current_price,
                timestamp=now.isoformat(),
            )

        primary_result.slot_results = slot_results
        return primary_result

    def _tick_single_slot(
        self,
        account: PaperAccount,
        slot_name: str,
        current_price: float,
        now: datetime,
        is_multi: bool = False,
    ) -> PaperTickResult:
        """
        Exécute un tick pour un slot donné.

        Un slot = un profil avec ses paramètres propres.
        Chaque slot ne peut avoir qu'une seule position ouverte.
        """
        # Résoudre le profil pour ce slot
        profile_params = PROFILE_PRESETS.get(slot_name, PROFILE_PRESETS["conservative"])
        profile_name = slot_name
        is_auto_mode = False  # en multi-slot, chaque slot a un profil fixe

        # [v2.0.13] Enregistrer le prix dans le buffer tick momentum.
        # On enregistre à CHAQUE tick, même si on ne trade pas, pour construire
        # l'historique de prix nécessaire à la confirmation de direction.
        TickMomentumService.record_tick(slot_name, current_price, now)

        # [v1.6] Paramètres de décision pilotés par le profil
        _analysis_tf = getattr(profile_params, "analysis_timeframe", None) or "4h"
        _analysis_days = 1 if _analysis_tf in ("1m", "3m", "5m", "15m", "30m") else 7
        _buy_th = getattr(profile_params, "buy_threshold", None)
        _sell_th = getattr(profile_params, "sell_threshold", None)

        # Helper pour journaliser (best-effort, ne bloque pas le tick)
        def _log_tick(**kwargs):
            try:
                journal = JournalService(self.db)
                journal.log_tick(account_id=account.id, profile_type=profile_name, **kwargs)
            except Exception as e:
                logger.debug(f"Journal log error (non-blocking): {e}")

        # [v1.7] Vérifier la position ouverte pour CE slot
        if is_multi:
            open_pos = self.get_open_position_for_slot(slot_name)
        else:
            open_pos = self.get_open_position()

        if open_pos is not None:
            # --- Position ouverte : vérifier SL/TP/expiration ---
            close_reason = self._check_sl_tp(open_pos, current_price)

            if close_reason is None:
                # [v1.6.1] Passer la durée max du profil pour expiration rapide
                profile_max_hours = (
                    profile_params.max_position_duration_hours
                    if profile_params else None
                )
                close_reason = self._check_expiration(open_pos, now, profile_max_hours)

            if close_reason is not None:
                # [v2.0.24] SL/TP : utiliser le prix de l'ordre au lieu du prix courant.
                # Simule une exécution stop-limit : quand le SL/TP est franchi entre
                # deux ticks (gap de 5 sec), on exécute AU prix de l'ordre, pas au prix
                # actuel qui peut être bien pire. Avant ce fix, le trade #629 perdait
                # -$21.76 (-0.87%) au lieu du SL attendu de -0.20% car le prix avait
                # gappé de $600 entre deux ticks. Avec ce fix, la perte max par SL
                # est bornée à loss_cut_pct (= -$5 sur $2500 à 0.20%).
                if close_reason == "closed_sl":
                    exit_price = open_pos.stop_loss_price
                elif close_reason == "closed_tp":
                    exit_price = open_pos.take_profit_price
                else:
                    exit_price = current_price

                closed = self._close_position(open_pos, exit_price, close_reason, close_reason)
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

            # [v2.0.23] MICRO STOP LOSS — PRIORITÉ ABSOLUE (avant trailing stop)
            # Si le PnL latent dépasse le seuil négatif micro, on sort IMMÉDIATEMENT.
            # C'est le garde-fou ultime : on ne laisse JAMAIS une perte grossir.
            # Contrairement au loss_cut_pct (vérifié avec le score), le micro SL
            # est inconditionnel et ultra-serré (-0.01% = -$0.25 sur $2500).
            micro_sl_pct = getattr(profile_params, "micro_stop_loss_pct", None) if profile_params else None
            if micro_sl_pct is not None and micro_sl_pct > 0:
                micro_unrealized = self._calc_unrealized_pnl(open_pos, current_price)
                micro_unrealized_pct = (micro_unrealized / open_pos.position_size_usd * 100) if open_pos.position_size_usd > 0 else 0
                if micro_unrealized_pct <= -micro_sl_pct:
                    micro_reason = (
                        f"Micro stop loss : PnL latent {micro_unrealized_pct:.3f}% "
                        f"(≤ -{micro_sl_pct:.3f}%) → sortie immédiate"
                    )
                    closed = self._close_position(open_pos, current_price, micro_reason, "closed_micro_sl")
                    _log_tick(action_taken="closed_micro_sl", btc_price=current_price,
                              had_open_position=True, trade_id=closed.id,
                              leverage_final=getattr(closed, "leverage", 1.0))
                    return PaperTickResult(
                        action_taken="closed_micro_sl",
                        detail=f"Position fermée (micro stop loss) : {micro_reason}",
                        position_closed=PaperTradeResponse.model_validate(closed),
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        leverage_used=getattr(closed, "leverage", 1.0),
                        profile_type=profile_name,
                    )

            # [v2.0.8] TRAILING STOP — PRIORITÉ MAXIMALE (avant stale exit)
            # BUG FIX CRITIQUE : Avant v2.0.8, le stale exit (lignes 428-500) était vérifié
            # AVANT le trailing stop (lignes 502-540). Conséquence : quand une position
            # gagnante (peak > activation) redescendait en négatif, le stale_negative_exit
            # (2 min) se déclenchait EN PREMIER et fermait la position en perte, alors que
            # le trailing stop aurait dû la fermer plus tôt, en profit.
            # Exemple réel : peak +0.12%, trailing aurait dû fermer à +0.06% (drop 0.06%),
            # mais le stale négatif fermait à -0.056% après 2 min.
            # Fix : trailing stop vérifié EN PREMIER, il a la priorité sur le stale exit.
            ts_pct = getattr(profile_params, "trailing_stop_pct", None) if profile_params else None
            ts_activation = getattr(profile_params, "trailing_stop_activation_pct", None) if profile_params else None
            # [v2.0.9] Trailing relatif : drop_ratio a priorité sur ts_pct absolu
            ts_drop_ratio = getattr(profile_params, "trailing_stop_drop_ratio", None) if profile_params else None
            if (ts_pct or ts_drop_ratio) and ts_activation:
                unrealized_pnl_now = self._calc_unrealized_pnl(open_pos, current_price)
                unrealized_pct_now = (unrealized_pnl_now / open_pos.position_size_usd * 100) if open_pos.position_size_usd > 0 else 0

                # Calculer le pic de PnL % via highest/lowest price
                if open_pos.direction == "long" and open_pos.highest_price_since_entry:
                    peak_pnl = self._calc_unrealized_pnl_at_price(open_pos, open_pos.highest_price_since_entry)
                elif open_pos.direction == "short" and open_pos.lowest_price_since_entry:
                    peak_pnl = self._calc_unrealized_pnl_at_price(open_pos, open_pos.lowest_price_since_entry)
                else:
                    peak_pnl = 0

                peak_pct = (peak_pnl / open_pos.position_size_usd * 100) if open_pos.position_size_usd > 0 else 0

                # Condition 1 : Trailing stop
                # [v2.0.9] TRAILING RELATIF — Protège les gains proportionnellement.
                # Ancien système (absolu) : on sortait quand le recul >= 0.06% fixe.
                #   → Peak 0.12% - 0.06% = exit à 0.06% → 50% du gain perdu !
                # Nouveau système (relatif) : on sort quand le gain < peak * (1 - drop_ratio).
                #   → Peak 0.12% × 70% = exit à 0.084% → seulement 30% perdu.
                # Le trailing relatif s'adapte à la taille du gain : plus le gain est gros,
                # plus il tolère de recul en absolu (mais garde toujours ~70% du gain).
                if peak_pct >= ts_activation:
                    trailing_triggered = False
                    if ts_drop_ratio is not None and peak_pct > 0:
                        # Mode RELATIF : sortir quand le gain actuel < peak * (1 - drop_ratio)
                        # Ex: drop_ratio=0.30, peak=0.20% → exit sous 0.14% (garde 70%)
                        retention = 1.0 - ts_drop_ratio
                        min_gain_pct = peak_pct * retention
                        if unrealized_pct_now <= min_gain_pct:
                            trailing_triggered = True
                            signal_reason = (
                                f"Trailing stop relatif : pic {peak_pct:.3f}%, actuel {unrealized_pct_now:.3f}%, "
                                f"seuil {min_gain_pct:.3f}% ({retention:.0%} du pic), "
                                f"recul {((peak_pct - unrealized_pct_now) / peak_pct * 100):.1f}% ≥ {ts_drop_ratio * 100:.0f}%"
                            )
                    elif ts_pct and (peak_pct - unrealized_pct_now) >= ts_pct:
                        # Mode ABSOLU (fallback) : recul fixe en points de %
                        trailing_triggered = True
                        signal_reason = (
                            f"Trailing stop absolu : pic {peak_pct:.3f}%, actuel {unrealized_pct_now:.3f}%, "
                            f"recul {(peak_pct - unrealized_pct_now):.3f}% ≥ seuil {ts_pct}%"
                        )

                    if trailing_triggered:
                        closed = self._close_position(open_pos, current_price, signal_reason, "closed_trailing_stop")
                        _log_tick(action_taken="closed_trailing_stop", btc_price=current_price,
                                  had_open_position=True, trade_id=closed.id,
                                  leverage_final=getattr(closed, "leverage", 1.0))
                        return PaperTickResult(
                            action_taken="closed_trailing_stop",
                            detail=f"Position fermée (trailing stop) : {signal_reason}",
                            position_closed=PaperTradeResponse.model_validate(closed),
                            current_price=current_price,
                            timestamp=now.isoformat(),
                            leverage_used=getattr(closed, "leverage", 1.0),
                            profile_type=profile_name,
                        )

                # [v2.0.8] Condition 2 : Breakeven stop (filet de sécurité)
                # Si la position a atteint un petit profit (peak >= activation/2 = 0.05%)
                # mais PAS assez pour activer le trailing (peak < activation), et que
                # le PnL retombe à 0% ou en négatif → fermer au breakeven.
                # Cela évite qu'une position qui ÉTAIT gagnante se transforme en perte.
                # Sans ce filet, la seule protection est le stale négatif (2 min) ou le SL (-0.20%).
                breakeven_activation = ts_activation / 2  # 0.05% par défaut

                # [v2.0.12] GAIN EROSION STOP — Protection des gains dès le premier dollar.
                # Comble le trou entre trailing (seuil activation) et breakeven (attend PnL ≤ 0).
                # Si le gain a existé et qu'il s'érode de plus de X% du pic → sortie immédiate.
                # [v2.0.28] Seuil min relevé 0.01→0.02% : les peaks < $0.50 sont du bruit de tick.
                # L'analyse du run v2.0.27 montre des gain erosion exits à +$0.12-$0.18 sur des
                # peaks de 0.01% — ces micro-gains ne couvrent pas les frais et polluent le journal.
                ge_ratio = getattr(profile_params, "gain_erosion_ratio", None) if profile_params else None
                if ge_ratio is not None and peak_pct >= 0.02 and peak_pct < ts_activation:
                    # Le gain erosion ne s'applique que sous le seuil d'activation du trailing.
                    # Au-dessus, le trailing (15% drop) est plus serré et prend le relais.
                    ge_retention = 1.0 - ge_ratio
                    ge_min_pct = peak_pct * ge_retention
                    if unrealized_pct_now <= ge_min_pct:
                        ge_reason = (
                            f"Gain erosion stop : pic {peak_pct:.3f}%, actuel {unrealized_pct_now:.3f}%, "
                            f"seuil {ge_min_pct:.3f}% ({ge_retention:.0%} du pic), "
                            f"érosion {((peak_pct - unrealized_pct_now) / peak_pct * 100):.1f}% ≥ {ge_ratio * 100:.0f}%"
                        )
                        closed = self._close_position(open_pos, current_price, ge_reason, "closed_gain_erosion")
                        _log_tick(action_taken="closed_gain_erosion", btc_price=current_price,
                                  had_open_position=True, trade_id=closed.id,
                                  leverage_final=getattr(closed, "leverage", 1.0))
                        return PaperTickResult(
                            action_taken="closed_gain_erosion",
                            detail=f"Position fermée (gain erosion) : {ge_reason}",
                            position_closed=PaperTradeResponse.model_validate(closed),
                            current_price=current_price,
                            timestamp=now.isoformat(),
                            leverage_used=getattr(closed, "leverage", 1.0),
                            profile_type=profile_name,
                        )

                if peak_pct >= breakeven_activation and unrealized_pct_now <= 0:
                    signal_reason = (
                        f"Breakeven stop : pic {peak_pct:.3f}% (≥ {breakeven_activation:.3f}%), "
                        f"PnL retombé à {unrealized_pct_now:.3f}% → protection breakeven"
                    )
                    closed = self._close_position(open_pos, current_price, signal_reason, "closed_breakeven")
                    _log_tick(action_taken="closed_breakeven", btc_price=current_price,
                              had_open_position=True, trade_id=closed.id,
                              leverage_final=getattr(closed, "leverage", 1.0))
                    return PaperTickResult(
                        action_taken="closed_breakeven",
                        detail=f"Position fermée (breakeven) : {signal_reason}",
                        position_closed=PaperTradeResponse.model_validate(closed),
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        leverage_used=getattr(closed, "leverage", 1.0),
                        profile_type=profile_name,
                    )

            # [v2.0.18] CANDLE REVERSAL EXIT — Sortie active quand la couleur de bougie change.
            # L'observation empirique montre que les trades profitables gardent la même couleur
            # de pastille (E=S), tandis que les perdants changent de couleur.
            # Ce check détecte quand le momentum s'inverse par rapport à l'entrée et sort
            # IMMÉDIATEMENT (après un délai de confirmation de ~3 sec pour éviter le bruit).
            # Priorité APRÈS le trailing stop (qui protège les gains) et AVANT le stale exit.
            cr_enabled = getattr(profile_params, "candle_reversal_exit_enabled", False) if profile_params else False
            if cr_enabled and getattr(open_pos, "entry_candle_direction", None):
                cr_window = getattr(profile_params, "candle_reversal_window_seconds", 15.0)
                cr_min_sec = getattr(profile_params, "candle_reversal_min_seconds", 3.0)
                cr_min_ticks = getattr(profile_params, "tick_momentum_min_ticks", 2) if profile_params else 2

                should_exit, reversal_delay, cr_reason = TickMomentumService.check_candle_reversal(
                    slot=slot_name,
                    entry_candle_direction=open_pos.entry_candle_direction,
                    trade_direction=open_pos.direction,
                    window_seconds=cr_window,
                    min_ticks=cr_min_ticks,
                    min_reversal_seconds=cr_min_sec,
                )

                if should_exit:
                    # Stocker le délai de reversal sur le trade avant fermeture
                    open_pos.reversal_delay_seconds = round(reversal_delay, 2)
                    self.db.commit()

                    closed = self._close_position(
                        open_pos, current_price, cr_reason, "closed_candle_reversal"
                    )
                    # Reset le tracker de reversal après fermeture
                    TickMomentumService.reset_reversal(slot_name)

                    _log_tick(action_taken="closed_candle_reversal", btc_price=current_price,
                              had_open_position=True, trade_id=closed.id,
                              leverage_final=getattr(closed, "leverage", 1.0))
                    return PaperTickResult(
                        action_taken="closed_candle_reversal",
                        detail=f"Position fermée (candle reversal) : {cr_reason}",
                        position_closed=PaperTradeResponse.model_validate(closed),
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        leverage_used=getattr(closed, "leverage", 1.0),
                        profile_type=profile_name,
                    )

            # [v1.6] Sortie rapide — Stale position
            # Si la position stagne depuis trop longtemps (faible mouvement),
            # on libère la place pour d'autres opportunités.
            # [v1.9.5] Stale exit ASYMÉTRIQUE : les positions en perte sortent plus vite.
            # [v2.0.8] Le stale exit est maintenant APRÈS le trailing stop et le breakeven.
            # Le trailing/breakeven ont priorité car ils protègent les gains.
            # Le stale est un fallback pour les positions qui n'ont JAMAIS été en profit.
            stale_minutes = getattr(profile_params, "stale_exit_minutes", None) if profile_params else None
            stale_negative_minutes = getattr(profile_params, "stale_negative_exit_minutes", None) if profile_params else None
            if stale_minutes and stale_minutes > 0:
                entry_ts = _ensure_aware(open_pos.entry_ts)
                elapsed_min = (now - entry_ts).total_seconds() / 60
                unrealized_pnl_now = self._calc_unrealized_pnl(open_pos, current_price)
                unrealized_pct = (unrealized_pnl_now / open_pos.position_size_usd * 100) if open_pos.position_size_usd > 0 else 0

                # [v1.9.5] Chemin 1 : Position en perte → sortie accélérée
                # Si le PnL est négatif ET qu'on a dépassé le seuil de stale négatif,
                # on sort sans attendre le stale complet. Cela évite que les positions
                # dérivent lentement vers le SL pendant 15 min.
                effective_negative_minutes = stale_negative_minutes or stale_minutes
                if unrealized_pct < -0.03 and elapsed_min >= effective_negative_minutes:
                    signal_reason = (
                        f"Position en perte depuis {elapsed_min:.0f} min, PnL latent {unrealized_pct:.2f}% "
                        f"(seuil négatif {effective_negative_minutes} min)"
                    )
                    closed = self._close_position(open_pos, current_price, signal_reason, "closed_stale")
                    _log_tick(action_taken="closed_stale", btc_price=current_price,
                              had_open_position=True, trade_id=closed.id,
                              leverage_final=getattr(closed, "leverage", 1.0))
                    return PaperTickResult(
                        action_taken="closed_stale",
                        detail=f"Position fermée (dérive négative) : {signal_reason}",
                        position_closed=PaperTradeResponse.model_validate(closed),
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        leverage_used=getattr(closed, "leverage", 1.0),
                        profile_type=profile_name,
                    )

                # [v1.6.2] Seuil de stagnation adapté au profil
                # Pour les profils tight (scalping, loss_cut ≤ 0.5%), on utilise
                # le trailing_stop_activation_pct comme seuil de stagnation.
                # [v2.0.0-fix] Avant, on utilisait profit_take_pct (0.8%), ce qui
                # classait des trades à +0.46% comme "stagnants" alors que le
                # trailing stop (activation 0.20%) était déjà actif et aurait dû
                # gérer la sortie. Résultat : le stale exit overridait le trailing
                # stop et tuait les trades profitables (trade #364 : +$11.39 fermé stale).
                # Avec trailing_stop_activation_pct (0.20%) :
                #   - Position à +0.46% → PAS stagnante → trailing gère ✓
                #   - Position à +0.05% → stagnante → fermée, slot libéré ✓
                # Pour les profils classiques, le seuil reste à 0.1%.
                stale_pnl_threshold = 0.1
                if profile_params and profile_params.loss_cut_pct <= 0.5:
                    ts_act = getattr(profile_params, "trailing_stop_activation_pct", None)
                    stale_pnl_threshold = ts_act if ts_act else profile_params.profit_take_pct

                # Chemin 2 : Position plate → stale exit normal (inchangé)
                if elapsed_min >= stale_minutes and abs(unrealized_pct) < stale_pnl_threshold:
                    signal_reason = f"Position stagnante depuis {elapsed_min:.0f} min, PnL latent {unrealized_pct:.2f}%"
                    closed = self._close_position(open_pos, current_price, signal_reason, "closed_stale")
                    _log_tick(action_taken="closed_stale", btc_price=current_price,
                              had_open_position=True, trade_id=closed.id,
                              leverage_final=getattr(closed, "leverage", 1.0))
                    return PaperTickResult(
                        action_taken="closed_stale",
                        detail=f"Position fermée (stagnante) : {signal_reason}",
                        position_closed=PaperTradeResponse.model_validate(closed),
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        leverage_used=getattr(closed, "leverage", 1.0),
                        profile_type=profile_name,
                    )

            # [v1.6] Sortie rapide — Momentum fade
            # Si le profit latent a atteint un pic puis recule significativement,
            # on prend le profit restant avant qu'il ne disparaisse.
            # [v2.0.0] Momentum fade = suspect principal de destruction de valeur.
            # Mode "restricted" : ne se déclenche que si le pic dépasse un seuil
            # d'amplitude minimum. En dessous, on laisse le trailing stop gérer.
            # Mode "disabled" : momentum fade complètement désactivé.
            mf_enabled = getattr(profile_params, "momentum_fade_enabled", False) if profile_params else False
            mf_mode = getattr(profile_params, "momentum_fade_mode", "enabled") if profile_params else "enabled"
            if mf_enabled and mf_mode != "disabled":
                unrealized_pnl_now = self._calc_unrealized_pnl(open_pos, current_price)
                # Le pic de PnL est approximé via highest/lowest price
                if open_pos.direction == "long" and open_pos.highest_price_since_entry:
                    peak_pnl = self._calc_unrealized_pnl_at_price(open_pos, open_pos.highest_price_since_entry)
                elif open_pos.direction == "short" and open_pos.lowest_price_since_entry:
                    peak_pnl = self._calc_unrealized_pnl_at_price(open_pos, open_pos.lowest_price_since_entry)
                else:
                    peak_pnl = 0

                # Déclencher si le peak_pnl était > 0.1% du capital et que
                # le PnL actuel a reculé en dessous du seuil de rétention.
                # [v1.9.5] Rétention configurable via momentum_fade_retention (défaut 0.4).
                # Plus la rétention est haute, plus on garde longtemps les gains qui s'essoufflent.
                # 0.55 = sort quand le PnL tombe sous 55% du pic (vs ancien 40% hardcodé).
                mf_retention = getattr(profile_params, "momentum_fade_retention", None) if profile_params else None
                if mf_retention is None:
                    mf_retention = 0.4  # Valeur historique par défaut
                peak_pct = (peak_pnl / open_pos.position_size_usd * 100) if open_pos.position_size_usd > 0 else 0
                if peak_pct > 0.1 and peak_pnl > 0 and unrealized_pnl_now < peak_pnl * mf_retention:
                    # [v2.0.0] En mode restricted, vérifier que l'amplitude du pic
                    # dépasse le seuil minimum ET que la sortie est net-positive après coûts.
                    mf_min_amp = getattr(profile_params, "momentum_fade_min_amplitude_pct", None) if profile_params else None
                    if mf_mode == "restricted" and mf_min_amp is not None:
                        if peak_pct < mf_min_amp:
                            # Pic trop petit — on laisse le trailing stop gérer
                            pass  # Ne pas sortir en momentum fade
                        else:
                            # Vérifier que la sortie reste net-positive après coûts estimés
                            from app.services.trading_cost_service import get_cost_model
                            cost_est = get_cost_model("realistic")
                            lev = getattr(open_pos, "leverage", 1.0) or 1.0
                            rt_cost = cost_est.round_trip_cost_usd(
                                open_pos.position_size_usd * lev
                            )
                            if unrealized_pnl_now > rt_cost:
                                signal_reason = (
                                    f"Momentum fade (restricted) : pic PnL +{peak_pnl:.2f} USD ({peak_pct:.2f}%), "
                                    f"actuel {unrealized_pnl_now:.2f} USD, net après coûts: {unrealized_pnl_now - rt_cost:.2f}"
                                )
                                closed = self._close_position(open_pos, current_price, signal_reason, "closed_momentum_fade")
                                _log_tick(action_taken="closed_momentum_fade", btc_price=current_price,
                                          had_open_position=True, trade_id=closed.id,
                                          leverage_final=getattr(closed, "leverage", 1.0))
                                return PaperTickResult(
                                    action_taken="closed_momentum_fade",
                                    detail=f"Position fermée (momentum fade restricted) : {signal_reason}",
                                    position_closed=PaperTradeResponse.model_validate(closed),
                                    current_price=current_price,
                                    timestamp=now.isoformat(),
                                    leverage_used=getattr(closed, "leverage", 1.0),
                                    profile_type=profile_name,
                                )
                            # Sinon : la sortie serait net-negative → on laisse courir
                    else:
                        # Mode "enabled" (comportement d'origine) — momentum fade normal
                        signal_reason = (
                            f"Momentum fade : pic PnL +{peak_pnl:.2f} USD ({peak_pct:.2f}%), "
                            f"actuel {unrealized_pnl_now:.2f} USD"
                        )
                        closed = self._close_position(open_pos, current_price, signal_reason, "closed_momentum_fade")
                        _log_tick(action_taken="closed_momentum_fade", btc_price=current_price,
                                  had_open_position=True, trade_id=closed.id,
                                  leverage_final=getattr(closed, "leverage", 1.0))
                        return PaperTickResult(
                            action_taken="closed_momentum_fade",
                            detail=f"Position fermée (momentum fade) : {signal_reason}",
                            position_closed=PaperTradeResponse.model_validate(closed),
                            current_price=current_price,
                            timestamp=now.isoformat(),
                            leverage_used=getattr(closed, "leverage", 1.0),
                            profile_type=profile_name,
                        )

            # Vérifier si le DecisionService recommande de fermer
            decision_result = self._get_decision(
                timeframe=_analysis_tf, history_days=_analysis_days,
                buy_threshold=_buy_th, sell_threshold=_sell_th,
            )
            if decision_result:
                action = decision_result.get("recommendation", {}).get("action", "attendre")
                score = decision_result.get("combined_score", 0)
                confidence = decision_result.get("recommendation", {}).get("confidence", "low")
                unrealized_pnl = self._calc_unrealized_pnl(open_pos, current_price)
                unrealized_pnl_pct = (unrealized_pnl / open_pos.position_size_usd * 100) if open_pos.position_size_usd > 0 else 0

                # [v1.6] Mode auto : résoudre le profil réel pour les seuils de sortie
                if is_auto_mode:
                    resolved_profile = TradingProfileService.auto_select_profile(score, confidence)
                    profile_params = PROFILE_PRESETS[resolved_profile]
                    profile_name = f"auto→{resolved_profile}"

                # [v1.9.1] Protection anti-micro-PnL — min_hold_seconds
                # Si la position est trop jeune, on ne ferme PAS sur signal contraire.
                # SL/TP/expiration/trailing restent actifs normalement.
                # Cela empêche les fermetures-éclair qui churnent à 0.00$.
                # [v1.9.3] Short-specific min_hold : les shorts peuvent avoir un
                # min_hold plus long pour capturer le retracement.
                min_hold = getattr(profile_params, "min_hold_seconds", None) if profile_params else None
                if open_pos.direction == "short" and profile_params:
                    short_min_hold = getattr(profile_params, "short_min_hold_seconds", None)
                    if short_min_hold is not None:
                        min_hold = short_min_hold
                entry_ts = _ensure_aware(open_pos.entry_ts)
                elapsed_seconds = (now - entry_ts).total_seconds()
                trade_too_young = min_hold is not None and elapsed_seconds < min_hold

                close_signal = False
                signal_reason = ""

                if open_pos.direction == "long":
                    # [v2.0.11] Protection reversal LONG : un mean_reversion_long est
                    # ouvert PARCE QUE le score est négatif (survente). Le signal contraire
                    # ne doit fermer que si le score bearish s'est INTENSIFIÉ au-delà du
                    # score d'entrée, sinon la thèse de renversement n'est pas invalidée.
                    # [v2.0.19] Étendu aux tick_override_long : même protection car le trade
                    # est basé sur la direction du prix, pas sur le score technique.
                    is_reversal = (open_pos.entry_reason or "").startswith(("mean_reversion_", "tick_override_"))
                    if action == "vendre" and not trade_too_young:
                        if is_reversal and open_pos.decision_score is not None:
                            # Reversal LONG : ne fermer que si le bearish est PIRE qu'à l'entrée
                            entry_score_abs = abs(open_pos.decision_score)
                            if abs(score) > entry_score_abs:
                                close_signal = True
                                signal_reason = (
                                    f"Signal contraire (reversal invalidé) : vendre "
                                    f"(score={score}, entrée={open_pos.decision_score})"
                                )
                            # Sinon : le même score bearish qu'à l'entrée → normal pour un reversal
                        else:
                            close_signal = True
                            signal_reason = f"Signal contraire : vendre (score={score})"
                    elif action == "attendre" and score <= 0 and not trade_too_young:
                        # [v1.9.5] Relevé de -10 à -15 : ne ferme sur "signal nettement
                        # contraire" que si le score est vraiment fortement bearish.
                        # Un score de -10 peut être du bruit ; -15 indique une vraie pression.
                        if score <= -15:
                            if is_reversal and open_pos.decision_score is not None:
                                if abs(score) > abs(open_pos.decision_score):
                                    close_signal = True
                                    signal_reason = f"Signal nettement contraire (reversal invalidé) : attendre (score={score})"
                            else:
                                close_signal = True
                                signal_reason = f"Signal nettement contraire : attendre (score={score})"

                elif open_pos.direction == "short":
                    # [v1.9.3] Seuil configurable pour fermer un short par signal contraire.
                    # Le moteur ne tue plus un short dès que le signal principal redevient
                    # légèrement bullish. Il exige un vrai retournement (score >= threshold).
                    short_exit_th = 10  # défaut historique
                    if profile_params:
                        short_exit_th = getattr(profile_params, "short_exit_score_threshold", None) or 10

                    # [v2.0.11] Protection reversal SHORT : un mean_reversion_short est
                    # ouvert PARCE QUE le score est bullish (surachat). Fermer sur le MÊME
                    # score bullish crée une boucle de churn : ouvrir → 50sec → fermer → repeat.
                    # Fix : pour les reversals, le signal contraire ne ferme que si le score
                    # a AUGMENTÉ au-delà du score d'entrée (la pression bullish s'intensifie,
                    # invalidant la thèse de mean-reversion). Sinon, laisser le trailing stop,
                    # le stale, ou le SL/TP gérer la sortie naturellement.
                    # [v2.0.19] Étendu aux tick_override_short : même protection car le trade
                    # est basé sur la direction du prix. Le score bullish n'invalide pas un
                    # short basé sur un momentum tick descendant.
                    is_reversal = (open_pos.entry_reason or "").startswith(("mean_reversion_", "tick_override_"))
                    if is_reversal and open_pos.decision_score is not None:
                        # Le seuil est le score d'entrée : ne fermer que si le bullish s'intensifie
                        short_exit_th = max(short_exit_th, abs(open_pos.decision_score) + 1)

                    if action == "acheter" and not trade_too_young:
                        if score >= short_exit_th:
                            close_signal = True
                            if is_reversal:
                                signal_reason = (
                                    f"Signal contraire (reversal invalidé) : acheter "
                                    f"(score={score} > entrée={open_pos.decision_score}, seuil={short_exit_th})"
                                )
                            else:
                                signal_reason = f"Signal contraire : acheter (score={score}, seuil={short_exit_th})"
                        # Si le score est positif mais sous le seuil, le short respire encore
                    elif action == "attendre" and score >= 0 and not trade_too_young:
                        # [v1.9.1] Même logique adoucie pour les shorts
                        # [v1.9.3] Utilise le seuil configurable au lieu du fixe 10
                        if score >= max(short_exit_th, 10):
                            close_signal = True
                            signal_reason = f"Signal nettement contraire : attendre (score={score})"

                # Profit taking : seuil piloté par le profil
                pt_pct = profile_params.profit_take_pct if profile_params else 2.0
                if not close_signal and unrealized_pnl_pct >= pt_pct:
                    close_signal = True
                    signal_reason = f"Prise de profit : PnL latent {unrealized_pnl_pct:.1f}%"

                # Loss cut : seuil piloté par le profil
                lc_pct = profile_params.loss_cut_pct if profile_params else 1.5
                lc_score = profile_params.loss_cut_score_threshold if profile_params else 30
                if not close_signal and unrealized_pnl_pct <= -lc_pct:
                    # [v1.6.1] Profil tight (scalping) : coupe inconditionnelle
                    # Pour les profils avec loss_cut_pct ≤ 0.5%, on ne vérifie pas
                    # le score — on coupe immédiatement. En scalping, 0.3% de perte
                    # est déjà significatif et ne doit pas dépendre du signal.
                    if lc_pct <= 0.5:
                        close_signal = True
                        signal_reason = f"Coupe de perte rapide (scalping) : PnL {unrealized_pnl_pct:.1f}%"
                    else:
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

            # [v2.0.22] SAS D'ENTRÉE SÉCURISÉ — Vérifier si un SAS est en attente.
            # Si oui, évaluer le PnL virtuel avant de continuer.
            sas_pending = EntrySasService.get_pending(slot_name)
            if sas_pending is not None:
                sas_verdict = EntrySasService.evaluate(slot_name, current_price, now)

                if sas_verdict.action == "approved":
                    # ✅ SAS confirmé → ouvrir la vraie position au prix courant
                    # Recalculer SL/TP relatifs au prix d'entrée réel
                    sas_dir = sas_pending.direction
                    _sas_lc = profile_params.loss_cut_pct / 100 if profile_params and profile_params.loss_cut_pct <= 0.5 else 0.002
                    _sas_pt = profile_params.profit_take_pct / 100 if profile_params and profile_params.loss_cut_pct <= 0.5 else 0.008
                    if sas_dir == "long":
                        sas_sl = current_price * (1 - _sas_lc)
                        sas_tp = current_price * (1 + _sas_pt)
                    else:
                        sas_sl = current_price * (1 + _sas_lc)
                        sas_tp = current_price * (1 - _sas_pt)

                    position = self._open_position(
                        account=account,
                        price=current_price,
                        sl=sas_sl,
                        tp=sas_tp,
                        size_usd=sas_pending.position_size_usd,
                        reason=f"sas_confirmed_{sas_dir} | {sas_pending.reason}",
                        score=sas_pending.score,
                        direction=sas_dir,
                        now=now,
                        leverage=sas_pending.leverage,
                        leverage_reason=sas_pending.leverage_reason,
                        profile_type=sas_pending.profile_type,
                        slot=slot_name if is_multi else None,
                        entry_candle_direction=sas_pending.entry_candle_direction,
                    )

                    if position is None:
                        _log_tick(action_taken="hold", btc_price=current_price,
                                  decision_score=sas_pending.score,
                                  reason_no_trade="slot_already_occupied",
                                  reason_detail=f"SAS approuvé mais slot '{slot_name}' occupé")
                        return PaperTickResult(
                            action_taken="hold",
                            detail=f"SAS approuvé mais slot '{slot_name}' déjà occupé.",
                            current_price=current_price,
                            timestamp=now.isoformat(),
                            decision_score=sas_pending.score,
                            profile_type=profile_name,
                            non_trade_reason="slot_already_occupied",
                        )

                    _log_tick(action_taken=f"opened_{sas_dir}", btc_price=current_price,
                              decision_score=sas_pending.score,
                              trade_id=position.id,
                              quality_gate_passed=True,
                              quality_gate_reason="sas_approved")
                    return PaperTickResult(
                        action_taken=f"opened_{sas_dir}",
                        detail=(
                            f"Position {sas_dir} ouverte (SAS confirmé) @ {current_price:.2f} "
                            f"| SL={sas_sl:.2f} | TP={sas_tp:.2f} | Levier x{sas_pending.leverage} "
                            f"| {sas_verdict.reason}"
                        ),
                        position_opened=PaperTradeResponse.model_validate(position),
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        decision_score=sas_pending.score,
                        risk_allowed=True,
                        leverage_used=sas_pending.leverage,
                        profile_type=profile_name,
                    )

                elif sas_verdict.action == "rejected":
                    # 🚫 SAS rejeté → ne pas ouvrir
                    _log_tick(action_taken="hold", btc_price=current_price,
                              decision_score=sas_pending.score,
                              reason_no_trade="sas_rejected",
                              reason_detail=sas_verdict.reason[:500])
                    return PaperTickResult(
                        action_taken="hold",
                        detail=f"SAS rejeté : {sas_verdict.reason}",
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        decision_score=sas_pending.score,
                        profile_type=profile_name,
                        non_trade_reason="sas_rejected",
                    )

                else:
                    # ⏳ SAS en attente → ne rien faire ce tick
                    _log_tick(action_taken="hold", btc_price=current_price,
                              decision_score=sas_pending.score,
                              reason_no_trade="sas_monitoring",
                              reason_detail=sas_verdict.reason[:500])
                    return PaperTickResult(
                        action_taken="hold",
                        detail=f"SAS en observation : {sas_verdict.reason}",
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        decision_score=sas_pending.score,
                        profile_type=profile_name,
                        non_trade_reason="sas_monitoring",
                    )

            decision_result = self._get_decision(
                timeframe=_analysis_tf, history_days=_analysis_days,
                buy_threshold=_buy_th, sell_threshold=_sell_th,
            )
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

            # [v1.6] Mode auto : résoudre le profil réel en fonction du signal
            if is_auto_mode:
                resolved_profile = TradingProfileService.auto_select_profile(score, confidence)
                profile_params = PROFILE_PRESETS[resolved_profile]
                profile_name = f"auto→{resolved_profile}"
                logger.info(f"🤖 Auto-profil résolu : {resolved_profile} (score={score}, conf={confidence})")

            # [v2.0.10] MARKET QUALITY — Calculé AVANT le reversal pour enrichir les signaux.
            # Le mq_data (micro_trend, volume, price_position) est utilisé par :
            # 1. Le reversal check (micro_trend ≤ -2 → signal SHORT)
            # 2. Le veto bearish (micro_trend < 0 → bloquer les LONG)
            # 3. Le market quality gate (quality_score minimum)
            # 4. Les structural proofs
            min_mq = getattr(profile_params, "min_market_quality", None) if profile_params else None
            min_vr = getattr(profile_params, "min_volume_ratio", None) if profile_params else None
            long_qf = getattr(profile_params, "long_quality_filter", False) if profile_params else False

            mq_reason = None
            mq_data = None
            # Toujours calculer mq_data pour le tracing et les gates
            if min_mq is not None and min_mq > 0:
                mq_reason, mq_data = self._check_market_quality(
                    decision_result=decision_result,
                    direction="long" if action == "acheter" else "short",
                    min_quality=min_mq,
                    min_volume_ratio=min_vr or 0.0,
                    long_quality_filter=long_qf,
                )
            else:
                # Compute quality data for tracing even without gating
                _, mq_data = self._check_market_quality(
                    decision_result=decision_result,
                    direction="long" if action == "acheter" else "short",
                )

            # [v2.0.14] TICK MOMENTUM DIRECTION OVERRIDE — La bougie décide la direction.
            # En mode override, on n'utilise PAS la direction du score technique (lagging 15 min).
            # On utilise la direction RÉELLE du prix sur les dernières ~30 secondes :
            # - Bougie verte (prix monte) → LONG
            # - Bougie rouge (prix descend) → SHORT
            # - Bougie neutre (flat) → pas de trade
            # Le score technique est gardé comme filtre de qualité (marché actif).
            # Cela élimine le biais 100% short quand les indicateurs restent bearish.
            tm_override_active = False
            tm_override_enabled = getattr(profile_params, "tick_momentum_override_direction", False) if profile_params else False
            tm_enabled = getattr(profile_params, "tick_momentum_enabled", False) if profile_params else False

            if tm_override_enabled and tm_enabled:
                tm_window = getattr(profile_params, "tick_momentum_window_seconds", 30.0)
                tm_min_ticks = getattr(profile_params, "tick_momentum_min_ticks", 3)

                tm_direction, tm_result = TickMomentumService.detect_direction(
                    slot=slot_name,
                    window_seconds=tm_window,
                    min_ticks=tm_min_ticks,
                )

                if tm_direction is None:
                    # Bougie flat ou données insuffisantes → pas de trade
                    # Ne bloque pas au démarrage (insufficient_data → on laisse passer l'ancien flow)
                    if tm_result.direction != "insufficient_data":
                        _log_tick(action_taken="hold", btc_price=current_price,
                                  decision_score=score, decision_action=action,
                                  decision_confidence=confidence,
                                  reason_no_trade="tick_momentum_no_direction",
                                  reason_detail=tm_result.detail[:500])
                        return PaperTickResult(
                            action_taken="hold",
                            detail=f"Bougie neutre : {tm_result.detail}",
                            current_price=current_price,
                            timestamp=now.isoformat(),
                            decision_score=score,
                            decision_action=action,
                            profile_type=profile_name,
                            non_trade_reason="tick_momentum_no_direction",
                        )
                    # insufficient_data → on continue avec le flow normal (fallback)
                else:
                    # La bougie a une direction claire → override
                    old_action = action
                    action = "acheter" if tm_direction == "long" else "vendre"
                    tm_override_active = True
                    logger.info(
                        f"🕯️ Candle override [{slot_name}]: {old_action}→{action} "
                        f"({tm_result.detail})"
                    )

                    # [v2.0.21] MOMENTUM STABILITY CHECK — Ne pas entrer si la bougie
                    # est sur le point de changer de couleur. Quand le momentum 30s dit "up"
                    # mais les 10 dernières secondes disent "down", on est en fin de bougie
                    # verte → si on entre LONG maintenant, on va changer de pastille
                    # immédiatement → trade perdant. On attend la prochaine bougie stable.
                    is_stable, stability_detail = TickMomentumService.check_momentum_stability(
                        slot=slot_name,
                        direction=tm_direction,
                        long_window=tm_window,
                        short_window=max(tm_window / 3, 8.0),
                        min_ticks=tm_min_ticks,
                    )
                    if not is_stable:
                        logger.info(f"⏸️ Momentum instable [{slot_name}]: {stability_detail}")
                        _log_tick(action_taken="hold", btc_price=current_price,
                                  decision_score=score, decision_action=action,
                                  decision_confidence=confidence,
                                  reason_no_trade="momentum_unstable",
                                  reason_detail=stability_detail[:500])
                        return PaperTickResult(
                            action_taken="hold",
                            detail=f"Momentum instable, bougie en fin de vie : {stability_detail}",
                            current_price=current_price,
                            timestamp=now.isoformat(),
                            decision_score=score,
                            decision_action=action,
                            profile_type=profile_name,
                            non_trade_reason="momentum_unstable",
                        )

            # [v2.0.26] TREND ALIGNMENT FILTER — Bloque les trades override
            # contre-tendance. L'analyse de 92 trades (v2.0.25) montre que les
            # shorts perdent quand le score est fortement bullish, et symétriquement
            # les longs perdent quand le score est fortement bearish.
            # Le tick_override ouvre sur une micro-bougie 30s, mais la tendance de
            # fond ramène le prix dans l'autre sens → fermeture en perte.
            # [v2.0.27] Symétrique : bloque aussi les LONGs quand score < -threshold.
            if tm_override_active and profile_params:
                ta_threshold = getattr(profile_params, "trend_alignment_score_threshold", None)
                if ta_threshold is not None:
                    # SHORT override bloqué en marché bullish (score > +threshold)
                    if action == "vendre" and score > ta_threshold:
                        ta_reason = (
                            f"trend_alignment_blocked: SHORT override bloqué car score={score} > "
                            f"threshold={ta_threshold} (marché bullish, short contre-tendance)"
                        )
                        logger.info(f"🚫 Trend alignment [{slot_name}]: {ta_reason}")
                        _log_tick(action_taken="hold", btc_price=current_price,
                                  decision_score=score, decision_action=action,
                                  decision_confidence=confidence,
                                  reason_no_trade="trend_alignment_blocked",
                                  reason_detail=ta_reason[:500])
                        return PaperTickResult(
                            action_taken="hold",
                            detail=ta_reason,
                            current_price=current_price,
                            timestamp=now.isoformat(),
                            decision_score=score,
                            decision_action=action,
                            profile_type=profile_name,
                            non_trade_reason="trend_alignment_blocked",
                        )
                    # [v2.0.27] LONG override bloqué en marché bearish (score < -threshold)
                    # Même logique symétrique : une bougie verte 30s en tendance baissière
                    # est un faux signal → BTC redescend → le long ferme en perte.
                    if action == "acheter" and score < -ta_threshold:
                        ta_reason = (
                            f"trend_alignment_blocked: LONG override bloqué car score={score} < "
                            f"-{ta_threshold} (marché bearish, long contre-tendance)"
                        )
                        logger.info(f"🚫 Trend alignment [{slot_name}]: {ta_reason}")
                        _log_tick(action_taken="hold", btc_price=current_price,
                                  decision_score=score, decision_action=action,
                                  decision_confidence=confidence,
                                  reason_no_trade="trend_alignment_blocked",
                                  reason_detail=ta_reason[:500])
                        return PaperTickResult(
                            action_taken="hold",
                            detail=ta_reason,
                            current_price=current_price,
                            timestamp=now.isoformat(),
                            decision_score=score,
                            decision_action=action,
                            profile_type=profile_name,
                            non_trade_reason="trend_alignment_blocked",
                        )

            # [v1.6.2] Scalping bidirectionnel — mean reversion
            # En scalping, on ne suit pas aveuglément la tendance. Quand les
            # oscillateurs (RSI, StochRSI) montrent un surachat/survente extrême,
            # on ouvre une position contrariante pour capter le pullback.
            # Cela permet d'ouvrir des SHORT même en tendance haussière.
            # [v2.0.10] Le reversal reçoit maintenant mq_data pour exploiter le micro_trend.
            # [v2.0.14] Le reversal est SKIPPÉ quand l'override est actif (la bougie prime).
            scalping_reversal = False
            if not tm_override_active and profile_params and profile_params.loss_cut_pct <= 0.5:
                reversal_dir = self._scalping_reversal_check(decision_result, mq_data=mq_data)
                if reversal_dir:
                    new_action = "acheter" if reversal_dir == "long" else "vendre"
                    if new_action != action:
                        logger.info(
                            f"⚡ Scalping mean reversion: {action}→{new_action} "
                            f"(reversal → {reversal_dir}, score={score})"
                        )
                        action = new_action
                        scalping_reversal = True

            # [v2.0.14] Quand l'override est actif, le check "attendre" est BYPASSÉ.
            # La direction vient de la bougie, pas du score. Le score "attendre" signifie
            # juste que les indicateurs 15 min sont indécis — mais le prix bouge quand même.
            if action == "attendre" and not tm_override_active:
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

            # [v2.0.10] Market quality gate — mq_data déjà calculé plus haut (avant reversal).
            # Ici on fait juste le gating (rejet si qualité trop basse).

            # Helper pour injecter les données de qualité dans le log
            _qg_log = {}
            if mq_data:
                _qg_log = {
                    "market_quality_score": mq_data.get("market_quality_score"),
                    "volume_ratio": mq_data.get("volume_ratio"),
                    "price_position_pct": mq_data.get("price_position_pct"),
                    "range_width_atr": mq_data.get("range_width_atr"),
                    "micro_trend_score": mq_data.get("micro_trend_score"),
                    "vwap_distance_pct": mq_data.get("vwap_distance_pct"),
                }

            if mq_reason:
                _log_tick(action_taken="hold", btc_price=current_price,
                          decision_score=score, decision_action=action,
                          decision_confidence=confidence,
                          reason_no_trade="market_quality_low",
                          reason_detail=mq_reason[:500],
                          quality_gate_passed=False,
                          quality_gate_reason=mq_reason[:500],
                          **_qg_log)
                return PaperTickResult(
                    action_taken="hold",
                    detail=f"No-trade zone : {mq_reason}",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    decision_score=score,
                    decision_action=action,
                    profile_type=profile_name,
                    non_trade_reason="market_quality_low",
                )

            # [v2.0.0] Economic viability gate — refuse les trades non viables après frais.
            # Le scalping v1.9.9 produisait 87.5% de "gagnants bruts" devenus perdants nets.
            # Ce gate calcule le coût round-trip et exige une capture minimum.
            _econ_log = {}
            econ_gate_enabled = getattr(profile_params, "economic_gate_enabled", False) if profile_params else False
            if econ_gate_enabled:
                from app.services.trading_cost_service import get_cost_model
                cost_model = get_cost_model("realistic")
                # Capture attendue = trailing_stop_activation (la capture réelle, pas le TP théorique)
                expected_cap = getattr(profile_params, "expected_capture_pct", None)
                if expected_cap is None:
                    ts_act = getattr(profile_params, "trailing_stop_activation_pct", None)
                    expected_cap = ts_act if ts_act else 0.15
                min_ev_mult = getattr(profile_params, "min_ev_multiple", 2.0)
                leverage_est = 1.0  # Estimé avant le calcul réel du levier
                econ_result = cost_model.estimate_economic_viability(
                    position_size_usd=2500,  # Taille standard scalping
                    leverage=leverage_est,
                    expected_capture_pct=expected_cap,
                    min_ev_multiple=min_ev_mult,
                )
                _econ_log = {
                    "estimated_round_trip_cost": econ_result["round_trip_cost_usd"],
                    "min_capture_required_pct": econ_result["min_capture_required_pct"],
                    "economic_gate_passed": econ_result["is_viable"],
                }
                if not econ_result["is_viable"]:
                    _log_tick(action_taken="hold", btc_price=current_price,
                              decision_score=score, decision_action=action,
                              decision_confidence=confidence,
                              reason_no_trade="economic_viability_low",
                              reason_detail=econ_result["rejection_reason"][:500],
                              quality_gate_passed=True,
                              rejection_category="economic",
                              **_qg_log, **_econ_log)
                    return PaperTickResult(
                        action_taken="hold",
                        detail=f"Non viable économiquement : {econ_result['rejection_reason']}",
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        decision_score=score,
                        decision_action=action,
                        profile_type=profile_name,
                        non_trade_reason="economic_viability_low",
                    )

            # [v2.0.0] Structural proofs gate — le scalping exige des preuves structurelles.
            # Les preuves : price_position favorable (haut de range pour long), volume > 1.2x,
            # micro-trend ≥ 3. Sans assez de preuves, pas d'entrée scalping.
            # [v2.0.20] BYPASS quand tick momentum override est actif.
            # L'override confirme la direction par le prix RÉEL (30 sec), pas par les
            # indicateurs 15 min. Les structural proofs utilisent micro_trend_score (15 min
            # lagging) → en marché bearish, elles bloquent 100% des LONGs de l'override,
            # recréant le biais SHORT que l'override était censé corriger.
            # Les protections restantes (economic gate, market quality, min_score, risk engine)
            # suffisent à filtrer les mauvaises entrées sans biais directionnel.
            min_proofs = getattr(profile_params, "min_structural_proofs", 0) if profile_params else 0
            if min_proofs > 0 and mq_data and not tm_override_active:
                proof_count = 0
                proof_details = []
                # Preuve 1 : volume confirmé (ratio >= 1.0)
                vol_r = mq_data.get("volume_ratio", 0) or 0
                if vol_r >= 1.0:
                    proof_count += 1
                    proof_details.append(f"volume={vol_r:.2f}x")
                # Preuve 2 : micro-trend favorable (≥ 3 pour long, ≤ -3 pour short)
                mt = mq_data.get("micro_trend_score", 0) or 0
                direction_check = "long" if action == "acheter" else "short"
                if (direction_check == "long" and mt >= 3) or (direction_check == "short" and mt <= -3):
                    proof_count += 1
                    proof_details.append(f"micro_trend={mt:+d}")
                # Preuve 3 : price_position favorable (bas de range pour long, haut pour short)
                pp = mq_data.get("price_position_pct", 0.5) or 0.5
                if (direction_check == "long" and pp < 0.35) or (direction_check == "short" and pp > 0.65):
                    proof_count += 1
                    proof_details.append(f"price_pos={pp:.0%}")
                # Preuve 4 : range suffisant (range_width_atr >= 1.5)
                rw = mq_data.get("range_width_atr", 0) or 0
                if rw >= 1.5:
                    proof_count += 1
                    proof_details.append(f"range_atr={rw:.1f}")

                if proof_count < min_proofs:
                    detail = (
                        f"Preuves structurelles insuffisantes : {proof_count}/{min_proofs} "
                        f"({', '.join(proof_details) if proof_details else 'aucune'})"
                    )
                    _log_tick(action_taken="hold", btc_price=current_price,
                              decision_score=score, decision_action=action,
                              decision_confidence=confidence,
                              reason_no_trade="structural_proof_insufficient",
                              reason_detail=detail[:500],
                              quality_gate_passed=True,
                              rejection_category="structure",
                              **_qg_log, **_econ_log)
                    return PaperTickResult(
                        action_taken="hold",
                        detail=detail,
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        decision_score=score,
                        decision_action=action,
                        profile_type=profile_name,
                        non_trade_reason="structural_proof_insufficient",
                    )

            # [v2.0.3] Gate micro-tendance obligatoire pour les longs scalping.
            # L'audit runtime montre 91% de closed_stale = entrées sur bruit sans tendance.
            # Ce gate est un VETO : pas de micro-trend ≥ min_micro_trend_long, pas de long.
            # Distinct de la preuve structurelle (qui vérifie ≥ 3 mais n'est qu'1 preuve parmi 4).
            min_mt_long = getattr(profile_params, "min_micro_trend_long", None) if profile_params else None
            if min_mt_long is not None and min_mt_long > 0 and mq_data:
                direction_check = "long" if action == "acheter" else "short"
                if direction_check == "long":
                    mt = mq_data.get("micro_trend_score", 0) or 0
                    if mt < min_mt_long:
                        detail = (
                            f"Gate micro-tendance : micro_trend_score {mt:+d} < {min_mt_long} requis pour long"
                        )
                        _log_tick(action_taken="hold", btc_price=current_price,
                                  decision_score=score, decision_action=action,
                                  decision_confidence=confidence,
                                  reason_no_trade="micro_trend_insufficient",
                                  reason_detail=detail[:500],
                                  quality_gate_passed=True,
                                  rejection_category="structure",
                                  **_qg_log, **_econ_log)
                        return PaperTickResult(
                            action_taken="hold",
                            detail=detail,
                            current_price=current_price,
                            timestamp=now.isoformat(),
                            decision_score=score,
                            decision_action=action,
                            profile_type=profile_name,
                            non_trade_reason="micro_trend_insufficient",
                        )

            # [v2.0.10] VETO BEARISH — Bloquer les LONG quand le marché descend.
            # Les données montrent que 7/33 trades perdent -$10.44 à cause d'entrées LONG
            # pendant que le BTC descend. Le score technique de 65 est RETARDÉ (basé sur
            # des indicateurs 15min) et reste bullish pendant un pullback.
            # Ce veto vérifie le micro_trend_score TEMPS RÉEL : s'il est négatif (bearish),
            # on bloque le LONG. Les reversals (shorts contrarians) ne sont PAS bloqués.
            # [v2.0.14] SKIPPÉ quand tick momentum override est actif — la bougie EST la
            # confirmation de direction, le micro_trend 15 min n'est plus pertinent.
            if mq_data and not scalping_reversal and not tm_override_active:
                direction_check = "long" if action == "acheter" else "short"
                mt = mq_data.get("micro_trend_score", 0) or 0
                if direction_check == "long" and mt < 0:
                    detail = (
                        f"Veto bearish : micro_trend_score {mt:+d} < 0, "
                        f"marché en baisse → LONG bloqué (score technique {score} en retard)"
                    )
                    _log_tick(action_taken="hold", btc_price=current_price,
                              decision_score=score, decision_action=action,
                              decision_confidence=confidence,
                              reason_no_trade="bearish_veto",
                              reason_detail=detail[:500],
                              quality_gate_passed=True,
                              rejection_category="structure",
                              **_qg_log, **_econ_log)
                    return PaperTickResult(
                        action_taken="hold",
                        detail=detail,
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        decision_score=score,
                        decision_action=action,
                        profile_type=profile_name,
                        non_trade_reason="bearish_veto",
                    )

            # [v2.0.13] TICK MOMENTUM CONFIRMATION — Gate d'entrée par micro price-action.
            # [v2.0.14] SKIPPÉ quand override est actif (la direction est déjà confirmée).
            # En mode non-override (profils classiques), ce gate vérifie que le prix va
            # dans la direction du trade AVANT d'ouvrir.
            if tm_enabled and not tm_override_active:
                tm_window = getattr(profile_params, "tick_momentum_window_seconds", 10.0)
                tm_min_ticks = getattr(profile_params, "tick_momentum_min_ticks", 2)
                trade_direction = "long" if action == "acheter" else "short"

                tm_confirmed, tm_result = TickMomentumService.check_direction(
                    slot=slot_name,
                    direction=trade_direction,
                    window_seconds=tm_window,
                    min_ticks=tm_min_ticks,
                )

                if not tm_confirmed:
                    detail = (
                        f"Tick momentum non confirmé ({trade_direction}) : {tm_result.detail}"
                    )
                    _log_tick(action_taken="hold", btc_price=current_price,
                              decision_score=score, decision_action=action,
                              decision_confidence=confidence,
                              reason_no_trade="tick_momentum_mismatch",
                              reason_detail=detail[:500],
                              quality_gate_passed=True,
                              rejection_category="momentum",
                              **_qg_log, **_econ_log)
                    return PaperTickResult(
                        action_taken="hold",
                        detail=detail,
                        current_price=current_price,
                        timestamp=now.isoformat(),
                        decision_score=score,
                        decision_action=action,
                        profile_type=profile_name,
                        non_trade_reason="tick_momentum_mismatch",
                    )

            # [v1.5] Vérification profil — score minimum
            # Les trades de reversal (mean reversion) ne sont pas soumis au
            # seuil de score car leur signal vient des oscillateurs, pas du score.
            # [v2.0.14] Quand tick momentum override est actif, on utilise un seuil
            # réduit car le score n'est qu'un filtre de qualité (le marché est-il actif ?).
            # La direction vient de la bougie, pas du score.
            if tm_override_active:
                min_score = getattr(profile_params, "tick_momentum_min_score", 10) if profile_params else 10
            else:
                min_score = profile_params.min_score if profile_params else 35
            if abs(score) < min_score and not scalping_reversal:
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
            # [v1.7] En multi-slot, cooldown par slot
            cooldown_slot = slot_name if is_multi else None
            cooldown_reason = self._check_cooldown(
                account.id, cooldown_min, slot=cooldown_slot,
                profile_params=profile_params, signal_score=abs(score),
            )
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
            # [v1.7] En multi-slot, compteur par slot
            max_slot = slot_name if is_multi else None
            max_check = self._check_max_trades_per_day(account.id, max_tpd, slot=max_slot)
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
            if scalping_reversal:
                reason = f"mean_reversion_{direction} | score={score} | {confidence} | {summary[:100]}"
            elif tm_override_active:
                # [v2.0.19] Les trades ouverts via tick momentum override utilisent un
                # préfixe spécifique pour bénéficier de la protection anti-churn dans
                # la logique de signal contraire (même protection que mean_reversion).
                # Sans cela, un override SHORT à score=66 est immédiatement fermé par
                # le signal contraire car score=66 > short_exit_th=30.
                reason = f"tick_override_{direction} | score={score} | {confidence} | {summary[:100]}"
            else:
                reason = f"{action} | score={score} | {confidence} | {summary[:100]}"

            # SL/TP par défaut du risk engine — direction-aware
            # [v1.6.2] Les fallbacks sont maintenant adaptés à la direction.
            # Avant, les shorts recevaient des SL/TP de long (bug critique).
            if direction == "long":
                sl_price = evaluation.stop_loss_price or current_price * 0.95
                tp_price = evaluation.take_profit_price or current_price * 1.10
            else:  # short
                sl_price = evaluation.stop_loss_price or current_price * 1.05
                tp_price = evaluation.take_profit_price or current_price * 0.90

            # [v1.6.1] Profil tight (scalping) : override SL/TP avec les %
            # du profil si ceux-ci sont plus serrés que le risk engine.
            # Cela garantit des sorties rapides adaptées au scalping.
            if profile_params and profile_params.loss_cut_pct <= 0.5:
                lc = profile_params.loss_cut_pct / 100
                pt = profile_params.profit_take_pct / 100
                if direction == "long":
                    profile_sl = current_price * (1 - lc)
                    profile_tp = current_price * (1 + pt)
                    sl_price = max(sl_price, profile_sl)  # SL plus proche = plus haut pour long
                    tp_price = min(tp_price, profile_tp)  # TP plus proche = plus bas pour long
                else:  # short
                    profile_sl = current_price * (1 + lc)
                    profile_tp = current_price * (1 - pt)
                    sl_price = min(sl_price, profile_sl)  # SL plus proche = plus bas pour short
                    tp_price = max(tp_price, profile_tp)  # TP plus proche = plus haut pour short
                logger.info(
                    f"🎯 Profil tight → SL/TP ajustés : "
                    f"SL={sl_price:.2f} TP={tp_price:.2f} "
                    f"(loss_cut={profile_params.loss_cut_pct}%, profit_take={profile_params.profit_take_pct}%)"
                )

            # [v2.0.15] Déterminer la couleur de la bougie à l'entrée.
            # Source 1 : tick momentum override (la plus fiable en scalping)
            # Source 2 : micro_trend_score du market quality (proxy pour tous profils)
            # Source 3 : fallback basé sur la direction du trade (toujours disponible)
            # On garantit TOUJOURS une valeur pour l'affichage frontend de la pastille.
            entry_candle_dir = None
            if tm_override_active:
                # Le tick momentum a déterminé la direction → la bougie est claire
                entry_candle_dir = "green" if direction == "long" else "red"
            elif mq_data:
                mt = mq_data.get("micro_trend_score", 0) or 0
                if mt > 0:
                    entry_candle_dir = "green"
                elif mt < 0:
                    entry_candle_dir = "red"

            # [v2.0.15-fix] Fallback final : si aucune source n'a pu déterminer
            # la couleur (ex: buffer vide après restart, micro_trend=0), on déduit
            # la couleur de la direction du trade. C'est cohérent car le système
            # n'ouvre un long que s'il détecte une tendance haussière, et inversement.
            if entry_candle_dir is None:
                entry_candle_dir = "green" if direction == "long" else "red"

            # [v2.0.22] SAS D'ENTRÉE SÉCURISÉ — Observer avant d'ouvrir.
            # Si le SAS est activé pour ce profil, on crée une entrée VIRTUELLE
            # au lieu d'ouvrir directement. L'entrée réelle sera confirmée ou
            # annulée aux ticks suivants après observation du PnL virtuel.
            sas_enabled = getattr(profile_params, "entry_sas_enabled", False) if profile_params else False
            if sas_enabled:
                sas_dur = getattr(profile_params, "entry_sas_duration_seconds", 15.0)
                sas_min_pos = getattr(profile_params, "entry_sas_min_positive_seconds", 10.0)
                sas_range = getattr(profile_params, "entry_sas_range_caution", True)
                pp_pct = mq_data.get("price_position_pct", 0.5) if mq_data else 0.5

                EntrySasService.create_pending(
                    slot=slot_name,
                    direction=direction,
                    virtual_entry_price=current_price,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    position_size_usd=evaluation.max_position_size_usd or 1000.0,
                    reason=reason,
                    score=score,
                    leverage=leverage_final,
                    leverage_reason=leverage_reasons,
                    profile_type=profile_name,
                    entry_candle_direction=entry_candle_dir,
                    price_position_pct=pp_pct,
                    max_duration_seconds=sas_dur,
                    min_positive_seconds=sas_min_pos,
                    range_caution=sas_range,
                    now=now,
                )

                _log_tick(action_taken="hold", btc_price=current_price,
                          decision_score=score, decision_action=action,
                          decision_confidence=confidence,
                          reason_no_trade="sas_pending",
                          reason_detail=f"SAS créé : {direction} virtuel @ {current_price:.2f}, observation {sas_dur}s",
                          **_qg_log)
                return PaperTickResult(
                    action_taken="hold",
                    detail=(
                        f"🚪 SAS d'entrée créé : {direction.upper()} virtuel @ {current_price:.2f} "
                        f"| Observation {sas_dur}s, besoin {sas_min_pos}s positif "
                        f"| range_pos={pp_pct:.0%}"
                    ),
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    decision_score=score,
                    decision_action=action,
                    profile_type=profile_name,
                    non_trade_reason="sas_pending",
                )

            position = self._open_position(
                account=account,
                price=current_price,
                sl=sl_price,
                tp=tp_price,
                size_usd=evaluation.max_position_size_usd or 1000.0,
                reason=reason,
                score=score,
                direction=direction,
                now=now,
                leverage=leverage_final,
                leverage_reason=leverage_reasons,
                profile_type=profile_name,
                slot=slot_name if is_multi else None,
                entry_candle_direction=entry_candle_dir,
            )

            # [v1.9.6] Si _open_position retourne None, le slot est déjà occupé
            # (race condition évitée par le guard anti-double ouverture).
            if position is None:
                _log_tick(action_taken="hold", btc_price=current_price,
                          decision_score=score, decision_action=action,
                          reason_no_trade="slot_already_occupied",
                          reason_detail=f"Slot '{slot_name}' déjà occupé (anti-double)")
                return PaperTickResult(
                    action_taken="hold",
                    detail=f"Slot '{slot_name}' déjà occupé (anti-double ouverture).",
                    current_price=current_price,
                    timestamp=now.isoformat(),
                    decision_score=score,
                    decision_action=action,
                    profile_type=profile_name,
                    non_trade_reason="slot_already_occupied",
                )

            _log_tick(action_taken=f"opened_{direction}", btc_price=current_price,
                      decision_score=score, decision_action=action,
                      decision_confidence=confidence,
                      leverage_recommended=leverage_recommended,
                      leverage_final=leverage_final,
                      leverage_reason=leverage_reasons,
                      trade_id=position.id,
                      quality_gate_passed=True,
                      quality_gate_reason="market_quality_ok",
                      **_qg_log)

            return PaperTickResult(
                action_taken=f"opened_{direction}",
                detail=f"Position {direction} ouverte @ {current_price:.2f} | SL={sl_price:.2f} | TP={tp_price:.2f} | Levier x{leverage_final}",
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
        slot: Optional[str] = None,
        entry_candle_direction: Optional[str] = None,
    ) -> Optional[PaperTrade]:
        """
        Ouvre une position paper.

        [v1.9.6] Guard anti-double ouverture :
        Avant d'insérer, re-vérifie qu'aucune position ouverte n'existe
        déjà sur ce slot. Cela corrige la race condition TOCTOU où deux
        ticks concurrents passaient la vérification dans _tick_single_slot()
        avant que l'un n'ait committé sa position.
        Retourne None si le slot est déjà occupé.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # [v1.9.6] INVARIANT CRITIQUE : 1 slot = 1 position ouverte max.
        # Double-check atomique juste avant l'INSERT pour fermer la fenêtre
        # de race condition entre le check dans _tick_single_slot() et ici.
        if slot is not None:
            existing = (
                self.db.query(PaperTrade)
                .filter(
                    PaperTrade.account_id == account.id,
                    PaperTrade.status == "open",
                    PaperTrade.slot == slot,
                )
                .first()
            )
            if existing is not None:
                logger.warning(
                    f"⚠️ INVARIANT SLOT : position ouverte #{existing.id} déjà présente "
                    f"sur slot '{slot}'. Ouverture refusée (anti-double)."
                )
                return None

        # [v1.7] En multi-slot, limiter le capital par slot
        max_pos = getattr(account, "max_open_positions", 1) or 1
        if max_pos > 1:
            capital_per_slot = self._capital_for_slot(account, max_pos)
            size_usd = min(size_usd, capital_per_slot)

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
            slot=slot,
            entry_candle_direction=entry_candle_direction,
            entry_reason=reason[:500],
            decision_score=score,
            entry_ts=now,
        )
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)

        # [v2.0.18] Reset le tracker de reversal pour ce slot (fresh start)
        TickMomentumService.reset_reversal(slot or "default")

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

        # [v2.0.16] Déterminer la direction de la bougie à la sortie.
        # Source 1 : tick momentum buffer (précis pour scalping)
        # Source 2 : comparaison exit_price vs entry_price (fallback universel)
        exit_candle_dir = None
        try:
            slot = getattr(trade, "slot", None) or "default"
            tm_dir, _ = TickMomentumService.detect_direction(
                slot=slot, window_seconds=15.0, min_ticks=2
            )
            if tm_dir == "long":
                exit_candle_dir = "green"
            elif tm_dir == "short":
                exit_candle_dir = "red"
        except Exception:
            pass  # Non-bloquant

        # Fallback : comparer le prix de sortie à l'entry
        if exit_candle_dir is None:
            if exit_price > trade.entry_price:
                exit_candle_dir = "green"
            elif exit_price < trade.entry_price:
                exit_candle_dir = "red"
            else:
                exit_candle_dir = "green"  # flat → neutre, on garde green par défaut

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
        trade.exit_candle_direction = exit_candle_dir  # v2.0.16

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

        # [v1.9] Enregistrer un échantillon d'apprentissage (best-effort)
        try:
            from app.services.learning_service import LearningService
            learning = LearningService(self.db)
            learning.record_sample(trade)
        except Exception as e:
            logger.debug(f"Learning sample recording error (non-blocking): {e}")

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

    def _check_market_quality(
        self,
        decision_result: dict,
        direction: str,
        min_quality: int = 30,
        min_volume_ratio: float = 0.0,
        long_quality_filter: bool = False,
    ) -> tuple[Optional[str], Optional[dict]]:
        """
        [v1.9.9] Vérifie la qualité de marché avant ouverture (no-trade zone).

        Utilise le MarketStructureService pour évaluer si le marché a
        assez de structure pour justifier un trade.

        Returns:
            (reason_if_rejected, quality_data_dict)
            reason est None si OK. quality_data est toujours renseigné si possible.
        """
        try:
            from app.services.market_structure_service import MarketStructureService

            # Récupérer la série depuis le decision_result
            series = decision_result.get("_series")
            if not series or len(series) < 5:
                return None, None  # Pas assez de données, ne pas bloquer

            quality = MarketStructureService.assess_quality(series)

            # Données de qualité pour le log (toujours renseignées)
            qdata = {
                "market_quality_score": quality.quality_score,
                "volume_ratio": quality.volume_ratio,
                "price_position_pct": quality.price_position_pct,
                "range_width_atr": quality.range_width_atr,
                "micro_trend_score": quality.micro_trend_score,
                "vwap_distance_pct": quality.vwap_distance_pct,
            }

            # Vérification 1 : No-trade zone globale
            if MarketStructureService.is_no_trade_zone(quality, min_quality):
                reason = (
                    f"Qualité marché {quality.quality_score}/100 < seuil {min_quality} — "
                    f"{'; '.join(quality.reasons[:2])}"
                )
                return reason, qdata

            # Vérification 2 : Filtre spécifique longs
            if direction == "long" and long_quality_filter:
                is_ok, reason = MarketStructureService.is_long_quality_sufficient(
                    quality,
                    min_quality=min_quality + 5,  # Exigence plus haute pour les longs
                    min_volume_ratio=min_volume_ratio,
                )
                if not is_ok:
                    return reason, qdata

            # Vérification 3 : Volume minimum général
            if min_volume_ratio > 0 and quality.volume_ratio < min_volume_ratio:
                reason = (
                    f"Volume insuffisant ({quality.volume_ratio:.2f}x < {min_volume_ratio}x SMA20)"
                )
                return reason, qdata

            return None, qdata  # Marché OK

        except Exception as e:
            logger.debug(f"Market quality check error (non-blocking): {e}")
            return None, None  # En cas d'erreur, ne pas bloquer le trade

    def _scalping_reversal_check(self, decision_result: dict, mq_data: dict = None) -> Optional[str]:
        """
        Vérifie si les conditions justifient une position contrariante (mean reversion).

        En scalping, quand le marché oscille dans un range, on veut alterner
        long/short pour capter chaque micro-mouvement. Le reversal détecte les
        points de retournement via plusieurs signaux :

        [v2.0.8] REFONTE — Le seuil de 2 signaux (v1.9.4) bloquait 100% des shorts.
        En marché range, RSI reste à 55 (jamais overbought) et StochRSI aussi.
        Résultat : 0 short en 24h, le robot ne trade que dans un sens.

        Nouveaux signaux ajoutés pour détecter les retournements en range :
        - Majorité bearish dans les règles satisfaites (plus de baissiers que haussiers)
        - Score négatif du moteur de décision (le marché penche vers le baissier)
        - [v2.0.10] Micro-tendance baissière (micro_trend ≤ -2) → signal SHORT

        Seuil abaissé à 1 signal. Les sorties (trailing, breakeven, stale 2min)
        protègent suffisamment contre les faux signaux. Un mauvais short sort
        en ~30sec-2min avec une perte de $0-1 max.

        Returns:
            "short" si retournement baissier détecté
            "long" si retournement haussier détecté
            None si pas de signal de reversal
        """
        rules = decision_result.get("rules_evaluated", [])

        # Source 1 : Règles overbought/oversold (RSI/StochRSI en zone extrême)
        overbought_signals = {"rsi_overbought", "stochrsi_overbought"}
        oversold_signals = {"rsi_oversold", "stochrsi_oversold"}

        overbought = 0
        oversold = 0
        for r in rules:
            if not r.get("satisfied"):
                continue
            name = r.get("rule_name", "")
            if name in overbought_signals:
                overbought += 1
            elif name in oversold_signals:
                oversold += 1

        # Source 2 : Score technique extrême (≥95 ou ≤-95)
        score = decision_result.get("combined_score", 0)
        tech_score = decision_result.get("technical_score", score)

        bullish_rules = sum(1 for r in rules if r.get("satisfied") and r.get("direction") == "bullish")
        bearish_rules = sum(1 for r in rules if r.get("satisfied") and r.get("direction") == "bearish")

        if tech_score >= 95 and bearish_rules == 0:
            overbought += 1
            logger.debug(f"⚡ Scalping reversal: tech_score={tech_score} → overbought signal")
        elif tech_score <= -95 and bullish_rules == 0:
            oversold += 1
            logger.debug(f"⚡ Scalping reversal: tech_score={tech_score} → oversold signal")

        # [v2.0.8] Source 3 : Majorité bearish/bullish dans les règles
        # Si plus de règles bearish que bullish sont satisfaites, le momentum
        # penche vers le bas → signal overbought (un pullback baissier est probable).
        # Cela permet de détecter les retournements en range même quand RSI est à 55.
        if bearish_rules > bullish_rules and bearish_rules >= 2:
            overbought += 1
            logger.debug(
                f"⚡ Scalping reversal: majorité bearish ({bearish_rules}b vs {bullish_rules}h) → overbought signal"
            )
        elif bullish_rules > bearish_rules and bullish_rules >= 2:
            oversold += 1
            logger.debug(
                f"⚡ Scalping reversal: majorité bullish ({bullish_rules}h vs {bearish_rules}b) → oversold signal"
            )

        # [v2.0.10] Source 4 : Micro-tendance temps réel
        # Quand le micro_trend_score ≤ -2, le marché est objectivement baissier
        # sur les dernières candles → signal overbought → favorise un SHORT.
        # Symétrique : micro_trend ≥ 3 → oversold → favorise un LONG.
        if mq_data:
            mt = mq_data.get("micro_trend_score", 0) or 0
            if mt <= -2:
                overbought += 1
                logger.debug(
                    f"⚡ Scalping reversal: micro_trend={mt} ≤ -2 → overbought signal (bearish trend)"
                )
            elif mt >= 3:
                oversold += 1
                logger.debug(
                    f"⚡ Scalping reversal: micro_trend={mt} ≥ 3 → oversold signal (bullish trend)"
                )

        # [v2.0.8] Seuil abaissé de 2 à 1 signal.
        # Les sorties (trailing stop, breakeven stop, stale 2min) protègent
        # contre les faux signaux. Un mauvais short est coupé très vite.
        if overbought >= 1:
            return "short"
        if oversold >= 1:
            return "long"
        return None

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

    def _check_expiration(self, trade: PaperTrade, now: datetime,
                          profile_max_hours: Optional[float] = None) -> Optional[str]:
        """Vérifie si la position a dépassé la durée max.

        Utilise le minimum entre la durée du compte et celle du profil actif.
        Pour scalping (profil 2h) vs compte (168h), cela garantit l'expiration rapide.
        """
        account = self.db.query(PaperAccount).get(trade.account_id)
        if account is None:
            return None
        max_hours = account.max_open_duration_hours
        # [v1.6.1] Utiliser la durée du profil si plus courte
        if profile_max_hours is not None and profile_max_hours > 0:
            max_hours = min(max_hours, profile_max_hours)
        entry_ts = _ensure_aware(trade.entry_ts)
        elapsed = (now - entry_ts).total_seconds() / 3600
        if elapsed >= max_hours:
            return "closed_expired"
        return None

    # ================================================================
    # [v1.5] CONTRÔLES DE FRÉQUENCE
    # ================================================================

    def _check_cooldown(self, account_id: int, cooldown_minutes: int,
                        slot: Optional[str] = None,
                        profile_params=None,
                        signal_score: Optional[float] = None) -> Optional[str]:
        """
        Vérifie le cooldown entre deux trades. Retourne raison si bloqué.

        [v1.7] En mode multi-slot, le cooldown est vérifié PAR SLOT.
        [v1.9] Si smart_cooldown_enabled, le cooldown est dynamique et contextuel.
        """
        if cooldown_minutes <= 0:
            return None
        query = (
            self.db.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account_id,
                PaperTrade.status != "open",
            )
        )
        # [v1.7] Filtrer par slot si spécifié
        if slot is not None:
            query = query.filter(PaperTrade.slot == slot)
        last_trade = query.order_by(PaperTrade.exit_ts.desc()).first()
        if last_trade and last_trade.exit_ts:
            exit_ts = _ensure_aware(last_trade.exit_ts)
            elapsed = (datetime.now(timezone.utc) - exit_ts).total_seconds() / 60

            # [v1.9] Smart cooldown : calcul dynamique basé sur le contexte
            effective_cooldown = cooldown_minutes
            smart_enabled = (
                profile_params is not None
                and getattr(profile_params, "smart_cooldown_enabled", False)
            )
            if smart_enabled:
                from app.services.smart_cooldown_service import SmartCooldownService
                min_cd = getattr(profile_params, "min_cooldown_minutes", None) or 0.5
                max_cd = getattr(profile_params, "max_cooldown_minutes", None) or 10.0
                # Calculer la durée du dernier trade en minutes
                last_duration_min = None
                if last_trade.duration_hours is not None:
                    last_duration_min = last_trade.duration_hours * 60
                effective_cooldown = SmartCooldownService.compute_cooldown(
                    base_cooldown=cooldown_minutes,
                    last_exit_type=last_trade.status,
                    last_pnl=last_trade.pnl,
                    last_pnl_pct=last_trade.pnl_pct,
                    last_duration_min=last_duration_min,
                    signal_score=signal_score,
                    min_cooldown=min_cd,
                    max_cooldown=max_cd,
                )

            if elapsed < effective_cooldown:
                remaining = round(effective_cooldown - elapsed, 1)
                if smart_enabled and effective_cooldown != cooldown_minutes:
                    return (
                        f"Smart cooldown : {remaining} min restantes "
                        f"(dynamique {effective_cooldown:.1f} min, base={cooldown_minutes} min)"
                    )
                return f"Cooldown : {remaining} min restantes (profil exige {cooldown_minutes} min)"
        return None

    def _check_max_trades_per_day(self, account_id: int, max_trades: int, slot: Optional[str] = None) -> Optional[str]:
        """
        Vérifie le nombre max de trades par jour. Retourne raison si atteint.

        [v1.7] En mode multi-slot, le compteur est PAR SLOT.
        Chaque slot a son propre quota de trades/jour.
        """
        if max_trades <= 0:
            return None
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        query = (
            self.db.query(func.count(PaperTrade.id))
            .filter(
                PaperTrade.account_id == account_id,
                PaperTrade.entry_ts >= today_start,
            )
        )
        # [v1.7] Filtrer par slot si spécifié
        if slot is not None:
            query = query.filter(PaperTrade.slot == slot)
        count = query.scalar() or 0
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
        open_positions = self.get_open_positions()
        open_pos = open_positions[0] if open_positions else None
        metrics = self.get_metrics()

        current_price = self._get_current_price()
        # Calcul PnL non réalisé total (toutes positions ouvertes)
        total_unrealized = None
        if open_positions and current_price:
            total_unrealized = sum(
                self._calc_unrealized_pnl(pos, current_price)
                for pos in open_positions
            )

        account_resp = PaperAccountResponse.model_validate(account)
        # Rétrocompat : open_position = première position
        if open_pos:
            account_resp.open_position = PaperTradeResponse.model_validate(open_pos)
        # [v1.7] Toutes les positions ouvertes
        account_resp.open_positions = [
            PaperTradeResponse.model_validate(p) for p in open_positions
        ]

        open_resp = PaperTradeResponse.model_validate(open_pos) if open_pos else None
        open_resps = [PaperTradeResponse.model_validate(p) for p in open_positions]

        return PaperStatus(
            account=account_resp,
            open_position=open_resp,
            open_positions=open_resps,
            metrics=metrics,
            is_running=account.is_active,
            current_btc_price=current_price,
            unrealized_pnl=round(total_unrealized, 2) if total_unrealized is not None else None,
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

    def export_trades(self) -> dict:
        """
        Export complet du journal de trading.

        Retourne toutes les données nécessaires pour analyser le trading :
        - Résumé du compte (capital, PnL, profil, dates)
        - Métriques de performance
        - Toutes les positions ouvertes (avec PnL latent)
        - Tous les trades fermés (avec détails complets)

        Conçu pour être analysé par un humain ou un LLM (ChatGPT, Claude, etc.).
        """
        from app.schemas.paper_trading import (
            PaperTradeExportItem,
            PaperExportAccountSummary,
            PaperExportResponse,
        )

        account = self.get_or_create_account()
        metrics = self.get_metrics()
        current_price = self._get_current_price()

        # Toutes les positions ouvertes
        open_positions = self.get_open_positions()
        open_items = [
            PaperTradeExportItem.model_validate(t) for t in open_positions
        ]

        # Tous les trades fermés — sans limite de pagination
        closed_trades = (
            self.db.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account.id,
                PaperTrade.status != "open",
            )
            .order_by(PaperTrade.exit_ts.desc())
            .all()
        )
        closed_items = [
            PaperTradeExportItem.model_validate(t) for t in closed_trades
        ]

        account_summary = PaperExportAccountSummary(
            initial_capital=account.initial_capital,
            current_capital=account.current_capital,
            total_pnl=account.total_pnl,
            total_pnl_pct=account.total_pnl_pct,
            peak_capital=account.peak_capital,
            max_drawdown_pct=account.max_drawdown_pct,
            btc_price_at_start=account.btc_price_at_start,
            active_profile=account.active_profile or "conservative",
            max_open_positions=account.max_open_positions or 1,
            created_at=account.created_at,
        )

        return PaperExportResponse(
            exported_at=datetime.now(timezone.utc),
            account=account_summary,
            metrics=metrics,
            current_btc_price=current_price,
            total_trades=len(open_positions) + len(closed_trades),
            open_trades=open_items,
            closed_trades=closed_items,
        )

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

    def _get_decision(self, timeframe: str = "4h", history_days: float = 7,
                       buy_threshold: int = None, sell_threshold: int = None) -> Optional[dict]:
        """Appelle le DecisionService pour obtenir la recommandation."""
        try:
            service = DecisionService(self.db)
            return service.analyze(
                symbol="BTC/USD",
                timeframe=timeframe,
                history_days=history_days,
                buy_threshold=buy_threshold,
                sell_threshold=sell_threshold,
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

    def _calc_unrealized_pnl_at_price(self, trade: PaperTrade, price: float) -> float:
        """Calcule le PnL non réalisé à un prix donné (pour estimer le pic de PnL)."""
        leverage = getattr(trade, "leverage", None) or 1.0
        if trade.direction == "long":
            pnl_pct = (price - trade.entry_price) / trade.entry_price
        else:
            pnl_pct = (trade.entry_price - price) / trade.entry_price
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

