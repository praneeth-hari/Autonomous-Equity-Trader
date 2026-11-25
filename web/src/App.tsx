import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import { Activity, Briefcase, ChartLine, LayoutDashboard, ListChecks, Radar } from 'lucide-react'
import { useEffect, useState, type ComponentType } from 'react'
import { Backtests } from './pages/Backtests'
import { Health } from './pages/Health'
import { Overview } from './pages/Overview'
import { Portfolio } from './pages/Portfolio'
import { Signals } from './pages/Signals'
import { Trades } from './pages/Trades'

const pages = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, view: Overview },
  { id: 'portfolio', label: 'Portfolio', icon: Briefcase, view: Portfolio },
  { id: 'trades', label: 'Trades', icon: ListChecks, view: Trades },
  { id: 'signals', label: 'Signals', icon: Radar, view: Signals },
  { id: 'backtests', label: 'Backtests', icon: ChartLine, view: Backtests },
  { id: 'health', label: 'Health', icon: Activity, view: Health },
] satisfies { id: string; label: string; icon: ComponentType<{ size?: number }>; view: ComponentType }[]

const fromHash = () => pages.find((p) => `#${p.id}` === window.location.hash)?.id ?? 'overview'

export default function App() {
  const [current, setCurrent] = useState(fromHash)
  useEffect(() => {
    const onHash = () => setCurrent(fromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const page = pages.find((p) => p.id === current) ?? pages[0]
  const View = page.view

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 border-r border-line bg-white p-4 md:block">
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <div className="size-6 rounded-lg bg-brand" />
          <span className="font-semibold">Paper Trader</span>
        </div>
        <nav aria-label="Pages" className="flex flex-col gap-0.5">
          {pages.map(({ id, label, icon: Icon }) => (
            <a
              key={id}
              href={`#${id}`}
              aria-current={id === current ? 'page' : undefined}
              className={clsx(
                'flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition-colors',
                id === current ? 'bg-brand-soft font-medium text-brand-ink' : 'text-slate-600 hover:bg-slate-100',
              )}
            >
              <Icon size={17} />
              {label}
            </a>
          ))}
        </nav>
        <p className="mt-6 px-3 text-xs leading-relaxed text-faint">Paper trading only. No real money. Nothing here is financial advice.</p>
      </aside>

      <main className="min-w-0 flex-1 p-6 md:p-8">
        <nav aria-label="Pages" className="mb-4 flex gap-1 overflow-x-auto md:hidden">
          {pages.map(({ id, label }) => (
            <a key={id} href={`#${id}`} className={clsx('rounded-full px-3 py-1.5 text-sm', id === current ? 'bg-brand-soft text-brand-ink' : 'text-slate-600')}>
              {label}
            </a>
          ))}
        </nav>
        <div className="mx-auto max-w-5xl">
          <AnimatePresence mode="wait">
            <motion.div key={page.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
              <View />
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  )
}
