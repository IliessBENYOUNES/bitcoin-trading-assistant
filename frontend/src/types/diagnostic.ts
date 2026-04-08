// =============================================================================
// Diagnostic Types — v1.6 Frequency Diagnostic
// =============================================================================

export interface NonTradeRankedReason {
  rank: number;
  reason: string;
  label: string;
  count: number;
  pct: number;
  category: string;
}

export interface PositionDurationStats {
  total_closed: number;
  avg_duration_hours: number;
  median_duration_hours: number;
  min_duration_hours: number;
  max_duration_hours: number;
  pct_under_1h: number;
  pct_1h_to_4h: number;
  pct_4h_to_24h: number;
  pct_over_24h: number;
  ticks_blocked_by_open_position: number;
  pct_ticks_blocked_by_position: number;
}

export interface ProfileComparisonRow {
  profile: string;
  total_trades: number;
  trades_per_day: number;
  win_rate: number;
  net_pnl: number;
  expectancy: number;
  avg_duration_hours: number;
  max_drawdown_pct: number;
  simulated_entries: number;
  simulated_entries_per_day: number;
  top_block_reason: string;
  top_block_pct: number;
}

export interface RiskBrakeAnalysis {
  total_ticks: number;
  ticks_blocked_by_risk: number;
  pct_blocked_by_risk: number;
  ticks_kill_switch: number;
  ticks_daily_loss: number;
  ticks_leverage_reduced: number;
  ticks_leverage_forced_x1: number;
  pct_signal_filter: number;
  pct_risk_filter: number;
  pct_structural: number;
}

export interface DiagnosticResponse {
  total_ticks: number;
  total_trades: number;
  tick_to_trade_pct: number;
  avg_trades_per_day: number;
  analysis_days: number;
  top_non_trade_reasons: NonTradeRankedReason[];
  position_duration: PositionDurationStats;
  profile_comparison: ProfileComparisonRow[];
  risk_brake: RiskBrakeAnalysis;
  main_bottleneck: string;
  bottleneck_detail: string;
  recommendations: string[];
}

export interface MissedOpportunityItem {
  tick_timestamp: string;
  btc_price_at_tick: number;
  decision_action?: string;
  decision_score?: number;
  reason_no_trade: string;
  profile_at_tick: string;
  price_after_5m?: number;
  price_after_15m?: number;
  price_after_30m?: number;
  best_move_pct: number;
  best_move_window: string;
  was_exploitable: boolean;
}

export interface MissedOpportunitySummary {
  total_non_trade_ticks_analyzed: number;
  ticks_with_favorable_move: number;
  pct_missed: number;
  avg_missed_move_pct: number;
  missed_above_010_pct: number;
  missed_above_020_pct: number;
  missed_above_030_pct: number;
  missed_above_050_pct: number;
  missed_by_reason: NonTradeRankedReason[];
  top_examples: MissedOpportunityItem[];
  warning: string;
}

export interface LeverageAnalysisResponse {
  total_leveraged_trades: number;
  total_unleveraged_trades: number;
  pnl_with_leverage: number;
  pnl_without_leverage: number;
  leverage_benefit: number;
  win_rate_leveraged: number;
  win_rate_unleveraged: number;
  trades_amplified_positive: number;
  trades_amplified_negative: number;
  trades_refused_by_leverage: number;
  trades_reduced_by_risk: number;
}

