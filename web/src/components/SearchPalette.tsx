import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api'
import { go, SYMBOL_RE } from '../lib/router'

/** Ctrl+K ticker search. Pick a suggestion or type any symbol and press Enter. */
export function SearchPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const overview = useQuery({ queryKey: ['market-overview'], queryFn: api.marketOverview, staleTime: 5 * 60_000, enabled: open })

  useEffect(() => {
    if (open) {
      setText('')
      setError('')
      input.current?.focus()
    }
  }, [open])

  const matches = useMemo(() => {
    const all = [...(overview.data?.etfs ?? []), ...(overview.data?.universe ?? [])]
    const q = text.trim().toLowerCase()
    return (q ? all.filter((s) => s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)) : all).slice(0, 8)
  }, [overview.data, text])

  if (!open) return null

  const open_ = (symbol: string) => {
    const s = symbol.trim().toUpperCase()
    if (!SYMBOL_RE.test(s)) {
      setError('Enter a ticker such as AAPL.')
      return
    }
    go(`stock/${s}`)
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[15vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Search tickers"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
    >
      <div className="w-full max-w-lg overflow-hidden rounded-2xl border border-line bg-card shadow-xl">
        <div className="flex items-center gap-2 border-b border-line px-4">
          <Search size={16} className="text-faint" />
          <input
            ref={input}
            autoFocus
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              setError('')
            }}
            onKeyDown={(e) => e.key === 'Enter' && open_(matches[0] ? matches[0].symbol : text)}
            placeholder="Search any ticker..."
            aria-label="Ticker"
            className="h-12 flex-1 bg-transparent text-sm outline-none"
          />
          <kbd className="num text-xs text-faint">Esc</kbd>
        </div>
        {error && <p className="px-4 pt-2 text-xs text-loss">{error}</p>}
        <ul className="max-h-72 overflow-y-auto p-2">
          {matches.map((s) => (
            <li key={s.symbol}>
              <button
                onClick={() => open_(s.symbol)}
                className="flex w-full cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-left text-sm hover:bg-chip"
              >
                <span>
                  <b>{s.symbol}</b> <span className="text-muted">{s.name}</span>
                </span>
                <span className="num text-muted">{s.price.toFixed(2)}</span>
              </button>
            </li>
          ))}
          {matches.length === 0 && text.trim() && (
            <li className="px-3 py-2 text-sm text-muted">
              Press Enter to open <b>{text.trim().toUpperCase()}</b>
            </li>
          )}
        </ul>
      </div>
    </div>
  )
}
