"""
Service de modélisation des coûts de trading.

Ce module modélise les coûts réels (frais, spread, slippage) pour permettre
des métriques brut/net honnêtes. C'est LE composant critique manquant avant v2.0.

Pourquoi c'est important :
- Sans ce modèle, toutes les métriques (PnL, expectancy, profit factor) sont
  structurellement trop optimistes.
- En scalping (50 trades/jour × 0.3% TP), les frais totaux (0.1% × 2 = 0.2%
  par round-trip) peuvent consommer 66% du gain brut.
- Avec le levier, les coûts sont amplifiés proportionnellement.

Le modèle est additif : il calcule les coûts sans modifier les trades existants.
Les métriques existantes restent "brutes", les nouvelles ajoutent le "net".
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TradingCostModel:
    """
    Modèle de coûts de trading.

    Tous les paramètres sont en pourcentage (ex: 0.1 = 0.1%).
    Le coût total d'un round-trip (entrée + sortie) est :
        total_cost = (maker_fee + taker_fee + spread + slippage) × 2 directions
    En pratique, on applique les coûts séparément à l'entrée et à la sortie.
    """
    # Frais exchange (en % du montant)
    maker_fee_pct: float = 0.10   # Frais maker (limit order)
    taker_fee_pct: float = 0.10   # Frais taker (market order)
    # Spread estimé (en % du prix)
    spread_pct: float = 0.05      # Bid-ask spread moyen
    # Slippage estimé (en % du prix)
    slippage_pct: float = 0.03    # Écart entre prix demandé et exécuté
    # Nom du preset (pour la traçabilité)
    name: str = "custom"

    def entry_cost_pct(self) -> float:
        """Coût total à l'entrée (en % de la taille de position)."""
        # À l'entrée, on paie le taker fee (market order typique) + demi-spread + slippage
        return self.taker_fee_pct + (self.spread_pct / 2) + self.slippage_pct

    def exit_cost_pct(self) -> float:
        """Coût total à la sortie (en % de la taille de position)."""
        # À la sortie, on paie le maker fee (limit order typique) + demi-spread + slippage
        return self.maker_fee_pct + (self.spread_pct / 2) + self.slippage_pct

    def round_trip_cost_pct(self) -> float:
        """Coût total d'un aller-retour (en % de la taille de position)."""
        return self.entry_cost_pct() + self.exit_cost_pct()

    def round_trip_cost_usd(self, position_size_usd: float) -> float:
        """Coût total d'un aller-retour en USD."""
        return position_size_usd * self.round_trip_cost_pct() / 100

    def apply_to_pnl(self, gross_pnl: float, position_size_usd: float,
                      leverage: float = 1.0) -> dict:
        """
        Applique les coûts à un PnL brut.

        Le levier amplifie la taille effective mais les coûts sont calculés
        sur la taille effective (position_size × leverage), ce qui est le
        comportement réel sur un exchange.

        Returns:
            dict avec gross_pnl, total_costs, net_pnl, cost_drag_pct
        """
        effective_size = position_size_usd * leverage
        total_costs = self.round_trip_cost_usd(effective_size)
        net_pnl = gross_pnl - total_costs
        cost_drag_pct = (total_costs / position_size_usd * 100) if position_size_usd > 0 else 0

        return {
            "gross_pnl": round(gross_pnl, 4),
            "total_costs": round(total_costs, 4),
            "net_pnl": round(net_pnl, 4),
            "cost_drag_pct": round(cost_drag_pct, 4),
        }

    def apply_to_trades(self, trades: list[dict]) -> dict:
        """
        Applique les coûts à une liste de trades et retourne les métriques agrégées.

        Chaque trade doit avoir au minimum :
        - pnl (float) : PnL brut en USD
        - position_size_usd (float) : taille de la position
        - leverage (float, optionnel) : levier (default 1.0)

        Returns:
            dict avec les métriques brut/net complètes
        """
        if not trades:
            return {
                "total_trades": 0,
                "gross_pnl": 0,
                "total_costs": 0,
                "net_pnl": 0,
                "cost_drag_pct": 0,
                "gross_expectancy": 0,
                "net_expectancy": 0,
                "gross_profit_factor": 0,
                "net_profit_factor": 0,
                "gross_avg_trade": 0,
                "net_avg_trade": 0,
                "gross_win_rate": 0,
                "net_win_rate": 0,
                "cost_model": self.name,
            }

        total_gross_pnl = 0
        total_costs = 0
        total_net_pnl = 0
        gross_wins = 0
        gross_losses = 0
        net_wins = 0
        net_losses = 0
        gross_win_sum = 0
        gross_loss_sum = 0
        net_win_sum = 0
        net_loss_sum = 0

        for trade in trades:
            pnl = trade.get("pnl", 0) or 0
            size = trade.get("position_size_usd", 0) or 0
            lev = trade.get("leverage", 1.0) or 1.0

            result = self.apply_to_pnl(pnl, size, lev)
            total_gross_pnl += result["gross_pnl"]
            total_costs += result["total_costs"]
            total_net_pnl += result["net_pnl"]

            # Brut
            if pnl >= 0:
                gross_wins += 1
                gross_win_sum += pnl
            else:
                gross_losses += 1
                gross_loss_sum += abs(pnl)

            # Net
            if result["net_pnl"] >= 0:
                net_wins += 1
                net_win_sum += result["net_pnl"]
            else:
                net_losses += 1
                net_loss_sum += abs(result["net_pnl"])

        n = len(trades)
        gross_wr = gross_wins / n * 100 if n > 0 else 0
        net_wr = net_wins / n * 100 if n > 0 else 0

        # Expectancy = avg_win × win_rate - avg_loss × loss_rate
        avg_gross_win = gross_win_sum / gross_wins if gross_wins > 0 else 0
        avg_gross_loss = gross_loss_sum / gross_losses if gross_losses > 0 else 0
        gross_exp = (avg_gross_win * gross_wins / n) - (avg_gross_loss * gross_losses / n) if n > 0 else 0

        avg_net_win = net_win_sum / net_wins if net_wins > 0 else 0
        avg_net_loss = net_loss_sum / net_losses if net_losses > 0 else 0
        net_exp = (avg_net_win * net_wins / n) - (avg_net_loss * net_losses / n) if n > 0 else 0

        # Profit factor
        gross_pf = gross_win_sum / gross_loss_sum if gross_loss_sum > 0 else (
            999.0 if gross_win_sum > 0 else 0)
        net_pf = net_win_sum / net_loss_sum if net_loss_sum > 0 else (
            999.0 if net_win_sum > 0 else 0)

        total_size = sum((t.get("position_size_usd", 0) or 0) for t in trades)
        cost_drag = (total_costs / total_size * 100) if total_size > 0 else 0

        return {
            "total_trades": n,
            "gross_pnl": round(total_gross_pnl, 2),
            "total_costs": round(total_costs, 2),
            "net_pnl": round(total_net_pnl, 2),
            "cost_drag_pct": round(cost_drag, 4),
            "gross_expectancy": round(gross_exp, 4),
            "net_expectancy": round(net_exp, 4),
            "gross_profit_factor": round(gross_pf, 2),
            "net_profit_factor": round(net_pf, 2),
            "gross_avg_trade": round(total_gross_pnl / n, 4) if n > 0 else 0,
            "net_avg_trade": round(total_net_pnl / n, 4) if n > 0 else 0,
            "gross_win_rate": round(gross_wr, 2),
            "net_win_rate": round(net_wr, 2),
            "cost_model": self.name,
        }

    def estimate_economic_viability(
        self,
        position_size_usd: float,
        leverage: float = 1.0,
        expected_capture_pct: float = 0.0,
        min_ev_multiple: float = 2.0,
    ) -> dict:
        """
        Évalue la viabilité économique d'un trade AVANT ouverture.

        Le trade doit pouvoir capturer au moins min_ev_multiple × le coût
        round-trip pour justifier l'entrée. C'est le garde-fou fondamental
        contre les trades de poussière qui semblent gagnants en brut mais
        perdent en net.

        Args:
            position_size_usd: Taille de la position en USD
            leverage: Levier appliqué
            expected_capture_pct: Capture attendue en % (ex: 0.3 = 0.3%)
            min_ev_multiple: Multiplicateur minimum (capture ≥ N × coût)

        Returns:
            dict avec round_trip_cost_usd, min_capture_required_pct,
            expected_net_pnl, is_viable, rejection_reason
        """
        effective_size = position_size_usd * leverage
        rt_cost = self.round_trip_cost_usd(effective_size)
        rt_cost_pct = self.round_trip_cost_pct()
        min_capture_pct = rt_cost_pct * min_ev_multiple
        min_capture_usd = rt_cost * min_ev_multiple

        expected_capture_usd = effective_size * expected_capture_pct / 100
        expected_net = expected_capture_usd - rt_cost

        is_viable = expected_capture_pct >= min_capture_pct
        rejection_reason = None
        if not is_viable:
            rejection_reason = (
                f"Capture attendue {expected_capture_pct:.3f}% < seuil {min_capture_pct:.3f}% "
                f"({min_ev_multiple}× coût RT {rt_cost_pct:.3f}%). "
                f"Net attendu: ${expected_net:.2f} (coût: ${rt_cost:.2f})"
            )

        return {
            "round_trip_cost_usd": round(rt_cost, 4),
            "round_trip_cost_pct": round(rt_cost_pct, 4),
            "min_capture_required_pct": round(min_capture_pct, 4),
            "min_capture_required_usd": round(min_capture_usd, 4),
            "expected_capture_pct": round(expected_capture_pct, 4),
            "expected_net_pnl": round(expected_net, 4),
            "is_viable": is_viable,
            "rejection_reason": rejection_reason,
        }


