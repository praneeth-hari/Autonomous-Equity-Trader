import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { useEffect, useState } from 'react'
import { PriceArea } from '../components/PriceArea'
import { TechChart } from '../components/TechChart'
import { Card, Load, Pill } from '../components/ui'
import { api, INTERVALS, type Interval } from '../lib/api'
import { compact, pct, price, tone } from '../lib/format'
import { SYMBOL_RE } from '../lib/router'

function Chip({ on, children, onClick }: { on: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={on}
      className={clsx(
        'cursor-pointer rounded-lg border px-3 py-1 text-xs transition-colors',
        on ? 'border-ink bg-ink text-canvas' : 'border-line bg-card hover:bg-chip',
      )}
    >
      {children}
    </button>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10.5px] tracking-[0.1em] text-faint">{label}</div>
      <div className="num text-[15px] font-semibold">{value}</div>
    </div>
  )
}

const sentimentDot = { positive: 'bg-brand', neutral: 'bg-faint', negative: 'bg-loss' } as const

export function Stock({ symbol }: { symbol?: string }) {
  const sym = (symbol ?? localStorage.getItem('pt-last-stock') ?? 'AAPL').toUpperCase()
  const valid = SYMBOL_RE.test(sym)
  const [interval, setIntervalValue] = useState<Interval>('1day')
  const [mode, setMode] = useState<'candles' | 'line'>('candles')
  const [showSpy, setShowSpy] = useState(false)
  const [showMa, setShowMa] = useState(true)

  useEffect(() => {
    if (valid) localStorage.setItem('pt-last-stock', sym)
  }, [sym, valid])

  const stock = useQuery({ queryKey: ['stock', sym], queryFn: () => api.stock(sym), enabled: valid, staleTime: 5 * 60_000 })
  const hero = useQuery({ queryKey: ['history', sym, '1day', false], queryFn: () => api.history(sym, '1day', false), enabled: valid, staleTime: 5 * 60_000 })
  const tech = useQuery({
    queryKey: ['history', sym, interval, showSpy],
    queryFn: () => api.history(sym, interval, showSpy),
    enabled: valid,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  })

  if (!valid) {
    return (
      <Card className="mt-10">
        <div className="font-medium text-loss">'{sym}' is not a valid ticker</div>
        <p className="mt-1 text-sm text-muted">Use the search box and type a symbol such as AAPL.</p>
      </Card>
    )
  }

  return (
    <>
      <Load q={stock}>
        {(s) => (
          <div className="pt-10">
            <div className="flex flex-wrap items-center gap-2">
              {s.model ? (
                <Pill tone={s.model.zone === 'buy zone' ? 'ok' : s.model.zone === 'exit zone' ? 'bad' : 'neutral'}>
                  Model score {s.model.probability.toFixed(2)} · {s.model.zone} · stored {s.model.date}
                </Pill>
              ) : (
                <Pill>{s.in_universe ? 'No stored model score yet' : 'Not scored: outside the 25 stocks'}</Pill>
              )}
            </div>
            <h1 className="mt-3 text-4xl font-extrabold tracking-tight">
              {s.name} <span className="text-xl font-medium tracking-normal text-faint">{s.symbol}</span>
            </h1>
            <div className="mt-2 flex flex-wrap items-baseline gap-3">
              <span className="num text-6xl font-bold tracking-tight">{price(s.price)}</span>
              <span className="text-sm text-faint">USD</span>
            </div>
            <div className={clsx('num text-sm', tone(s.change))}>
              {s.change >= 0 ? '+' : ''}
              {price(s.change)} ({pct(s.change_pct)}) <span className="text-faint">on the last close, {new Date(s.as_of * 1000).toLocaleDateString()}</span>
            </div>

            <div className="mt-2">
              <Load q={hero}>{(h) => <PriceArea bars={h.bars} interval="1day" height={240} />}</Load>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-4 border-t border-line pt-3 sm:grid-cols-5">
              <Stat label="OPEN" value={price(s.open)} />
              <Stat label="PREV CLOSE" value={price(s.prev_close)} />
              <Stat label="VOLUME" value={compact(s.volume)} />
              <Stat label="52W HIGH" value={price(s.week52_high)} />
              <Stat label="52W LOW" value={price(s.week52_low)} />
            </div>
          </div>
        )}
      </Load>

      <section className="pt-12">
        <h2 className="text-3xl font-bold tracking-tight">Technical analysis</h2>
        <p className="mb-4 mt-1 max-w-2xl text-muted">Candles with a 20-bar average, volume, RSI and MACD, all computed from the same price history.</p>
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <b className="text-xl">{sym}</b>
              {showSpy && sym !== 'SPY' && <b className="text-[#7a5af8]">vs SPY</b>}
              <Pill>{interval} · {tech.data?.bars.length ?? '–'} bars</Pill>
            </div>
            <div className="text-xs text-muted">
              <span className="text-brand">▬</span> up &nbsp;<span className="text-loss">▬</span> down &nbsp;<span className="text-[#f0a02e]">▬</span> 20-bar average
              {showSpy && sym !== 'SPY' && (
                <>
                  &nbsp;<span className="text-[#7a5af8]">▬</span> SPY
                </>
              )}
            </div>
          </div>
          <div className="my-3 flex flex-wrap items-center gap-1.5">
            {INTERVALS.map((i) => (
              <Chip key={i} on={interval === i} onClick={() => setIntervalValue(i)}>
                {i}
              </Chip>
            ))}
            <span className="mx-2 h-4 w-px bg-line" />
            <Chip on={mode === 'candles'} onClick={() => setMode('candles')}>
              CANDLES
            </Chip>
            <Chip on={mode === 'line'} onClick={() => setMode('line')}>
              LINE
            </Chip>
            <Chip on={showMa} onClick={() => setShowMa(!showMa)}>
              AVERAGE
            </Chip>
            <Chip on={showSpy} onClick={() => setShowSpy(!showSpy)}>
              SPY OVERLAY
            </Chip>
          </div>
          {showSpy && <p className="mb-2 text-xs text-muted">The SPY line is rescaled to start at the same price, so you compare shape and direction, not level.</p>}
          <Load q={tech}>{(h) => <TechChart bars={h.bars} spy={h.spy} interval={interval} mode={mode} showSpy={showSpy} showMa={showMa} />}</Load>
          <p className="mt-2 text-xs text-faint">Prices from Yahoo Finance, adjusted for splits and dividends, and shown in your local time. Intraday bars cover only recent days.</p>
        </Card>
      </section>

      <Load q={stock}>
        {(s) => (
          <section className="pt-12">
            <h2 className="text-3xl font-bold tracking-tight">Related headlines</h2>
            {s.headlines.length === 0 ? (
              <p className="mt-3 text-sm text-muted">No headlines came back from Yahoo Finance right now.</p>
            ) : (
              <ul className="mt-3">
                {s.headlines.map((h) => (
                  <li key={h.title} className="flex items-start gap-3 border-t border-line py-4 text-[17px] font-semibold">
                    <span className={clsx('mt-2.5 size-2 shrink-0 rounded-full', sentimentDot[h.sentiment])} title={`Sentiment: ${h.sentiment}`} />
                    <span>
                      {h.title}
                      <span className="block text-[13px] font-normal text-muted">Sentiment: {h.sentiment}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </Load>
    </>
  )
}
