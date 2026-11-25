import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { X } from 'lucide-react'
import { useState } from 'react'
import { Card, Empty, Pill } from '../components/ui'
import { api, type Quote } from '../lib/api'
import { compact, pct, price, tone, usd } from '../lib/format'
import { go, SYMBOL_RE } from '../lib/router'
import { usePersisted } from '../lib/storage'

interface Position {
  symbol: string
  shares: number
  cost: number
}

const isPositions = (v: unknown): v is Position[] =>
  Array.isArray(v) && v.every((p) => p && typeof p.symbol === 'string' && typeof p.shares === 'number' && typeof p.cost === 'number')
const isSymbols = (v: unknown): v is string[] => Array.isArray(v) && v.every((s) => typeof s === 'string')

const PALETTE = ['var(--color-brand)', '#3b82f6', '#f0a02e', '#7a5af8', '#e8734a', '#2fb5b5']

export function Watchlist() {
  const [positions, setPositions] = usePersisted<Position[]>('pt-practice', [], isPositions)
  const [watch, setWatch] = usePersisted<string[]>('pt-watchlist', ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN'], isSymbols)
  const [form, setForm] = useState({ symbol: '', shares: '', cost: '' })
  const [watchInput, setWatchInput] = useState('')
  const [error, setError] = useState('')
  const [watchError, setWatchError] = useState('')

  const symbols = Array.from(new Set([...positions.map((p) => p.symbol), ...watch])).slice(0, 40)
  const q = useQuery({
    queryKey: ['quotes', symbols.join(',')],
    queryFn: () => api.quotes(symbols),
    enabled: symbols.length > 0,
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  })
  const quotes = new Map<string, Quote>((q.data?.quotes ?? []).map((x) => [x.symbol, x]))

  const addPosition = () => {
    const symbol = form.symbol.trim().toUpperCase()
    const shares = Number(form.shares)
    const cost = Number(form.cost)
    if (!SYMBOL_RE.test(symbol)) return setError('Enter a ticker such as AAPL.')
    if (!(shares > 0) || !(cost > 0)) return setError('Enter shares and an average cost above zero.')
    setError('')
    setPositions((p) => [...p, { symbol, shares, cost }])
    setForm({ symbol: '', shares: '', cost: '' })
  }

  const addWatch = () => {
    const s = watchInput.trim().toUpperCase()
    if (!SYMBOL_RE.test(s)) return setWatchError('Enter a ticker such as AAPL.')
    if (watch.includes(s)) return setWatchError(`${s} is already on the list.`)
    setWatchError('')
    setWatch((w) => [...w, s])
    setWatchInput('')
  }

  const total = positions.reduce((s, p) => s + p.shares * (quotes.get(p.symbol)?.price ?? 0), 0)
  const field = 'rounded-xl border border-line bg-chip px-3 py-2 text-sm outline-none focus:border-brand'

  return (
    <>
      <div className="pb-4 pt-10">
        <h1 className="text-5xl font-extrabold tracking-tight md:text-6xl">Watchlist</h1>
        <p className="mt-3 max-w-xl text-muted">Your practice portfolio and watched tickers. Both live only in this browser and never touch the real paper account or the trading system.</p>
      </div>

      {q.isError && (
        <Card className="mb-4 border-loss/40">
          <div className="text-sm font-medium text-loss">Couldn't load prices</div>
          <p className="mt-1 text-sm text-muted">{(q.error as Error).message}</p>
        </Card>
      )}

      <Card className="mb-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Practice portfolio</h2>
          <Pill tone="warn">Practice, not traded by the system</Pill>
        </div>
        {total > 0 && (
          <div className="mb-4 flex h-3.5 gap-1 overflow-hidden rounded-full" aria-label="Allocation by position">
            {positions.map((p, i) => (
              <span key={`${p.symbol}-${i}`} title={p.symbol} style={{ width: `${((p.shares * (quotes.get(p.symbol)?.price ?? 0)) / total) * 100}%`, background: PALETTE[i % PALETTE.length] }} />
            ))}
          </div>
        )}
        <form
          className="mb-1 flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            addPosition()
          }}
        >
          <input className={clsx(field, 'w-36')} placeholder="Search any ticker..." aria-label="Ticker" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} />
          <input className={clsx(field, 'w-28')} placeholder="Shares" inputMode="decimal" aria-label="Shares" value={form.shares} onChange={(e) => setForm({ ...form, shares: e.target.value })} />
          <input className={clsx(field, 'w-28')} placeholder="Avg cost" inputMode="decimal" aria-label="Average cost" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} />
          <button type="submit" className="cursor-pointer rounded-xl bg-brand px-4 py-2 text-xs font-medium tracking-wider text-white hover:opacity-90">
            ADD POSITION
          </button>
        </form>
        {error && <p className="mt-1 text-xs text-loss">{error}</p>}
        {positions.length === 0 ? (
          <Empty title="No practice positions" body="Add a ticker, share count and average cost to follow a made-up position against live prices." />
        ) : (
          <table className="mt-3 w-full text-sm">
            <thead className="border-b border-line text-[10.5px] tracking-[0.1em] text-faint">
              <tr>
                {['POSITION', 'SHARES', 'AVG COST', 'PRICE', 'VALUE', 'RETURN', ''].map((h, i) => (
                  <th key={h + i} className={clsx('py-2.5 font-normal', i === 0 ? 'text-left' : 'text-right')}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => {
                const px = quotes.get(p.symbol)
                const ret = px ? (px.price - p.cost) * p.shares : null
                return (
                  <tr key={`${p.symbol}-${i}`} className="border-b border-line last:border-0 hover:bg-chip">
                    <td className="py-3">
                      <button className="cursor-pointer text-left" onClick={() => go(`stock/${p.symbol}`)}>
                        <b>{p.symbol}</b>
                        <div className="text-xs text-muted">{px?.name ?? (q.isLoading ? 'Loading…' : 'No price found')}</div>
                      </button>
                    </td>
                    <td className="num text-right">{p.shares}</td>
                    <td className="num text-right">{usd(p.cost)}</td>
                    <td className="num text-right">{px ? usd(px.price) : '–'}</td>
                    <td className="num text-right">{px ? usd(px.price * p.shares) : '–'}</td>
                    <td className={clsx('num text-right', ret != null && tone(ret))}>{ret != null ? `${usd(ret)} ${pct((px!.price / p.cost - 1) * 100)}` : '–'}</td>
                    <td className="text-right">
                      <button className="cursor-pointer p-1 text-faint hover:text-loss" aria-label={`Remove ${p.symbol}`} onClick={() => setPositions((all) => all.filter((_, j) => j !== i))}>
                        <X size={15} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>

      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Watchlist</h2>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              addWatch()
            }}
          >
            <input className={clsx(field, 'w-40')} placeholder="Add a ticker" aria-label="Add a ticker to the watchlist" value={watchInput} onChange={(e) => setWatchInput(e.target.value)} />
            <button type="submit" className="cursor-pointer rounded-xl border border-line bg-card px-4 py-2 text-xs tracking-wider hover:bg-chip">
              ADD
            </button>
          </form>
        </div>
        {watchError && <p className="mb-2 text-xs text-loss">{watchError}</p>}
        {watch.length === 0 ? (
          <Empty title="Your watchlist is empty" body="Add a ticker above to follow its price." />
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-line text-[10.5px] tracking-[0.1em] text-faint">
              <tr>
                {['SYMBOL', 'PRICE', 'CHANGE', '% CHANGE', 'VOLUME', 'MODEL SCORE', ''].map((h, i) => (
                  <th key={h + i} className={clsx('py-2.5 font-normal', i === 0 ? 'text-left' : 'text-right')}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {watch.map((s) => {
                const px = quotes.get(s)
                return (
                  <tr key={s} className="border-b border-line last:border-0 hover:bg-chip">
                    <td className="py-3">
                      <button className="cursor-pointer text-left" onClick={() => go(`stock/${s}`)}>
                        <b>{s}</b>
                        <div className="text-xs text-muted">{px?.name ?? (q.isLoading ? 'Loading…' : 'No price found')}</div>
                      </button>
                    </td>
                    <td className="num text-right">{px ? price(px.price) : '–'}</td>
                    <td className={clsx('num text-right', px && tone(px.change))}>{px ? `${px.change >= 0 ? '+' : ''}${price(px.change)}` : '–'}</td>
                    <td className={clsx('num text-right', px && tone(px.change_pct))}>{px ? pct(px.change_pct) : '–'}</td>
                    <td className="num text-right">{px ? compact(px.volume) : '–'}</td>
                    <td className="num text-right">
                      {px?.model ? (
                        <>
                          {px.model.probability.toFixed(2)} <Pill tone={px.model.zone === 'buy zone' ? 'ok' : 'neutral'}>{px.model.zone}</Pill>
                        </>
                      ) : (
                        <span className="text-faint">–</span>
                      )}
                    </td>
                    <td className="text-right">
                      <button className="cursor-pointer p-1 text-faint hover:text-loss" aria-label={`Remove ${s}`} onClick={() => setWatch((w) => w.filter((x) => x !== s))}>
                        <X size={15} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
        <p className="mt-3 text-xs text-faint">Model scores are the latest stored predictions for the 25 universe stocks only. A dash means no stored score.</p>
      </Card>
    </>
  )
}
