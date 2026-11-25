import { useEffect, useState } from 'react'

/** State saved in this browser only (localStorage). Bad or missing data falls back to `initial`. */
export function usePersisted<T>(key: string, initial: T, valid: (v: unknown) => v is T): [T, (v: T | ((p: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      if (raw) {
        const parsed: unknown = JSON.parse(raw)
        if (valid(parsed)) return parsed
      }
    } catch {
      /* ignore and use the default */
    }
    return initial
  })
  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value))
  }, [key, value])
  return [value, setValue]
}
