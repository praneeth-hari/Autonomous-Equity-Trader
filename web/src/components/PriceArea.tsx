import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Bar } from '../lib/api'
import { barTime, price } from '../lib/format'

/** Plain price line with a soft fill, used for the hero of the Dashboard and Stock pages. */
export function PriceArea({ bars, interval = '1day', height = 220 }: { bars: Bar[]; interval?: string; height?: number }) {
  const up = bars.length > 1 && bars[bars.length - 1].c >= bars[0].c
  const color = up ? 'var(--color-brand)' : 'var(--color-loss)'
  return (
    <div style={{ height }} className="w-full" role="img" aria-label="Price chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={bars} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--color-line)" vertical={false} />
          <XAxis dataKey="t" tick={{ fill: 'var(--color-faint)', fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={60} tickFormatter={(t: number) => barTime(t, interval)} />
          <YAxis orientation="right" domain={['auto', 'auto']} tick={{ fill: 'var(--color-faint)', fontSize: 11 }} tickLine={false} axisLine={false} width={52} tickFormatter={(v: number) => price(v)} />
          <Tooltip
            formatter={(v) => price(Number(v))}
            labelFormatter={(t) => barTime(Number(t), interval)}
            contentStyle={{ borderRadius: 12, border: '1px solid var(--color-line)', fontSize: 12, background: 'var(--color-card)', color: 'var(--color-ink)' }}
          />
          <Area type="monotone" dataKey="c" name="Price" stroke={color} strokeWidth={2.2} fill={color} fillOpacity={0.1} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
