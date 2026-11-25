import type { Quote } from '../lib/api'
import { pct, price, tone } from '../lib/format'

/** Scrolling price strip. Pauses with reduced-motion. */
export function Tape({ quotes }: { quotes: Quote[] }) {
  if (quotes.length === 0) return null
  const items = [...quotes, ...quotes]
  return (
    <div className="overflow-hidden border-y border-line py-3.5" aria-label="Latest prices">
      <div className="tape-track">
        {items.map((q, i) => (
          <span key={`${q.symbol}-${i}`} className="mr-9 text-[13px]" aria-hidden={i >= quotes.length}>
            {q.symbol}
            <b className="num mx-1.5">{price(q.price)}</b>
            <span className={`num ${tone(q.change_pct)}`}>{pct(q.change_pct)}</span>
          </span>
        ))}
      </div>
    </div>
  )
}
