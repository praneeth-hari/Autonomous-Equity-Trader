export const usd = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(v)

export const pct = (v: number, digits = 2) => `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`

export const tone = (v: number) => (v > 0 ? 'text-brand' : v < 0 ? 'text-loss' : 'text-muted')

/** Settings store stop/target either as fractions (0.08) or percents (8); show percents. */
export const asPercent = (v: number) => (Math.abs(v) <= 1 ? Math.abs(v) * 100 : Math.abs(v))
