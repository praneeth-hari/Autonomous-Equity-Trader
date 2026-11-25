import { expect, test as base, type Page } from '@playwright/test'

// ── Sample data (deterministic) ────────────────────────────────────────────────

export const UNIVERSE = [
  'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'VZ', 'CMCSA', 'AMZN', 'TSLA', 'HD', 'JPM', 'V', 'BAC',
  'UNH', 'JNJ', 'LLY', 'CAT', 'GE', 'UPS', 'PG', 'COST', 'KO', 'XOM', 'CVX', 'COP',
]
const ETFS = ['SPY', 'QQQ', 'DIA', 'IWM']

const spark = (base: number, up: boolean) => Array.from({ length: 30 }, (_, i) => base + (up ? i : -i) * 0.3)

export function quote(symbol: string, i = 0) {
  const price = 100 + i * 7
  const pct = (i % 2 ? 1 : -1) * (0.4 + (i % 3) * 0.3)
  return {
    symbol,
    name: `${symbol} Inc.`,
    price,
    prev_close: price / (1 + pct / 100),
    change: price - price / (1 + pct / 100),
    change_pct: pct,
    volume: 1_000_000 * (i + 1),
    spark: spark(price, pct >= 0),
    in_universe: UNIVERSE.includes(symbol),
    weight: price * 1_000_000 * (i + 1),
    model: symbol === 'AAPL' ? { probability: 0.58, date: '2026-09-28', zone: 'wait zone' } : null,
  }
}

export function bars(n = 120) {
  const t0 = 1_750_000_000
  return Array.from({ length: n }, (_, i) => {
    const c = 100 + Math.sin(i / 7) * 6 + i * 0.1
    return { t: t0 + i * 86_400, o: c - 0.4, h: c + 1.2, l: c - 1.1, c, v: 1_000_000 + (i % 9) * 90_000 }
  })
}

export const SYMBOL_PRICES: Record<string, number> = { AAPL: 123.45 }

export function stock(symbol: string) {
  const q = quote(symbol, Math.max(0, UNIVERSE.indexOf(symbol)))
  return {
    ...q,
    price: SYMBOL_PRICES[symbol] ?? q.price,
    open: 120.1, high: 125.2, low: 119.3, week52_high: 140.5, week52_low: 90.25, as_of: 1_760_000_000,
    headlines: [{ title: 'A sample headline for testing', sentiment: 'neutral' }],
  }
}

export const BUY = { id: '2026-11-25:BUY:AAPL', date: '2026-11-25', ticker: 'AAPL', action: 'BUY', shares: 4, price: 200, value: 800, reason: 'QUALIFIED_CONVICTION_BUY', requires_approval: true, status: 'PENDING' }
export const SELL = { id: '2026-11-25:SELL:META', date: '2026-11-25', ticker: 'META', action: 'SELL', shares: 1.5, price: 590, value: 885, reason: 'STOP_LOSS', requires_approval: false, status: 'AUTO' }

export const runHistory = (outcomes: string[]) =>
  outcomes.map((outcome, i) => ({ date: `2026-11-${String(10 + i).padStart(2, '0')}`, outcome }))

export function healthPayload(outcomes: string[] = ['SUCCESS', 'DEGRADED']) {
  return {
    pipeline: { status: 'DEGRADED', message: 'sample run message', timestamp: null },
    model: { file_found: true, matches_freeze: true, frozen: true },
    drift: { status: 'MONITOR', recommendation: 'Keep watching.', sample_size_live: 0 },
    psi_note: 'PSI note',
    ops: {
      run_history: runHistory(outcomes),
      missed_days: outcomes.includes('MISSED') ? ['2026-11-12'] : [],
      backups: { supported: true, count: 1, newest: 'trader_x.db', age_hours: 1.5, size_mb: 51.5, stale: false },
      environment: { ok: true, problems: [], warnings: [], info: ['Python 3.11.9'] },
      data_skips: { date: null, skipped: [] },
      data_quality: { checked: 26, problems: [] },
      kill_switch: { enabled: false, reason: '' },
      alerts: { telegram_configured: true, heartbeat_configured: false },
    },
  }
}

// ── The mock API ───────────────────────────────────────────────────────────────

export interface Call {
  method: string
  path: string
  query: string
  headers: Record<string, string>
  body: string | null
}

