import clsx from 'clsx'
import { ChevronDown, Moon, Search, Sun } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTheme } from '../lib/theme'

export const PRIMARY = [
  { id: 'dashboard', label: 'DASHBOARD' },
  { id: 'markets', label: 'MARKETS' },
  { id: 'watchlist', label: 'WATCHLIST' },
  { id: 'stock', label: 'STOCK' },
] as const

export const ACCOUNT = [
  { id: 'overview', label: 'Account overview' },
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'trades', label: 'Trades' },
  { id: 'performance', label: 'Performance' },
  { id: 'signals', label: 'Signals' },
  { id: 'backtests', label: 'Backtests' },
  { id: 'chat', label: 'Chatbot' },
] as const

const lastStock = () => localStorage.getItem('pt-last-stock') ?? 'AAPL'

export function TopNav({ current, onSearch }: { current: string; onSearch: () => void }) {
  const { theme, toggle } = useTheme()
  const [menu, setMenu] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const accountActive = ACCOUNT.some((a) => a.id === current)

  useEffect(() => {
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setMenu(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas/90 backdrop-blur">
      <div className="mx-auto flex h-[60px] max-w-6xl items-center gap-3 px-5 md:gap-4 md:px-8 lg:gap-5">
        <a href="#dashboard" className="flex shrink-0 items-center gap-2.5 whitespace-nowrap text-sm font-bold tracking-[0.12em]">
          <span className="relative block size-5 rounded-md bg-brand">
            <span className="absolute inset-[5px] rounded-sm bg-canvas" />
          </span>
          PAPER TRADER
        </a>

        <nav aria-label="Pages" className="hidden flex-1 items-center justify-center gap-5 md:flex lg:gap-7">
          {PRIMARY.map((p) => (
            <a
              key={p.id}
              href={p.id === 'stock' ? `#stock/${lastStock()}` : `#${p.id}`}
              aria-current={current === p.id ? 'page' : undefined}
              className={clsx(
                'border-b-2 py-1.5 text-[12.5px] tracking-[0.1em] transition-colors',
                current === p.id ? 'border-ink text-ink' : 'border-transparent text-muted hover:text-ink',
              )}
            >
              {p.label}
            </a>
          ))}
          <div ref={box} className="relative">
            <button
              onClick={() => setMenu(!menu)}
              aria-expanded={menu}
              aria-haspopup="true"
              className={clsx(
                'flex cursor-pointer items-center gap-1 border-b-2 py-1.5 text-[12.5px] tracking-[0.1em] transition-colors',
                accountActive ? 'border-ink text-ink' : 'border-transparent text-muted hover:text-ink',
              )}
            >
              ACCOUNT <ChevronDown size={13} />
            </button>
            {menu && (
              <div className="absolute left-1/2 top-full mt-2 w-48 -translate-x-1/2 rounded-xl border border-line bg-card p-1.5 shadow-lg">
                {ACCOUNT.map((a) => (
                  <a
                    key={a.id}
                    href={`#${a.id}`}
                    onClick={() => setMenu(false)}
                    className={clsx('block rounded-lg px-3 py-2 text-sm hover:bg-chip', current === a.id && 'bg-brand-soft text-brand-ink')}
                  >
                    {a.label}
                  </a>
                ))}
              </div>
            )}
          </div>
        </nav>

        <button
          onClick={onSearch}
          className="ml-auto flex min-w-36 cursor-pointer lg:min-w-40 items-center gap-2 rounded-xl border border-line bg-chip px-3 py-2 text-[13px] text-faint md:ml-0"
          aria-label="Search tickers"
        >
          <Search size={14} /> Search <kbd className="num ml-auto text-[11px]">Ctrl K</kbd>
        </button>
        <button
          onClick={toggle}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          className="flex size-9 cursor-pointer items-center justify-center rounded-xl border border-line bg-card"
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>
        <a href="#health" className="hidden rounded-xl border border-line bg-card px-3.5 py-2 text-[12.5px] tracking-[0.06em] xl:block">
          STATUS
        </a>
      </div>

      <nav aria-label="Pages (small screens)" className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 pb-2 md:hidden">
        {[...PRIMARY.map((p) => ({ id: p.id, label: p.label[0] + p.label.slice(1).toLowerCase() })), ...ACCOUNT].map((p) => (
          <a
            key={p.id}
            href={p.id === 'stock' ? `#stock/${lastStock()}` : `#${p.id}`}
            className={clsx('shrink-0 rounded-full px-3 py-1.5 text-sm', current === p.id ? 'bg-brand-soft text-brand-ink' : 'text-muted')}
          >
            {p.label}
          </a>
        ))}
      </nav>
    </header>
  )
}
