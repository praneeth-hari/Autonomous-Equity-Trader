/** Small trend line with a soft fill. Colour follows `up` (the day's move) when given, else the line's own direction. */
export function Spark({ values, height = 46, up }: { values: number[]; height?: number; up?: boolean }) {
  if (values.length < 2) return <div style={{ height }} />
  const w = 200
  const min = Math.min(...values)
  const max = Math.max(...values)
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, height - 3 - ((v - min) / (max - min || 1)) * (height - 6)])
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('')
  const isUp = up ?? values[values.length - 1] >= values[0]
  const color = isUp ? 'var(--color-brand)' : 'var(--color-loss)'
  return (
    <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} preserveAspectRatio="none" aria-hidden="true">
      <path d={`${d}L${w},${height}L0,${height}Z`} fill={color} opacity={0.12} />
      <path d={d} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
