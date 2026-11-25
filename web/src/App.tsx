import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState, type ComponentType } from 'react'
import { SearchPalette } from './components/SearchPalette'
import { TopNav } from './components/TopNav'
import { useRoute } from './lib/router'
import { Approvals } from './pages/Approvals'
import { Backtests } from './pages/Backtests'
import { Chat } from './pages/Chat'
import { Dashboard } from './pages/Dashboard'
import { Health } from './pages/Health'
import { Markets } from './pages/Markets'
import { Overview } from './pages/Overview'
import { Performance } from './pages/Performance'
import { Portfolio } from './pages/Portfolio'
import { Signals } from './pages/Signals'
import { Stock } from './pages/Stock'
import { Trades } from './pages/Trades'
import { Watchlist } from './pages/Watchlist'

const pages: Record<string, ComponentType<{ param?: string }>> = {
  dashboard: Dashboard,
  markets: Markets,
  watchlist: Watchlist,
  stock: ({ param }) => <Stock symbol={param} />,
  overview: Overview,
  portfolio: Portfolio,
  trades: Trades,
  performance: Performance,
  signals: Signals,
  approvals: Approvals,
  backtests: Backtests,
  health: Health,
  chat: Chat,
}

export default function App() {
  const route = useRoute()
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearching(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const name = route.name in pages ? route.name : 'dashboard'
  const View = pages[name]

  return (
    <div className="min-h-screen">
      <TopNav current={name} onSearch={() => setSearching(true)} />
      <SearchPalette open={searching} onClose={() => setSearching(false)} />
      <main className="mx-auto max-w-6xl px-5 pb-20 md:px-8">
        <AnimatePresence mode="wait">
          <motion.div key={`${name}/${route.param ?? ''}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
            {['overview', 'portfolio', 'trades', 'performance', 'signals', 'approvals', 'backtests', 'health', 'chat'].includes(name) ? (
              <div className="pt-8">
                <View param={route.param} />
              </div>
            ) : (
              <View param={route.param} />
            )}
          </motion.div>
        </AnimatePresence>
      </main>
      <footer className="border-t border-line py-8 text-center text-xs text-faint">Paper trading only. No real money. Nothing here is financial advice.</footer>
    </div>
  )
}
