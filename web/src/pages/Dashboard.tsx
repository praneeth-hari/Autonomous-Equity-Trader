import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Search } from 'lucide-react'
import { useState } from 'react'
import { PriceArea } from '../components/PriceArea'
import { QuoteCard } from '../components/QuoteCard'
import { Tape } from '../components/Tape'
import { Card, Load, Pill } from '../components/ui'
import { api } from '../lib/api'
import { compact, pct, price, tone, usd } from '../lib/format'
import { go, SYMBOL_RE } from '../lib/router'

const POPULAR = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'TSLA']

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10.5px] tracking-[0.1em] text-faint">{label}</div>
      <div className="num text-[15px] font-semibold">{value}</div>
    </div>
  )
}

function AccountTile({ label, value, note, href }: { label: string; value: string; note: string; href: string }) {
  return (
    <a href={href} className="rounded-2xl border border-line bg-card p-4 transition-colors hover:border-brand">
      <div className="text-xs text-muted">{label}</div>
      <div className="num my-1 text-2xl font-semibold tracking-tight">{value}</div>
      <div className="text-xs text-muted">{note}</div>
    </a>
  )
}

export function Dashboard() {
  const [sym, setSym] = useState(() => localStorage.getItem('pt-last-stock') ?? 'AAPL')
  const [text, setText] = useState('')
  const [error, setError] = useState('')

  const market = useQuery({ queryKey: ['market-overview'], queryFn: api.marketOverview, staleTime: 5 * 60_000, refetchInterval: 5 * 60_000 })
  const stock = useQuery({ queryKey: ['stock', sym], queryFn: () => api.stock(sym), staleTime: 5 * 60_000 })
  const hist = useQuery({ queryKey: ['history', sym, '1day', false], queryFn: () => api.history(sym, '1day', false), staleTime: 5 * 60_000 })
  const account = useQuery({ queryKey: ['overview'], queryFn: api.overview, staleTime: 60_000 })
  const signals = useQuery({ queryKey: ['signals'], queryFn: api.signals, staleTime: 5 * 60_000 })
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, staleTime: 60_000 })

  const open = () => {
    const s = text.trim().toUpperCase()
    if (!SYMBOL_RE.test(s)) return setError('Enter a ticker such as AAPL.')
    go(`stock/${s}`)
  }

  const s = stock.data
  return (
    <>
      <div className="grid items-center gap-10 pb-8 pt-12 lg:grid-cols-[1fr_1.15fr]">
        <div>
          <h1 className="text-[clamp(44px,7vw,84px)] font-extrabold leading-[0.98] tracking-[-0.04em]">
            Measure<span className="text-brand">.</span>
            <br />
            Learn<span className="text-brand">.</span>
            <br />
            Protect<span className="text-brand">.</span>
          </h1>
          <p className="mt-5 max-w-md text-muted">Prices, indicators and your paper account in one place. Pick a ticker and the chart follows it.</p>
          <form
            className="mt-5 flex gap-2 rounded-2xl border border-line bg-card p-2"
            onSubmit={(e) => {
              e.preventDefault()
              open()
            }}
          >
            <Search size={16} className="ml-2 mt-2.5 text-faint" />
            <input
              value={text}
              onChange={(e) => {
                setText(e.target.value)
                setError('')
              }}
              placeholder="Search any ticker..."
              aria-label="Ticker"
              className="min-w-0 flex-1 bg-transparent px-2 text-sm outline-none"
            />
            <button type="submit" className="cursor-pointer rounded-xl bg-brand px-4 py-2 text-xs font-medium tracking-wider text-white hover:opacity-90">
              GO
            </button>
          </form>
          {error && <p className="mt-1 text-xs text-loss">{error}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-faint">
            Popular:
            {POPULAR.map((p) => (
              <button
                key={p}
                onClick={() => setSym(p)}
                aria-pressed={sym === p}
                className={clsx('cursor-pointer rounded-lg border px-3 py-1 text-xs', sym === p ? 'border-ink bg-ink text-canvas' : 'border-line bg-card text-ink hover:bg-chip')}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div>
          <Load q={stock}>
            {(d) => (
              <>
                <div className="text-sm text-muted">{d.name}</div>
                <div className="flex items-baseline gap-2">
                  <span className="num text-[clamp(52px,8vw,92px)] font-bold leading-none tracking-tight">{price(d.price)}</span>
                  <span className="text-sm text-faint">USD</span>
                </div>
                <div className={clsx('num mb-2 mt-1 text-sm', tone(d.change))}>
                  {d.change >= 0 ? '+' : ''}
                  {price(d.change)} ({pct(d.change_pct)})
                </div>
              </>
            )}
          </Load>
          <Load q={hist}>{(h) => <PriceArea bars={h.bars} height={200} />}</Load>
          {s && (
            <div className="mt-2 grid grid-cols-3 gap-4 border-t border-line pt-3 sm:grid-cols-5">
              <Stat label="OPEN" value={price(s.open)} />
              <Stat label="PREV CLOSE" value={price(s.prev_close)} />
              <Stat label="VOLUME" value={compact(s.volume)} />
              <Stat label="52W HIGH" value={price(s.week52_high)} />
              <Stat label="52W LOW" value={price(s.week52_low)} />
            </div>
          )}
          {s && (
            <button onClick={() => go(`stock/${s.symbol}`)} className="mt-3 cursor-pointer text-xs tracking-wider text-brand-ink underline-offset-4 hover:underline">
              OPEN FULL ANALYSIS
            </button>
          )}
        </div>
      </div>

      {market.data && <Tape quotes={[...market.data.etfs, ...market.data.universe]} />}

      <section className="pt-12">
        <h2 className="text-3xl font-bold tracking-tight">Market movers</h2>
        <p className="mb-4 mt-1 text-muted">The biggest moves in your 25-stock universe today.</p>
        <Load q={market}>
          {(m) => (
            <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-5">
              {m.movers.map((q) => (
                <QuoteCard key={q.symbol} q={q} />
              ))}
            </div>
          )}
        </Load>
      </section>

      <section className="pt-12">
        <h2 className="text-3xl font-bold tracking-tight">Where the model stands</h2>
        <p className="mb-4 mt-1 max-w-2xl text-muted">The strategy only buys at a score of 0.60 or higher, and sits in cash when nothing qualifies. Cash is a position.</p>
        <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
          <AccountTile
            label="Account value"
            value={account.data ? usd(account.data.summary.total_equity) : '–'}
            note={account.data ? `${pct(account.data.return_pct)} since start, paper money` : account.isError ? 'API not reachable' : 'Loading…'}
            href="#overview"
          />
          <AccountTile
            label="Market regime"
            value={signals.data ? signals.data.regime.status : '–'}
            note={signals.data ? (signals.data.regime.is_risk_on ? 'Buying is allowed' : 'No new buys: SPY is below its 200-day line') : signals.isError ? 'Not available' : 'Loading…'}
            href="#signals"
          />
          <AccountTile
            label="Open positions"
            value={account.data ? `${account.data.summary.open_positions_count} of ${account.data.summary.max_positions}` : '–'}
            note={account.data ? `${account.data.summary.cash_reserve_pct.toFixed(0)}% in cash` : 'Loading…'}
            href="#portfolio"
          />
          <AccountTile
            label="Last pipeline run"
            value={health.data ? health.data.pipeline.status : '–'}
            note={health.data?.pipeline.status === 'DEGRADED' ? 'Some stocks were skipped by the data check' : health.data ? 'See the status page' : 'Loading…'}
            href="#health"
          />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Pill tone="warn">Backtests trail SPY buy-and-hold</Pill>
          <Pill>Optimistic: real results likely worse</Pill>
        </div>
      </section>
      <Card className="mt-12 border-0 bg-transparent p-0 text-xs text-faint">Prices come from Yahoo Finance and may be delayed. Paper trading only, and nothing here is financial advice.</Card>
    </>
  )
}
