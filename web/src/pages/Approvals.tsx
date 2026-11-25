import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { useState } from 'react'
import { Card, Empty, Label, Load, PageHeader, Pill } from '../components/ui'
import { api, type QueuedOrder } from '../lib/api'
import { usd } from '../lib/format'

const statusTone = { PENDING: 'warn', APPROVED: 'ok', REJECTED: 'bad', AUTO: 'neutral' } as const
const statusWord = { PENDING: 'Waiting for you', APPROVED: 'Approved', REJECTED: 'Rejected', AUTO: 'Runs automatically' } as const

function OrderRow({ o, modeOn }: { o: QueuedOrder; modeOn: boolean }) {
  const qc = useQueryClient()
  const decide = useMutation({
    mutationFn: (action: 'approve' | 'reject') => api.decide(o.id, action),
    onSuccess: (data) => qc.setQueryData(['approvals'], data),
  })
  return (
    <tr className="border-b border-line last:border-0">
      <td className="py-3">
        <b>{o.ticker}</b>
        <div className="text-xs text-muted">{o.reason.replaceAll('_', ' ').toLowerCase()}</div>
      </td>
      <td>
        <Pill tone={o.action === 'BUY' ? 'ok' : 'bad'}>{o.action}</Pill>
      </td>
      <td className="num text-right">{o.shares.toFixed(2)}</td>
      <td className="num text-right">{usd(o.price)}</td>
      <td className="num pr-4 text-right">{usd(o.value)}</td>
      <td className="pl-4">
        <Pill tone={statusTone[o.status]}>{statusWord[o.status]}</Pill>
        {o.action === 'SELL' && <div className="mt-1 text-xs text-muted">Sells remove risk, so they never wait.</div>}
      </td>
      <td className="text-right">
        {o.requires_approval && modeOn && (
          <div className="flex justify-end gap-1.5">
            <button
              onClick={() => decide.mutate('approve')}
              aria-pressed={o.status === 'APPROVED'}
              className={clsx('cursor-pointer rounded-lg border px-3 py-1 text-xs', o.status === 'APPROVED' ? 'border-brand bg-brand text-white' : 'border-line bg-card hover:bg-chip')}
            >
              Approve
            </button>
            <button
              onClick={() => decide.mutate('reject')}
              aria-pressed={o.status === 'REJECTED'}
              className={clsx('cursor-pointer rounded-lg border px-3 py-1 text-xs', o.status === 'REJECTED' ? 'border-loss bg-loss text-white' : 'border-line bg-card hover:bg-chip')}
            >
              Reject
            </button>
          </div>
        )}
        {decide.isError && <div className="mt-1 text-xs text-loss">{(decide.error as Error).message}</div>}
      </td>
    </tr>
  )
}

function KillSwitchCard() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['kill-switch'], queryFn: api.killSwitch, refetchInterval: 30_000 })
  const [reason, setReason] = useState('')
  const [understood, setUnderstood] = useState(false)
  const [error, setError] = useState('')
  const set = useMutation({
    mutationFn: ({ enabled, why }: { enabled: boolean; why: string }) => api.setKillSwitch(enabled, why),
    onSuccess: (data) => {
      qc.setQueryData(['kill-switch'], data)
      qc.invalidateQueries({ queryKey: ['health'] })
      setReason('')
      setUnderstood(false)
      setError('')
    },
    onError: (e: Error) => setError(e.message),
  })

  return (
    <Load q={q}>
      {(k) => (
        <Card className={clsx(k.effective && 'border-loss/40 bg-loss/10')}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Kill switch</h2>
            <Pill tone={k.effective ? 'bad' : 'ok'}>{k.effective ? 'ON: the nightly run does nothing' : 'Off: trading allowed'}</Pill>
          </div>
          <p className="text-sm text-muted">{k.warning}</p>
          {k.reason && <p className="mt-2 text-sm">Reason: {k.reason}</p>}
          {k.env_override && <p className="mt-2 text-sm text-amber">KILL_SWITCH_ENABLED=true is set in .env, so it stays on until you change that file.</p>}

          {k.enabled ? (
            <button
              onClick={() => set.mutate({ enabled: false, why: '' })}
              className="mt-4 cursor-pointer rounded-xl bg-brand px-4 py-2 text-sm font-medium text-white hover:opacity-90"
            >
              Turn the kill switch off
            </button>
          ) : (
            <form
              className="mt-4 grid gap-3"
              onSubmit={(e) => {
                e.preventDefault()
                if (!reason.trim()) return setError('Say why, so the log can explain the halt later.')
                if (!understood) return setError('Tick the box to confirm you understand.')
                set.mutate({ enabled: true, why: reason })
              }}
            >
              <input
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value)
                  setError('')
                }}
                maxLength={200}
                placeholder="Why are you stopping trading?"
                aria-label="Reason for turning the kill switch on"
                className="rounded-xl border border-line bg-chip px-3 py-2 text-sm outline-none focus:border-loss"
              />
              <label className="flex items-start gap-2 text-sm text-muted">
                <input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} className="mt-1" />
                <span>I understand that while it is on, nothing runs: no buys, no sells, and stop-losses are not checked.</span>
              </label>
              <button type="submit" className="w-fit cursor-pointer rounded-xl bg-loss px-4 py-2 text-sm font-medium text-white hover:opacity-90">
                Turn the kill switch on
              </button>
            </form>
          )}
          {error && <p className="mt-2 text-sm text-loss">{error}</p>}
        </Card>
      )}
    </Load>
  )
}

export function Approvals() {
  const q = useQuery({ queryKey: ['approvals'], queryFn: api.approvals, refetchInterval: 30_000 })
  return (
    <>
      <PageHeader eyebrow="Approvals" title="Approve buys, and the kill switch" />
      <div className="grid gap-4">
        <Load q={q}>
          {(a) => (
            <Card>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold">Orders waiting for the next run</h2>
                <Pill tone={a.approval_required ? 'ok' : 'neutral'}>{a.approval_required ? 'Approval is ON' : 'Approval is off'}</Pill>
              </div>
              <ul className="mb-3 list-disc pl-5 text-sm text-muted">
                {a.how_it_works.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
              {a.enable_hint && <p className="mb-3 text-sm text-amber">{a.enable_hint} Until then, orders fill automatically.</p>}
              {a.orders.length === 0 ? (
                <Empty title="Nothing is waiting" body={`No order was queued by the latest run${a.run_date ? ` (${a.run_date})` : ''}.`} />
              ) : (
                <table className="w-full text-sm">
                  <thead className="border-b border-line text-xs text-muted">
                    <tr>
                      <th className="py-2 text-left font-normal">Order</th>
                      <th className="text-left font-normal">Side</th>
                      <th className="text-right font-normal">Shares</th>
                      <th className="text-right font-normal">Price</th>
                      <th className="pr-4 text-right font-normal">Value</th>
                      <th className="pl-4 text-left font-normal">Status</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {a.orders.map((o) => (
                      <OrderRow key={o.id} o={o} modeOn={a.approval_required} />
                    ))}
                  </tbody>
                </table>
              )}
              <p className="mt-3 text-xs text-faint">
                The risk engine already vetted every order here. Approving cannot add a trade it vetoed, and nothing on this page can place a trade by itself.
              </p>
            </Card>
          )}
        </Load>
        <KillSwitchCard />
        <Label>Paper trading only. No real money.</Label>
      </div>
    </>
  )
}
