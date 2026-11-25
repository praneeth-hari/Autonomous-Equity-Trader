import { describe, expect, it } from 'vitest'
import { treemap } from '../treemap'

const items = [5, 3, 2, 2, 1, 1].map((value, i) => ({ value, item: `T${i}` }))

describe('treemap', () => {
  it('fills the whole area with no gaps', () => {
    const area = treemap(items).reduce((s, r) => s + r.w * r.h, 0)
    expect(area).toBeCloseTo(100 * 100, 4)
  })
  it('gives each tile an area proportional to its value', () => {
    const total = items.reduce((s, i) => s + i.value, 0)
    for (const r of treemap(items)) {
      const value = items.find((i) => i.item === r.item)!.value
      expect((r.w * r.h) / (100 * 100)).toBeCloseTo(value / total, 4)
    }
  })
  it('keeps every tile inside the box', () => {
    for (const r of treemap(items)) {
      expect(r.x).toBeGreaterThanOrEqual(0)
      expect(r.y).toBeGreaterThanOrEqual(0)
      expect(r.x + r.w).toBeLessThanOrEqual(100.0001)
      expect(r.y + r.h).toBeLessThanOrEqual(100.0001)
    }
  })
  it('ignores zero-value items and handles empty input', () => {
    expect(treemap([])).toEqual([])
    expect(treemap([{ value: 0, item: 'x' }])).toEqual([])
    expect(treemap([{ value: 4, item: 'only' }])).toEqual([{ item: 'only', x: 0, y: 0, w: 100, h: 100 }])
  })
})
