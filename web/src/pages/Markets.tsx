import { useQuery } from '@tanstack/react-query'
import { Load } from '../components/ui'
import { QuoteCard } from '../components/QuoteCard'
import { Tape } from '../components/Tape'
import { api, type Quote } from '../lib/api'
import { pct } from '../lib/format'
import { go } from '../lib/router'
import { treemap } from '../lib/treemap'

function Heatmap({ stocks }: { stocks: Quote[] }) {
  const tiles = treemap(stocks.map((q) => ({ value: q.weight ?? 0, item: q })))
  return (
    <div className="relative h-[360px] overflow-hidden rounded-2xl border border-line" role="group" aria-label="Market heatmap">
      {tiles.map(({ item: q, x, y, w, h }) => {
        const tiny = w < 7 || h < 11 // too small for two lines of text
        return (
          <button
            key={q.symbol}
            onClick={() => go(`stock/${q.symbol}`)}
            title={`${q.symbol} ${pct(q.change_pct)}`}
            className="absolute flex cursor-pointer flex-col items-center justify-center overflow-hidden border-2 border-canvas transition-[filter] hover:brightness-95"
            style={{ left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%`, background: q.change_pct >= 0 ? 'var(--color-tile-up)' : 'var(--color-tile-down)' }}
          >
            <b className={tiny ? 'text-[10px] leading-none' : 'text-[clamp(12px,1.6vw,20px)]'}>{q.symbol}</b>
            {!tiny && <span className="num text-[clamp(10px,1.1vw,13px)] text-muted">{pct(q.change_pct)}</span>}
          </button>
        )
      })}
    </div>
  )
}

export function Markets() {
  const q = useQuery({ queryKey: ['market-overview'], queryFn: api.marketOverview, staleTime: 5 * 60_000, refetchInterval: 5 * 60_000 })
  return (
    <>
      <div className="pb-2 pt-10">
        <h1 className="text-5xl font-extrabold tracking-tight md:text-6xl">Markets</h1>
        <p className="mt-3 max-w-xl text-muted">Indices and your 25-stock universe, with the day's biggest moves. Prices come from Yahoo Finance and may be delayed.</p>
      </div>
      <Load q={q}>
        {(d) => (
          <>
            <Tape quotes={[...d.etfs, ...d.universe]} />
            <section className="pt-10">
              <h2 className="mb-4 text-3xl font-bold tracking-tight">Index ETFs</h2>
              <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
                {d.etfs.map((e) => (
                  <QuoteCard key={e.symbol} q={e} />
                ))}
              </div>
            </section>
            <section className="pt-10">
              <h2 className="mb-4 text-3xl font-bold tracking-tight">Top movers</h2>
              <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-5">
                {d.movers.map((m) => (
                  <QuoteCard key={m.symbol} q={m} />
                ))}
              </div>
            </section>
            <section className="pt-10">
              <h2 className="text-3xl font-bold tracking-tight">Market heatmap</h2>
              <p className="mb-4 mt-1 text-muted">Tile size follows dollar volume (price times shares traded), colour follows the day's move. Click a tile to open it.</p>
              <Heatmap stocks={d.universe} />
            </section>
          </>
        )}
      </Load>
    </>
  )
}
