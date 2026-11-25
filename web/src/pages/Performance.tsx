import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, Empty, Label, Load, OptimisticNote, PageHeader, Pill } from '../components/ui'
import { api } from '../lib/api'
import { pct, tone, usd } from '../lib/format'

const GAIN = 'var(--color-brand)'
const LOSS = 'var(--color-loss)'
const AXIS = { fill: 'var(--color-faint)', fontSize: 11 }
const TOOLTIP = { borderRadius: 12, border: '1px solid var(--color-line)', fontSize: 12, background: 'var(--color-card)', color: 'var(--color-ink)' }
const SECTOR_COLORS = ['var(--color-brand)', '#4f9cf9', '#f0b44c', '#8b7cf6', '#e8734a', '#2fb5b5', '#c26dbc']

function ChartCard({ title, note, children, empty }: { title: string; note?: string; children: ReactNode; empty?: string }) {
  return (
    <Card>
      <h2 className="text-base font-semibold">{title}</h2>
      {note && <p className="mb-2 text-xs text-muted">{note}</p>}
      {empty ? <Empty title="Nothing to chart yet" body={empty} /> : <div className="h-56 w-full">{children}</div>}
    </Card>
  )
}

function Metric({ label, value, enough, hint }: { label: string; value: string; enough: boolean; hint?: string }) {
  return (
    <Card className="p-4">
      <Label>{label}</Label>
      <div className="num text-xl font-medium">{enough ? value : '–'}</div>
      {hint && <div className="mt-1 text-xs text-faint">{hint}</div>}
    </Card>
  )
}

export function Performance() {
  const q = useQuery({ queryKey: ['performance'], queryFn: api.performance, refetchInterval: 60_000 })
  return (
    <>
      <PageHeader eyebrow="Performance" title="How the strategy is doing" />
      <Load q={q}>
        {(d) => {
          const m = d.metrics
          const cs = d.closed_summary
          return (
            <div className="grid gap-4">
              {!d.enough_history && (
                <Card className="border-amber/40 bg-amber/10">
                  <div className="text-sm font-medium text-amber">Not enough history for ratios yet</div>
                  <p className="mt-1 text-sm text-muted">
                    There are {d.sample_days} days of snapshots. Sharpe, Sortino and Calmar are noise below {d.min_days} days, so they are hidden until
                    there is more data.
                  </p>
                </Card>
              )}

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label="Sharpe ratio" value={(m.sharpe_ratio ?? 0).toFixed(2)} enough={d.enough_history} hint="Return per unit of risk" />
                <Metric label="Sortino ratio" value={(m.sortino_ratio ?? 0).toFixed(2)} enough={d.enough_history} hint="Counts only downside swings" />
                <Metric label="Calmar ratio" value={(m.calmar_ratio ?? 0).toFixed(2)} enough={d.enough_history} hint="Return against worst drop" />
                <Metric label="Max drawdown" value={`${(m.max_drawdown_pct ?? 0).toFixed(2)}%`} enough hint="Worst fall from a peak" />
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <ChartCard title="Drawdown" note="How far below its previous high the account has been." empty={d.drawdown.length < 2 ? 'Needs at least two daily snapshots.' : undefined}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={d.drawdown} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke="var(--color-line)" vertical={false} />
                      <XAxis dataKey="date" tick={AXIS} tickLine={false} axisLine={false} minTickGap={40} />
                      <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickFormatter={(v: number) => `${v}%`} />
                      <Tooltip formatter={(v) => `${Number(v).toFixed(2)}%`} contentStyle={TOOLTIP} />
                      <Area type="monotone" dataKey="drawdown_pct" name="Drawdown" stroke={LOSS} strokeWidth={2} fill="var(--color-loss-soft)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Daily returns" note="How many days landed in each return range." empty={d.daily_returns.length === 0 ? 'Needs daily snapshots.' : undefined}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.daily_returns} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke="var(--color-line)" vertical={false} />
                      <XAxis dataKey="bin_center" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={(v: number) => `${v}%`} />
                      <YAxis allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} width={30} />
                      <Tooltip labelFormatter={(_, p) => p?.[0]?.payload?.bin_label ?? ''} contentStyle={TOOLTIP} />
                      <Bar dataKey="count" name="Days" radius={[4, 4, 0, 0]}>
                        {d.daily_returns.map((r) => (
                          <Cell key={r.bin_label} fill={r.sign === 'Positive' ? GAIN : LOSS} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Win and loss by trade" note="Net profit or loss of each closed trade, after costs." empty={d.win_loss.length === 0 ? 'No trade has been closed yet.' : undefined}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.win_loss} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke="var(--color-line)" vertical={false} />
                      <XAxis dataKey="trade_label" tick={AXIS} tickLine={false} axisLine={false} />
                      <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} tickFormatter={(v: number) => `$${v}`} />
                      <Tooltip formatter={(v) => usd(Number(v))} contentStyle={TOOLTIP} />
                      <Bar dataKey="net_pnl" name="Net P/L" radius={[4, 4, 0, 0]}>
                        {d.win_loss.map((r) => (
                          <Cell key={r.trade_id} fill={r.net_pnl >= 0 ? GAIN : LOSS} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Where the money sits" note="Share of the account in each sector, with cash on its own." empty={d.sectors.length === 0 ? 'No snapshot yet.' : undefined}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={d.sectors} dataKey="value" nameKey="sector" innerRadius={50} outerRadius={80} paddingAngle={2}>
                        {d.sectors.map((s, i) => (
                          <Cell key={s.sector} fill={s.sector.toLowerCase().includes('cash') ? 'var(--color-faint)' : SECTOR_COLORS[i % SECTOR_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(v, _n, p) => `${usd(Number(v))} (${p?.payload?.pct?.toFixed?.(1)}%)`} contentStyle={TOOLTIP} />
                      <Legend verticalAlign="bottom" iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                    </PieChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>

              <Card>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-base font-semibold">Closed trades</h2>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <Pill>{cs.total_trades ?? 0} trades</Pill>
                    <Pill tone={(cs.total_pnl ?? 0) >= 0 ? 'ok' : 'bad'}>Net {usd(cs.total_pnl ?? 0)}</Pill>
                    <Pill>Win rate {(cs.win_rate ?? 0).toFixed(0)}%</Pill>
                  </div>
                </div>
                {d.closed_trades.length === 0 ? (
                  <Empty title="No closed trades yet" body="A trade appears here once a buy has been sold, with the reason it was sold." />
                ) : (
                  <table className="w-full text-sm">
                    <thead className="border-b border-line text-xs text-muted">
                      <tr>
                        {['Bought', 'Sold', 'Ticker', 'Entry', 'Exit', 'P/L', 'Why it was sold'].map((h) => (
                          <th key={h} className="py-2 text-left font-normal">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {d.closed_trades.map((t, i) => (
                        <tr key={`${t.ticker}-${t.date_sold}-${i}`} className="border-b border-line last:border-0">
                          <td className="num py-3">{t.date_bought}</td>
                          <td className="num">{t.date_sold}</td>
                          <td className="font-semibold">{t.ticker}</td>
                          <td className="num">{usd(t.entry_price)}</td>
                          <td className="num">{usd(t.exit_price)}</td>
                          <td className={`num ${tone(t.pnl)}`}>
                            {usd(t.pnl)} ({pct(t.pnl_pct)})
                          </td>
                          <td className="text-muted">{t.exit_reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
              <OptimisticNote>{d.label} Figures are net of the 0.2% cost per trade.</OptimisticNote>
            </div>
          )
        }}
      </Load>
    </>
  )
}
