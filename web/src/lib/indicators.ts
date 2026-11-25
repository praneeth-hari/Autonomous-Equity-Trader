// Indicators computed in the browser from the same bars that are drawn, so nothing extra is fetched.

/** Simple moving average. Entries before `n` bars exist are null. */
export function sma(values: number[], n: number): (number | null)[] {
  return values.map((_, i) => (i < n - 1 ? null : values.slice(i - n + 1, i + 1).reduce((s, v) => s + v, 0) / n))
}

/** Exponential moving average seeded with the first value. */
export function ema(values: number[], n: number): number[] {
  const k = 2 / (n + 1)
  const out: number[] = []
  values.forEach((v, i) => out.push(i === 0 ? v : v * k + out[i - 1] * (1 - k)))
  return out
}

/** Wilder's RSI. Entries before `n` changes exist are null. */
export function rsi(values: number[], n = 14): (number | null)[] {
  const out: (number | null)[] = values.map(() => null)
  if (values.length <= n) return out
  let gain = 0
  let loss = 0
  for (let i = 1; i <= n; i++) {
    const d = values[i] - values[i - 1]
    if (d >= 0) gain += d
    else loss -= d
  }
  gain /= n
  loss /= n
  const toRsi = () => (loss === 0 ? 100 : 100 - 100 / (1 + gain / loss))
  out[n] = toRsi()
  for (let i = n + 1; i < values.length; i++) {
    const d = values[i] - values[i - 1]
    gain = (gain * (n - 1) + Math.max(d, 0)) / n
    loss = (loss * (n - 1) + Math.max(-d, 0)) / n
    out[i] = toRsi()
  }
  return out
}

export interface Macd {
  macd: number[]
  signal: number[]
  hist: number[]
}

export function macd(values: number[], fast = 12, slow = 26, sig = 9): Macd {
  const f = ema(values, fast)
  const s = ema(values, slow)
  const line = f.map((v, i) => v - s[i])
  const signal = ema(line, sig)
  return { macd: line, signal, hist: line.map((v, i) => v - signal[i]) }
}
