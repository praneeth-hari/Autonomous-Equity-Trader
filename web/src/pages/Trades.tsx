import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Card, Empty, Load, PageHeader } from '../components/ui'
import { api, type Trade } from '../lib/api'
import { tone, usd } from '../lib/format'

type SortKey = keyof Trade

export function Trades() {
  const q = useQuery({ queryKey: ['trades'], queryFn: () => api.trades(200) })
  const [key, setKey] = useState<SortKey>('date')
  const [desc, setDesc] = useState(true)
  const [filter, setFilter] = useState('')

  const header = (k: SortKey, label: string) => (
    <th className="py-2 text-left font-normal">
      <button
        className="cursor-pointer hover:text-ink"
        onClick={() => {
          if (k === key) setDesc(!desc)
          else {
            setKey(k)
            setDesc(true)
          }
        }}
      >
        {label} {key === k ? (desc ? '↓' : '↑') : ''}
      </button>
    </th>
  )

  return (
    <>
      <PageHeader eyebrow="Trades" title="Trade history" />
      <Load q={q}>
        {(d) => (
          <TradeTable
            trades={d.trades}
            cost={d.cost_per_trade_pct}
            sortKey={key}
            desc={desc}
            filter={filter}
            setFilter={setFilter}
            header={header}
          />
        )}
      </Load>
    </>
  )
}

function TradeTable(props: {
  trades: Trade[]
  cost: number
  sortKey: SortKey
  desc: boolean
  filter: string
  setFilter: (v: string) => void
  header: (k: SortKey, label: string) => React.ReactNode
}) {
  const { trades, cost, sortKey, desc, filter, setFilter, header } = props
  const rows = useMemo(() => {
    const f = filter.trim().toUpperCase()
    const list = trades.filter((t) => !f || t.ticker.toUpperCase().includes(f))
    return [...list].sort((a, b) => {
      const x = a[sortKey]
      const y = b[sortKey]
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
      return desc ? -c : c
    })
  }, [trades, sortKey, desc, filter])

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by ticker"
          aria-label="Filter by ticker"
          className="w-48 rounded-lg border border-line px-3 py-1.5 text-sm"
        />
        <span className="text-xs text-muted">Every fill includes the {cost}% simulated cost</span>
      </div>
      {rows.length === 0 ? (
        <Empty title="No trades yet" body="Trades appear here after the daily run fills an order." />
      ) : (
        <table className="w-full text-sm">
          <thead className="border-b border-line text-xs text-muted">
            <tr>
              {header('date', 'Date')}
              {header('ticker', 'Ticker')}
              {header('action', 'Side')}
              {header('shares', 'Shares')}
              {header('price', 'Price')}
              {header('fee', 'Cost')}
              {header('net_pnl', 'Net P/L')}
            </tr>
          </thead>
          <tbody>
            {rows.map((t, i) => (
              <tr key={`${t.date}-${t.ticker}-${i}`} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="num py-3">{t.date}</td>
                <td className="font-semibold">{t.ticker}</td>
                <td>{t.action}</td>
                <td className="num">{t.shares}</td>
                <td className="num">{usd(t.price)}</td>
                <td className="num text-muted">{usd(t.fee)}</td>
                <td className={`num ${tone(t.net_pnl)}`}>{usd(t.net_pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}