# ================================================================
# PRESETS — Hypothèses documentées et paramétrables
# ================================================================

# Preset OPTIMISTIC : conditions idéales (gros compte, limit orders, marché calme)
# - Frais Binance VIP1 (0.04% maker / 0.06% taker)
# - Spread serré (0.02%) : typique BTC/USDT en heures de haute liquidité
# - Slippage minimal (0.01%) : limit orders uniquement
COST_OPTIMISTIC = TradingCostModel(
    maker_fee_pct=0.04,
    taker_fee_pct=0.06,
    spread_pct=0.02,
    slippage_pct=0.01,
    name="optimistic",
)

# Preset REALISTIC : conditions normales (retail, market orders fréquents)
# - Frais Binance standard (0.10% maker / 0.10% taker)
# - Spread moyen (0.05%) : typique BTC/USDT conditions normales
# - Slippage modéré (0.03%) : mix market/limit orders
COST_REALISTIC = TradingCostModel(
    maker_fee_pct=0.10,
    taker_fee_pct=0.10,
    spread_pct=0.05,
    slippage_pct=0.03,
    name="realistic",
)

# Preset STRESSED : conditions défavorables (volatilité, faible liquidité)
# - Frais Binance standard (0.10%)
# - Spread élargi (0.15%) : typique en période de volatilité / liquidité basse
# - Slippage élevé (0.10%) : market orders en conditions tendues
COST_STRESSED = TradingCostModel(
    maker_fee_pct=0.10,
    taker_fee_pct=0.10,
    spread_pct=0.15,
    slippage_pct=0.10,
    name="stressed",
)

# Dictionnaire d'accès par nom
COST_PRESETS = {
    "optimistic": COST_OPTIMISTIC,
    "realistic": COST_REALISTIC,
    "stressed": COST_STRESSED,
}


def get_cost_model(preset: str = "realistic") -> TradingCostModel:
    """Retourne un TradingCostModel par nom de preset."""
    return COST_PRESETS.get(preset, COST_REALISTIC)

