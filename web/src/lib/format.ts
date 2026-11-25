export const usd = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(v)

export const pct = (v: number, digits = 2) => `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`

export const tone = (v: number) => (v > 0 ? 'text-brand' : v < 0 ? 'text-loss' : 'text-muted')

/** Settings store stop/target either as fractions (0.08) or percents (8); show percents. */
export const asPercent = (v: number) => (Math.abs(v) <= 1 ? Math.abs(v) * 100 : Math.abs(v))

export const price = (v: number) => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const compact = (v: number) =>
  v >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : String(Math.round(v))

/** Axis label for a bar time: clock time for intraday intervals, date otherwise. */
export function barTime(t: number, interval: string): string {
  const d = new Date(t * 1000)
  const intraday = ['5min', '15min', '30min', '1h', '4h'].includes(interval)
  return intraday
    ? d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: interval === '1month' || interval === '1week' ? '2-digit' : undefined })
}
