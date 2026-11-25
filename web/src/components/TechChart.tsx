import { useMemo, useState, type MouseEvent } from 'react'
import type { Bar } from '../lib/api'
import { barTime, compact, price } from '../lib/format'
import { macd as calcMacd, rsi as calcRsi, sma } from '../lib/indicators'

const W = 1000
const X0 = 8
const X1 = W - 62
const PRICE = { top: 8, h: 320 }
const VOL = { top: 360, h: 70 }
const RSI = { top: 452, h: 80 }
const MACD = { top: 556, h: 90 }
const H = 690
const UP = 'var(--color-brand)'
const DOWN = 'var(--color-loss)'
const MA_COLOR = '#f0a02e'
const SPY_COLOR = '#7a5af8'
const MACD_COLOR = '#3b82f6'

export interface TechChartProps {
  bars: Bar[]
  spy?: { t: number; c: number }[]
  interval: string
  mode: 'candles' | 'line'
  showSpy: boolean
  showMa: boolean
}

export function TechChart({ bars, spy, interval, mode, showSpy, showMa }: TechChartProps) {
  const [hover, setHover] = useState<number | null>(null)
  const n = bars.length

  const calc = useMemo(() => {
    const closes = bars.map((b) => b.c)
    const base = bars[0]?.c ?? 1
    const spyMap = new Map((spy ?? []).map((s) => [s.t, s.c]))
    const firstSpy = spy?.[0]?.c
    // SPY is rescaled so it starts at the same price as the stock: only the shape is compared.
    const spyLine = bars.map((b) => (firstSpy && spyMap.has(b.t) ? (spyMap.get(b.t)! / firstSpy) * base : null))
    return { closes, ma: sma(closes, 20), rsi: calcRsi(closes, 14), macd: calcMacd(closes), spyLine }
  }, [bars, spy])

  if (n < 2) return <p className="py-8 text-center text-sm text-muted">Not enough bars to draw this chart.</p>

  const step = (X1 - X0) / n
  const xAt = (i: number) => X0 + step * (i + 0.5)

  const pool: number[] = mode === 'candles' ? bars.flatMap((b) => [b.h, b.l]) : calc.closes
  if (showMa) pool.push(...(calc.ma.filter((v) => v != null) as number[]))
  if (showSpy) pool.push(...(calc.spyLine.filter((v) => v != null) as number[]))
  const pMin = Math.min(...pool)
  const pMax = Math.max(...pool)
  const pad = (pMax - pMin) * 0.06 || 1
  const lo = pMin - pad
  const hi = pMax + pad
  const yP = (v: number) => PRICE.top + ((hi - v) / (hi - lo)) * PRICE.h

  const vMax = Math.max(...bars.map((b) => b.v), 1)
  const yV = (v: number) => VOL.top + VOL.h - (v / vMax) * VOL.h
  const yR = (v: number) => RSI.top + ((100 - v) / 100) * RSI.h
  const mAbs = Math.max(...calc.macd.hist.map(Math.abs), ...calc.macd.macd.map(Math.abs), 1e-9)
  const yM = (v: number) => MACD.top + MACD.h / 2 - (v / mAbs) * (MACD.h / 2 - 4)

  const path = (vals: (number | null)[], y: (v: number) => number) => {
    let d = ''
    let pen = false
    vals.forEach((v, i) => {
      if (v == null) {
        pen = false
        return
      }
      d += `${pen ? 'L' : 'M'}${xAt(i).toFixed(1)},${y(v).toFixed(1)}`
      pen = true
    })
    return d
  }

  const ticks = [0, 1, 2, 3, 4].map((k) => lo + ((hi - lo) * k) / 4)
  const timeTicks = [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1]

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - r.left) / r.width) * W
    setHover(Math.max(0, Math.min(n - 1, Math.floor((x - X0) / step))))
  }

  const hb = hover != null ? bars[hover] : null
  const hr = hover != null ? calc.rsi[hover] : null

  return (
    <div className="relative">
      <div className="pointer-events-none absolute left-2 top-1 z-10 min-h-[22px] rounded-lg bg-card/90 px-2 py-1 text-xs text-muted">
        {hb ? (
          <span className="num">
            {barTime(hb.t, interval)} &nbsp;O {price(hb.o)} &nbsp;H {price(hb.h)} &nbsp;L {price(hb.l)} &nbsp;C {price(hb.c)} &nbsp;Vol {compact(hb.v)}
            {hr != null && <> &nbsp;RSI {hr.toFixed(1)}</>}
          </span>
        ) : (
          'Hover the chart for exact values'
        )}
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label={`${mode === 'candles' ? 'Candlestick' : 'Line'} chart with volume, RSI and MACD`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        className="block"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={X0} x2={X1} y1={yP(t)} y2={yP(t)} stroke="var(--color-line)" />
            <text x={X1 + 6} y={yP(t) + 4} fontSize="11" fill="var(--color-faint)">
              {price(t)}
            </text>
          </g>
        ))}

        {mode === 'candles' ? (
          bars.map((b, i) => {
            const up = b.c >= b.o
            const color = up ? UP : DOWN
            const top = yP(Math.max(b.o, b.c))
            return (
              <g key={b.t}>
                <line x1={xAt(i)} x2={xAt(i)} y1={yP(b.h)} y2={yP(b.l)} stroke={color} />
                <rect x={xAt(i) - step * 0.32} y={top} width={step * 0.64} height={Math.max(1.2, Math.abs(yP(b.o) - yP(b.c)))} fill={color} />
              </g>
            )
          })
        ) : (
          <path d={path(calc.closes, yP)} fill="none" stroke={UP} strokeWidth={2} strokeLinejoin="round" />
        )}
        {showMa && <path d={path(calc.ma, yP)} fill="none" stroke={MA_COLOR} strokeWidth={1.6} />}
        {showSpy && <path d={path(calc.spyLine, yP)} fill="none" stroke={SPY_COLOR} strokeWidth={2} strokeDasharray="5 4" />}

        <text x={X0} y={VOL.top - 8} fontSize="10.5" letterSpacing="1" fill="var(--color-faint)">
          VOLUME
        </text>
        {bars.map((b, i) => (
          <rect key={b.t} x={xAt(i) - step * 0.35} y={yV(b.v)} width={step * 0.7} height={VOL.top + VOL.h - yV(b.v)} fill={b.c >= b.o ? UP : DOWN} opacity={0.55} />
        ))}
        <text x={X1 + 6} y={VOL.top + 10} fontSize="11" fill="var(--color-faint)">
          {compact(vMax)}
        </text>

        <text x={X0} y={RSI.top - 8} fontSize="10.5" letterSpacing="1" fill="var(--color-faint)">
          RSI 14
        </text>
        <rect x={X0} y={RSI.top} width={X1 - X0} height={RSI.h} fill="var(--color-chip)" rx={6} />
        <line x1={X0} x2={X1} y1={yR(70)} y2={yR(70)} stroke={DOWN} strokeDasharray="3 4" opacity={0.6} />
        <line x1={X0} x2={X1} y1={yR(30)} y2={yR(30)} stroke={UP} strokeDasharray="3 4" opacity={0.6} />
        <path d={path(calc.rsi, yR)} fill="none" stroke="var(--color-ink)" strokeWidth={1.5} />
        <text x={X1 + 6} y={yR(70) + 4} fontSize="11" fill="var(--color-faint)">
          70
        </text>
        <text x={X1 + 6} y={yR(30) + 4} fontSize="11" fill="var(--color-faint)">
          30
        </text>

        <text x={X0} y={MACD.top - 8} fontSize="10.5" letterSpacing="1" fill="var(--color-faint)">
          MACD 12 · 26 · 9
        </text>
        <rect x={X0} y={MACD.top} width={X1 - X0} height={MACD.h} fill="var(--color-chip)" rx={6} />
        {calc.macd.hist.map((v, i) => (
          <rect
            key={bars[i].t}
            x={xAt(i) - step * 0.35}
            y={v >= 0 ? yM(v) : yM(0)}
            width={step * 0.7}
            height={Math.abs(yM(v) - yM(0))}
            fill={v >= 0 ? UP : DOWN}
            opacity={0.5}
          />
        ))}
        <path d={path(calc.macd.macd, yM)} fill="none" stroke={MACD_COLOR} strokeWidth={1.6} />
        <path d={path(calc.macd.signal, yM)} fill="none" stroke={MA_COLOR} strokeWidth={1.6} />

        {timeTicks.map((i) => (
          <text key={i} x={xAt(i)} y={H - 8} fontSize="11" textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'} fill="var(--color-faint)">
            {barTime(bars[i].t, interval)}
          </text>
        ))}

        {hover != null && <line x1={xAt(hover)} x2={xAt(hover)} y1={PRICE.top} y2={MACD.top + MACD.h} stroke="var(--color-faint)" strokeDasharray="3 3" />}
      </svg>
    </div>
  )
}
