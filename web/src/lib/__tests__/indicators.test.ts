import { describe, expect, it } from 'vitest'
import { ema, macd, rsi, sma } from '../indicators'

describe('sma', () => {
  it('is null until n values exist, then the plain average', () => {
    expect(sma([1, 2, 3, 4, 5], 3)).toEqual([null, null, 2, 3, 4])
  })
})

describe('ema', () => {
  it('starts at the first value and moves toward new ones', () => {
    const out = ema([10, 10, 10, 20], 3)
    expect(out.slice(0, 3)).toEqual([10, 10, 10])
    expect(out[3]).toBeCloseTo(15, 5) // k = 0.5
  })
})

describe('rsi', () => {
  it('is null before n changes exist', () => {
    const out = rsi([1, 2, 3, 4, 5], 14)
    expect(out.every((v) => v === null)).toBe(true)
  })
  it('is 100 for a series that only rises and 0 for one that only falls', () => {
    const up = Array.from({ length: 30 }, (_, i) => 100 + i)
    const down = Array.from({ length: 30 }, (_, i) => 100 - i)
    expect(rsi(up, 14).at(-1)).toBe(100)
    expect(rsi(down, 14).at(-1)).toBeCloseTo(0, 5)
  })
  it('stays between 0 and 100 on noisy data', () => {
    const noisy = Array.from({ length: 80 }, (_, i) => 100 + Math.sin(i / 3) * 5 + (i % 7))
    for (const v of rsi(noisy, 14)) if (v !== null) expect(v).toBeGreaterThanOrEqual(0), expect(v).toBeLessThanOrEqual(100)
  })
})

describe('macd', () => {
  it('has one value per input and the histogram is macd minus signal', () => {
    const data = Array.from({ length: 60 }, (_, i) => 100 + i * 0.5 + Math.sin(i))
    const m = macd(data)
    expect(m.macd).toHaveLength(60)
    m.hist.forEach((h, i) => expect(h).toBeCloseTo(m.macd[i] - m.signal[i], 10))
  })
  it('is zero for a flat series', () => {
    const m = macd(Array(40).fill(50))
    expect(Math.max(...m.macd.map(Math.abs))).toBe(0)
  })
})
