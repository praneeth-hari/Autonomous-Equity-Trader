import type { UseQueryResult } from '@tanstack/react-query'
import clsx from 'clsx'
import type { ReactNode } from 'react'

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx('rounded-2xl border border-line bg-white p-5', className)}>{children}</div>
}

export function Label({ children }: { children: ReactNode }) {
  return <div className="text-xs text-muted">{children}</div>
}

type PillTone = 'ok' | 'warn' | 'neutral' | 'bad'
const pillTones: Record<PillTone, string> = {
  ok: 'bg-brand-soft text-brand-ink',
  warn: 'bg-amber-50 text-amber',
  neutral: 'bg-slate-100 text-slate-600',
  bad: 'bg-red-50 text-loss',
}

export function Pill({ children, tone = 'neutral' }: { children: ReactNode; tone?: PillTone }) {
  return <span className={clsx('inline-block rounded-full px-3 py-1 text-xs', pillTones[tone])}>{children}</span>
}

export function PageHeader({ eyebrow, title, right }: { eyebrow: string; title: string; right?: ReactNode }) {
  return (
    <header className="mb-6 flex items-end justify-between">
      <div>
        <div className="text-sm text-muted">{eyebrow}</div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      </div>
      <div className="flex gap-2">{right}</div>
    </header>
  )
}

export function OptimisticNote({ children }: { children?: ReactNode }) {
  return <p className="text-xs text-amber">{children ?? 'Optimistic: real results likely worse.'}</p>
}

/** Renders loading, error (fail loud, with the reason) or the data. */
export function Load<T>({ q, children }: { q: UseQueryResult<T>; children: (data: T) => ReactNode }) {
  if (q.isLoading) {
    return <div className="h-40 animate-pulse rounded-2xl bg-slate-200/60" role="status" aria-label="Loading" />
  }
  if (q.isError || !q.data) {
    return (
      <Card className="border-red-200">
        <div className="font-medium text-loss">Couldn't load this page</div>
        <p className="mt-1 text-sm text-muted">{(q.error as Error | null)?.message ?? 'No data returned.'}</p>
        <p className="mt-2 text-sm text-muted">
          Check that the API is running: <code className="num">uvicorn src.api.app:app --port 8000</code>
        </p>
      </Card>
    )
  }
  return <>{children(q.data)}</>
}

export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="py-10 text-center">
      <div className="font-medium">{title}</div>
      <p className="mt-1 text-sm text-muted">{body}</p>
    </div>
  )
}
