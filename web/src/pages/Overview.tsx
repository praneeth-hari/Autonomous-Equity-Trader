import { useQuery } from '@tanstack/react-query'
import { EquityChart } from '../components/EquityChart'
import { Card, Empty, Label, Load, OptimisticNote, PageHeader, Pill } from '../components/ui'
import { api } from '../lib/api'
import { pct, tone, usd } from '../lib/format'

export function Overview() {
  const q = useQuery({ queryKey: ['overview'], queryFn: api.overview, refetchInterval: 60_000 })
  const model = useQuery({ queryKey: ['health'], queryFn: api.health })

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Good morning"
        right={
          <>
            <Pill tone="ok">Paper money only</Pill>
            {model.data?.model.frozen && <Pill>Model frozen</Pill>}
          </>
        }
      />
      <Load q={q}>
        {(d) => {
          const s = d.summary
          return (
            <div className="grid gap-4 lg:grid-cols-[1.8fr_1fr]">
              <Card>
                <Label>Total value</Label>
                <div className="flex flex-wrap items-baseline gap-3">
                  <span className="num text-4xl font-medium tracking-tight">{usd(s.total_equity)}</span>
                  <span className={`num text-sm ${tone(d.return_pct)}`}>{pct(d.return_pct)}</span>
                  <span className="num text-sm text-faint">SPY {pct(d.spy_return_pct)}</span>
                </div>
                <EquityChart data={d.curve} />
                <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
                  <span>Strategy, net of 0.2% costs, against SPY buy-and-hold (dashed)</span>
                  <OptimisticNote>{d.label}</OptimisticNote>
                </div>
              </Card>

              <div className="grid gap-4">
                <Card>
                  <Label>Cash</Label>
                  <div className="num text-2xl font-medium">{s.cash_reserve_pct.toFixed(1)}%</div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, s.cash_reserve_pct)}%` }} />
                  </div>
                  <div className="mt-2 text-xs text-muted">{usd(s.cash)} uninvested</div>
                </Card>
                <Card>
                  <Label>Max drawdown</Label>
                  <div className="num text-2xl font-medium">{(d.metrics.max_drawdown_pct ?? 0).toFixed(1)}%</div>
                  <div className="mt-2 text-xs text-muted">Stop-loss caps each position at -8%</div>
                </Card>
              </div>

              <Card>
                <Label>Open positions</Label>
                {s.positions.length === 0 ? (
                  <Empty title="No open positions" body="Cash is a valid position. The model buys only at a score of 0.60 or higher." />
                ) : (
                  <table className="mt-2 w-full text-sm">
                    <thead>
                      <tr className="border-b border-line text-left text-xs text-muted">
                        <th className="py-2 font-normal">Ticker</th>
                        <th className="font-normal">Value</th>
                        <th className="font-normal">P/L</th>
                        <th className="font-normal">Earnings</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.positions.map((p) => (
                        <tr key={p.ticker} className="border-b border-slate-100 last:border-0">
                          <td className="py-3 font-semibold">{p.ticker}</td>
                          <td className="num">{usd(p.market_value)}</td>
                          <td className={`num ${tone(p.unrealized_pnl_pct)}`}>{pct(p.unrealized_pnl_pct)}</td>
                          <td className="text-xs text-muted">{p.earnings}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>

              <Card>
                <Label>Last pipeline run</Label>
                <div className="mt-1 text-sm font-medium">{s.last_run_status}</div>
                <p className="mt-1 text-xs text-muted">{s.last_run_message}</p>
                {s.run_date && <p className="num mt-2 text-xs text-faint">Snapshot {s.run_date}</p>}
              </Card>
            </div>
          )
        }}
      </Load>
    </>
  )
}
