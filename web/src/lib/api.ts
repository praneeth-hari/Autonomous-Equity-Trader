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

export interface ClosedTrade {
  date_bought: string
  date_sold: string
  ticker: string
  entry_price: number
  exit_price: number
  shares: number
  pnl: number
  pnl_pct: number
  exit_reason: string
  model_score: number | null
}

export interface Performance {
  sample_days: number
  enough_history: boolean
  min_days: number
  metrics: Record<string, number>
  drawdown: { date: string; drawdown_pct: number }[]
  daily_returns: { bin_center: number; bin_label: string; count: number; sign: string }[]
  win_loss: { trade_id: number; date: string; ticker: string; net_pnl: number; sign: string; trade_label: string }[]
  sectors: { sector: string; value: number; pct: number }[]
  closed_summary: Record<string, number>
  closed_trades: ClosedTrade[]
  label: string
}

export interface Quote {
  symbol: string
  name: string
  price: number
  prev_close: number
  change: number
  change_pct: number
  volume: number
  spark: number[]
  in_universe: boolean
  weight?: number
  model?: { probability: number; date: string; zone: string } | null
}

export interface MarketOverview {
  etfs: Quote[]
  movers: Quote[]
  universe: Quote[]
}

export interface Bar {
  t: number
  o: number
  h: number
  l: number
  c: number
  v: number
}

export interface History {
  symbol: string
  name: string
  interval: string
  bars: Bar[]
  spy?: { t: number; c: number }[]
}

export interface StockDetail extends Quote {
  open: number
  high: number
  low: number
  week52_high: number
  week52_low: number
  as_of: number
  model: { probability: number; date: string; zone: string } | null
  headlines: { title: string; sentiment: 'positive' | 'neutral' | 'negative' }[]
}

export const INTERVALS = ['5min', '15min', '30min', '1h', '4h', '1day', '1week', '1month'] as const
export type Interval = (typeof INTERVALS)[number]

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatReply {
  reply: string
  ok: boolean
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  performance: () => get<Performance>('/api/performance'),
  marketOverview: () => get<MarketOverview>('/api/market/overview'),
  quotes: (symbols: string[]) => get<{ quotes: Quote[] }>(`/api/market/quotes?symbols=${encodeURIComponent(symbols.join(','))}`),
  history: (symbol: string, interval: Interval, spy: boolean) =>
    get<History>(`/api/market/history/${encodeURIComponent(symbol)}?interval=${interval}&bars=120&spy=${spy}`),
  stock: (symbol: string) => get<StockDetail>(`/api/market/stock/${encodeURIComponent(symbol)}`),
  chatStatus: () => get<{ available: boolean; model: string; local_only: boolean }>('/api/chat/status'),
  chat: (message: string, history: ChatTurn[]) => post<ChatReply>('/api/chat', { message, history: history.slice(-6) }),
  status: () => get<Status>('/api/status'),
  overview: () => get<Overview>('/api/overview'),
  portfolio: () => get<{ summary: Summary; stop_loss_pct: number; take_profit_pct: number }>('/api/portfolio'),
  trades: (limit = 100) => get<{ trades: Trade[]; cost_per_trade_pct: number }>(`/api/trades?limit=${limit}`),
  signals: () => get<Signals>('/api/signals'),
  backtests: () => get<Backtests>('/api/backtests'),
  health: () => get<Health>('/api/health'),
}
