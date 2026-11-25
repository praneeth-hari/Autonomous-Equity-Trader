// Read-only client for the local FastAPI backend (GET only).

export interface Position {
  ticker: string
  shares: number
  entry_price: number
  current_price: number
  market_value: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  sentiment: string
  earnings: string
  size_tier: string
}

export interface Summary {
  run_date: string | null
  cash: number
  total_equity: number
  invested_value: number
  cash_reserve_pct: number
  open_positions_count: number
  max_positions: number
  unrealized_pnl_total: number
  positions: Position[]
  last_run_status: string
  last_run_message: string
  last_run_timestamp: string | null
}

export interface CurvePoint {
  date: string
  'My Portfolio': number
  'SPY Benchmark': number
}

export interface Overview {
  summary: Summary
  initial_capital: number
  return_pct: number
  spy_return_pct: number
  curve: CurvePoint[]
  metrics: Record<string, number>
  label: string
}

export interface Rules {
  buy_bar: number
  signal_exit: number
  stop_loss: number
  take_profit: number
  max_positions: number
}

export interface Status {
  ok: boolean
  paper_only: boolean
  notice: string
  initial_capital: number
  benchmark: string
  rules: Rules
}

export interface Trade {
  date: string
  ticker: string
  action: string
  shares: number
  price: number
  fee: number
  net_pnl: number
}

export interface Prediction {
  ticker: string
  sector: string
  probability: number
  sentiment: string
  earnings: string
  qualification: string
  action_signal: string
}

export interface Signals {
  regime: { status: string; is_risk_on: boolean; explanation: string; spy_price: number | null; spy_200ma: number | null }
  buy_bar: number
  signal_exit: number
  predictions: Prediction[]
}

interface Stats {
  cagr_pct: number
  max_drawdown_pct: number
  sharpe: number
}

export interface Backtests {
  source: string
  label: string
  net_of_cost_pct_per_trade: number
  note: string
  periods: { period: string; strategy: Stats; spy_buy_hold: Stats; spy_above_200d: Stats }[]
}

export interface Health {
  pipeline: { status: string; message: string; timestamp: string | null }
  model: { file_found: boolean; matches_freeze: boolean; frozen: boolean }
  drift: { status: string; recommendation: string; sample_size_live: number }
  psi_note: string
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  status: () => get<Status>('/api/status'),
  overview: () => get<Overview>('/api/overview'),
  portfolio: () => get<{ summary: Summary; stop_loss_pct: number; take_profit_pct: number }>('/api/portfolio'),
  trades: (limit = 100) => get<{ trades: Trade[]; cost_per_trade_pct: number }>(`/api/trades?limit=${limit}`),
  signals: () => get<Signals>('/api/signals'),
  backtests: () => get<Backtests>('/api/backtests'),
  health: () => get<Health>('/api/health'),
}
