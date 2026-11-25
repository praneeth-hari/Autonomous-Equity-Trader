import clsx from 'clsx'
import type { Quote } from '../lib/api'
import { pct, price, tone } from '../lib/format'
import { go } from '../lib/router'
import { Spark } from './Spark'

export function QuoteCard({ q }: { q: Quote }) {
  return (
    <button
      onClick={() => go(`stock/${q.symbol}`)}
      className={clsx(
        'cursor-pointer rounded-2xl border border-line bg-card p-4 text-left transition-all hover:-translate-y-0.5',
        q.change_pct >= 0 ? 'hover:border-brand' : 'hover:border-loss',
      )}
    >
      <div className="text-[15px] font-bold">{q.symbol}</div>
      <div className="mb-1 truncate text-xs text-muted">{q.name}</div>
      <div className="num text-2xl font-semibold tracking-tight">{price(q.price)}</div>
      <div className={clsx('num mb-1 text-[13px]', tone(q.change_pct))}>{pct(q.change_pct)}</div>
      <Spark values={q.spark} up={q.change_pct >= 0} />
    </button>
  )
}
