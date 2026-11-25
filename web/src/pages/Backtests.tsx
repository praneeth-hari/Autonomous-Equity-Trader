import { useQuery } from '@tanstack/react-query'
import { Card, Load, OptimisticNote, PageHeader } from '../components/ui'
import { api } from '../lib/api'

export function Backtests() {
  const q = useQuery({ queryKey: ['backtests'], queryFn: api.backtests })
  return (
    <>
      <PageHeader eyebrow="Backtests" title="Strategy against SPY" />
      <Load q={q}>
        {(d) => (
          <div className="grid gap-4">
            <Card>
              <table className="w-full text-sm">
                <thead className="border-b border-line text-xs text-muted">
                  <tr>
                    <th className="py-2 text-left font-normal">Period</th>
                    <th className="text-left font-normal">Strategy CAGR</th>
                    <th className="text-left font-normal">SPY buy-and-hold</th>
                    <th className="text-left font-normal">SPY above 200-day</th>
                    <th className="text-left font-normal">Strategy max drawdown</th>
                  </tr>
                </thead>
                <tbody>
                  {d.periods.map((p) => (
                    <tr key={p.period} className="border-b border-line last:border-0">
                      <td className="py-3 font-semibold">{p.period}</td>
                      <td className="num">{p.strategy.cagr_pct.toFixed(2)}%</td>
                      <td className="num">{p.spy_buy_hold.cagr_pct.toFixed(2)}%</td>
                      <td className="num">{p.spy_above_200d.cagr_pct.toFixed(2)}%</td>
                      <td className="num">{p.strategy.max_drawdown_pct.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card>
              {d.periods.map((p) => (
                <div key={p.period} className="mb-4 last:mb-0">
                  <div className="mb-1 text-sm font-semibold">{p.period}</div>
                  {[
                    ['Strategy', p.strategy.cagr_pct, 'bg-brand'],
                    ['SPY hold', p.spy_buy_hold.cagr_pct, 'bg-faint'],
                  ].map(([label, v, cls]) => (
                    <div key={String(label)} className="mt-1 grid grid-cols-[90px_1fr_56px] items-center gap-3 text-sm">
                      <span className="text-muted">{label}</span>
                      <div className="h-3 rounded-full bg-chip">
                        <div className={`h-3 rounded-full ${cls}`} style={{ width: `${Math.max(2, (Number(v) / 14) * 100)}%` }} />
                      </div>
                      <span className="num text-right">{Number(v).toFixed(2)}%</span>
                    </div>
                  ))}
                </div>
              ))}
              <p className="mt-4 text-sm text-muted">{d.note}</p>
              <OptimisticNote>
                {d.label} Net of {d.net_of_cost_pct_per_trade}% per trade. Source: {d.source}.
              </OptimisticNote>
            </Card>
          </div>
        )}
      </Load>
    </>
  )
}
