import { useQuery } from '@tanstack/react-query'
import { Card, Empty, Label, Load, PageHeader } from '../components/ui'
import { api, type Position } from '../lib/api'
import { asPercent, pct, tone, usd } from '../lib/format'

/** Position sits on a lane between its stop-loss and take-profit. */
function Lane({ p, stop, target }: { p: Position; stop: number; target: number }) {
  const span = stop + target
  const at = Math.max(0, Math.min(100, ((p.unrealized_pnl_pct + stop) / span) * 100))
  const zero = (stop / span) * 100
  return (
    <div className="grid grid-cols-[80px_1fr_80px] items-center gap-4 border-t border-line py-4 first:border-0">
      <div className="font-semibold">{p.ticker}</div>
      <div className="relative h-6" aria-label={`${p.ticker} at ${pct(p.unrealized_pnl_pct)} between stop-loss and take-profit`}>
        <div className="absolute inset-x-0 top-[11px] h-0.5 bg-line" />
        <div className="absolute inset-y-1 w-0.5 bg-ink" style={{ left: `${zero}%` }} />
        <div
          className={`absolute top-[8px] h-2 rounded-full ${p.unrealized_pnl_pct >= 0 ? 'bg-brand' : 'bg-loss'}`}
          style={{ left: `${Math.min(zero, at)}%`, width: `${Math.abs(at - zero)}%` }}
        />
        <div
          className={`absolute top-1 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-white ring-2 ${
            p.unrealized_pnl_pct >= 0 ? 'bg-brand ring-brand' : 'bg-loss ring-loss'
          }`}
          style={{ left: `${at}%` }}
        />
      </div>
      <div className={`num text-right font-medium ${tone(p.unrealized_pnl_pct)}`}>{pct(p.unrealized_pnl_pct)}</div>
    </div>
  )
}

export function Portfolio() {
  const q = useQuery({ queryKey: ['portfolio'], queryFn: api.portfolio })
  return (
    <>
      <PageHeader eyebrow="Portfolio" title="Holdings" />
      <Load q={q}>
        {(d) => {
          const s = d.summary
          const stop = asPercent(d.stop_loss_pct)
          const target = asPercent(d.take_profit_pct)
          return (
            <div className="grid gap-4">
              <div className="grid gap-4 sm:grid-cols-3">
                <Card>
                  <Label>Invested</Label>
                  <div className="num text-2xl font-medium">{usd(s.invested_value)}</div>
                </Card>
                <Card>
                  <Label>Cash reserve</Label>
                  <div className="num text-2xl font-medium">{s.cash_reserve_pct.toFixed(1)}%</div>
                </Card>
                <Card>
                  <Label>Positions</Label>
                  <div className="num text-2xl font-medium">
                    {s.open_positions_count} of {s.max_positions}
                  </div>
                </Card>
              </div>
              <Card>
                <h2 className="text-lg font-semibold">Where each holding sits</h2>
                <p className="mb-2 text-sm text-muted">
                  Each position lives between its stop-loss (-{stop}%) and its take-profit (+{target}%). The dark line is the price paid.
                </p>
                {s.positions.length === 0 ? (
                  <Empty title="Nothing held right now" body="The account is fully in cash." />
                ) : (
                  s.positions.map((p) => <Lane key={p.ticker} p={p} stop={stop} target={target} />)
                )}
              </Card>
            </div>
          )
        }}
      </Load>
    </>
  )
}
