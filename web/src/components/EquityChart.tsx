import { Area, AreaChart, CartesianGrid, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CurvePoint } from '../lib/api'
import { usd } from '../lib/format'

export function EquityChart({ data }: { data: CurvePoint[] }) {
  return (
    <div className="h-64 w-full" role="img" aria-label="Strategy equity curve compared with SPY buy-and-hold">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#eef0f3" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: '#8a909c', fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={40} />
          <YAxis
            tick={{ fill: '#8a909c', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={62}
            domain={['auto', 'auto']}
            tickFormatter={(v: number) => usd(v).replace('.00', '')}
          />
          <Tooltip
            formatter={(v) => usd(Number(v))}
            contentStyle={{ borderRadius: 12, border: '1px solid #e6e8ec', fontSize: 12 }}
          />
          <Area type="monotone" dataKey="My Portfolio" name="Strategy" stroke="#12a066" strokeWidth={2.2} fill="#e7f7ef" />
          <Line type="monotone" dataKey="SPY Benchmark" name="SPY buy-and-hold" stroke="#b3b9c4" strokeWidth={1.8} strokeDasharray="5 4" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