export class MockApi {
  calls: Call[] = []
  unmocked: string[] = []
  errors: string[] = []
  approvals = { approval_required: true, run_date: '2026-11-25', orders: [{ ...BUY }, { ...SELL }], how_it_works: ['No decision means no buy.'], enable_hint: '' }
  killSwitch = { enabled: false as boolean, reason: '', env_override: false, effective: false, warning: 'While the kill switch is ON the nightly run does nothing at all.' }
  health: ReturnType<typeof healthPayload> = healthPayload()

  respond(method: string, path: string, body: string | null): unknown | undefined {
    if (path === '/api/market/overview') {
      const etfs = ETFS.map((s, i) => quote(s, i + 30))
      const universe = UNIVERSE.map((s, i) => quote(s, i))
      return { etfs, movers: universe.slice(0, 5), universe }
    }
    if (path.startsWith('/api/market/stock/')) return stock(decodeURIComponent(path.split('/').pop()!))
    if (path.startsWith('/api/market/history/')) return { symbol: path.split('/').pop(), name: 'x', interval: '1day', bars: bars(), spy: bars().map((b) => ({ t: b.t, c: b.c * 4 })) }
    if (path === '/api/market/quotes') return { quotes: [] } // replaced per request below
    if (path === '/api/overview') return { summary: { run_date: '2026-11-25', cash: 9000, total_equity: 10000, invested_value: 1000, cash_reserve_pct: 90, open_positions_count: 0, max_positions: 3, unrealized_pnl_total: 0, positions: [], last_run_status: 'DEGRADED', last_run_message: 'm', last_run_timestamp: null }, initial_capital: 10000, return_pct: 0, spy_return_pct: 0, curve: [], metrics: {}, label: 'Optimistic' }
    if (path === '/api/signals') return { regime: { status: 'RISK-OFF', is_risk_on: false, explanation: 'SPY below its 200-day line', spy_price: 700, spy_200ma: 710 }, buy_bar: 0.6, signal_exit: 0.45, predictions: [] }
    if (path === '/api/health') return this.health
    if (path === '/api/approvals') return this.approvals
    if (path === '/api/kill-switch' && method === 'GET') return this.killSwitch
    if (path === '/api/kill-switch' && method === 'POST') {
      const b = JSON.parse(body ?? '{}')
      this.killSwitch = { ...this.killSwitch, enabled: b.enabled, reason: b.reason, effective: b.enabled }
      return this.killSwitch
    }
    const m = path.match(/^\/api\/approvals\/(.+)\/(approve|reject)$/)
    if (m && method === 'POST') {
      const id = decodeURIComponent(m[1])
      this.approvals = { ...this.approvals, orders: this.approvals.orders.map((o) => (o.id === id ? { ...o, status: m[2] === 'approve' ? 'APPROVED' : 'REJECTED' } : o)) }
      return this.approvals
    }
    return undefined
  }
}

export async function installMockApi(page: Page): Promise<MockApi> {
  const api = new MockApi()
  // Nothing may leave the machine during a test.
  await page.route(/^https?:\/\/(?!127\.0\.0\.1|localhost)/, (route) => route.abort())
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    api.calls.push({ method: req.method(), path: url.pathname, query: url.search, headers: req.headers(), body: req.postData() })
    if (url.pathname === '/api/market/quotes') {
      const symbols = (url.searchParams.get('symbols') ?? '').split(',').filter(Boolean)
      return route.fulfill({ json: { quotes: symbols.map((s, i) => quote(s, Math.max(0, UNIVERSE.indexOf(s)) || i)) } })
    }
    const body = api.respond(req.method(), url.pathname, req.postData())
    if (body === undefined) {
      api.unmocked.push(`${req.method()} ${url.pathname}`)
      return route.fulfill({ status: 500, json: { detail: 'not mocked in the browser tests' } })
    }
    return route.fulfill({ json: body as object })
  })
  page.on('pageerror', (e) => api.errors.push(String(e)))
  page.on('console', (m) => m.type() === 'error' && api.errors.push(m.text()))
  return api
}

/** `test` with the mock API installed. After every test: no unmocked API call, no console error, no page error. */
export const test = base.extend<{ api: MockApi }>({
  // auto: true installs the mock for EVERY test, even one that never asks for `api`. Without it such a test would
  // quietly talk to whatever real server is running.
  api: [
    async ({ page }, use) => {
      const api = await installMockApi(page)
      await use(api)
      expect(api.unmocked, 'API calls the test did not mock').toEqual([])
      expect(api.errors, 'console or page errors').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
