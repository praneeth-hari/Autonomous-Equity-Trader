import { useQuery } from '@tanstack/react-query'
import { Card, Label, Load, PageHeader, Pill } from '../components/ui'
import { api } from '../lib/api'

const signalTone = { BUY: 'ok', SELL: 'bad', VETO: 'warn', HOLD: 'neutral' } as const

export function Signals() {
  const q = useQuery({ queryKey: ['signals'], queryFn: api.signals, staleTime: 5 * 60_000 })
  return (
    <>
      <PageHeader eyebrow="Signals" title="Today's rankings" />
      <Load q={q}>
        {(d) => (
          <div className="grid gap-4">
            <Card>
              <Label>Market regime</Label>
              <div className="mt-1 flex items-center gap-3">
                <Pill tone={d.regime.is_risk_on ? 'ok' : 'bad'}>{d.regime.status}</Pill>
                <span className="text-sm text-muted">{d.regime.explanation}</span>
              </div>
            </Card>
            <Card>
              <p className="mb-2 text-sm text-muted">
                Buy at {d.buy_bar.toFixed(2)} or higher. Exit below {d.signal_exit.toFixed(2)}. In between, wait. A score of
                0.50 means no prediction was stored for today.
              </p>
              <table className="w-full text-sm">
                <thead className="border-b border-line text-xs text-muted">
                  <tr>
                    <th className="py-2 text-left font-normal">Ticker</th>
                    <th className="text-left font-normal">Sector</th>
                    <th className="text-left font-normal">Probability</th>
                    <th className="text-left font-normal">Earnings</th>
                    <th className="text-left font-normal">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {d.predictions.map((p) => (
                    <tr key={p.ticker} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                      <td className="py-3 font-semibold">{p.ticker}</td>
                      <td className="text-muted">{p.sector}</td>
                      <td className="num">{p.probability.toFixed(2)}</td>
                      <td className="text-xs text-muted">{p.earnings}</td>
                      <td>
                        <Pill tone={signalTone[p.action_signal as keyof typeof signalTone] ?? 'neutral'}>{p.action_signal}</Pill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
        )}
      </Load>
    </>
  )
}
