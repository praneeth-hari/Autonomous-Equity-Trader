import { useEffect, useState } from 'react'

export interface Route {
  name: string
  param?: string
}

function read(): Route {
  const [name, ...rest] = window.location.hash.replace(/^#\/?/, '').split('/')
  const param = decodeURIComponent(rest.join('/')) || undefined
  return { name: name || 'dashboard', param }
}

/** Tiny hash router: #markets, #stock/AAPL. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(read)
  useEffect(() => {
    const on = () => setRoute(read())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export const go = (path: string) => {
  window.location.hash = path
}

export const SYMBOL_RE = /^[A-Za-z0-9][A-Za-z0-9.-]{0,9}$/
