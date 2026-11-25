import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Card, Label, Load, PageHeader, Pill } from '../components/ui'
import { api, type RunDay } from '../lib/api'

/** Only FAILED is red. DEGRADED means some stocks were skipped by the data check, which is by design. */
function pipelineTone(status: string): 'ok' | 'warn' | 'neutral' | 'bad' {
  if (status === 'SUCCESS') return 'ok'
  if (status === 'FAILED') return 'bad'
  if (status === 'NO_RUNS') return 'neutral'
  return 'warn' // DEGRADED, PARTIAL_SUCCESS, HALTED, SKIPPED
}

const dayStyle: Record<RunDay['outcome'], string> = {
  SUCCESS: 'bg-brand',
  DEGRADED: 'bg-amber',
  HALTED: 'bg-amber',
  FAILED: 'bg-loss',
  MISSED: 'bg-loss/30 ring-1 ring-loss',
  UNKNOWN: 'bg-faint',
}

const dayWord: Record<RunDay['outcome'], string> = {
  SUCCESS: 'ran cleanly',
  DEGRADED: 'ran, some stocks skipped by the data check',
  HALTED: 'halted (kill switch or a run already in progress)',
  FAILED: 'crashed, nothing was traded',
  MISSED: 'did not run',
  UNKNOWN: 'the log has no clear result',
}

function Legend({ className, children }: { className: string; children: string }) {
  return (
    <span>
      <i className={clsx('mr-1 inline-block size-2.5 rounded-sm', className)} />
      {children}
    </span>
  )
}

function RunStrip({ days }: { days: RunDay[] }) {
  return (
    <div className="flex flex-wrap gap-1.5" role="list" aria-label="Nightly runs, oldest first">
      {days.map((d) => (
        <div key={d.date} role="listitem" title={`${d.date}: ${dayWord[d.outcome]}`} className="text-center">
          <div className={clsx('size-7 rounded-md', dayStyle[d.outcome])} />
          <div className="num mt-1 text-[10px] text-faint">{d.date.slice(8)}</div>
        </div>
      ))}
    </div>
  )
}

export function Health() {
  const q = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 60_000 })
  return (
    <>
      <PageHeader eyebrow="Health" title="System health" />
      <Load q={q}>
        {(d) => {
          // Tolerate an older API that does not send every section yet: show what exists instead of crashing.
          const o = {
            ...d.ops,
            data_quality: d.ops.data_quality ?? { checked: 0, problems: [], message: 'Not reported by this version of the API. Restart the API to see it.' },
            alerts: { ...d.ops.alerts, heartbeat_configured: d.ops.alerts?.heartbeat_configured ?? false, telegram_configured: d.ops.alerts?.telegram_configured ?? false },
          }
          const failed = o.run_history.filter((r) => r.outcome === 'FAILED').length
          const missed = o.missed_days.length
          return (
            <div className="grid gap-4">
              {(failed > 0 || missed > 0 || !o.environment.ok) && (
                <Card className="border-loss/40 bg-loss/10">
                  <div className="text-sm font-medium text-loss">Needs attention</div>
                  <ul className="mt-1 list-disc pl-5 text-sm text-muted">
                    {failed > 0 && <li>{failed} nightly run(s) crashed in the last 14 days, so nothing was traded and stops were not checked.</li>}
                    {missed > 0 && <li>{missed} weekday(s) had no run at all: {o.missed_days.join(', ')}.</li>}
                    {!o.environment.ok && <li>The environment check is failing, so the next nightly run will not start.</li>}
                  </ul>
                </Card>
              )}

              <Card>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-lg font-semibold">Nightly runs, last 14 days</h2>
                  <div className="flex flex-wrap gap-3 text-xs text-muted">
                    <Legend className="bg-brand">ran</Legend>
                    <Legend className="bg-amber">ran, some skipped</Legend>
                    <Legend className="bg-loss">crashed</Legend>
                    <Legend className="bg-loss/30 ring-1 ring-loss">missed</Legend>
                  </div>
                </div>
                <RunStrip days={o.run_history} />
                <p className="mt-3 text-xs text-muted">Weekends are not shown. Today appears once its run has started.</p>
              </Card>

              <div className="grid gap-4 sm:grid-cols-2">
                <Card>
                  <Label>Last pipeline run</Label>
                  <div className="mt-1">
                    <Pill tone={pipelineTone(d.pipeline.status)}>{d.pipeline.status}</Pill>
                  </div>
                  <p className="mt-2 text-xs text-muted">{d.pipeline.message}</p>
                </Card>

                <Card>
                  <Label>Kill switch</Label>
                  <div className="mt-1">
                    <Pill tone={o.kill_switch.enabled === null ? 'neutral' : o.kill_switch.enabled ? 'bad' : 'ok'}>
                      {o.kill_switch.enabled === null ? 'Unknown' : o.kill_switch.enabled ? 'ON: trading is halted' : 'Off: trading allowed'}
                    </Pill>
                  </div>
                  {o.kill_switch.reason && <p className="mt-2 text-xs text-muted">{o.kill_switch.reason}</p>}
                </Card>

                <Card>
                  <Label>Backups</Label>
                  <div className="mt-1">
                    <Pill tone={!o.backups.supported || !o.backups.count ? 'neutral' : o.backups.stale ? 'warn' : 'ok'}>
                      {!o.backups.supported ? 'Not available' : !o.backups.count ? 'None yet' : o.backups.stale ? 'Older than 2 days' : 'Up to date'}
                    </Pill>
                  </div>
                  <p className="mt-2 text-xs text-muted">
                    {o.backups.message ??
                      `${o.backups.count} kept. Newest ${o.backups.newest}, ${o.backups.age_hours} hours old, ${o.backups.size_mb} MB. One is made and checked before each nightly run.`}
                  </p>
                </Card>

                <Card>
                  <Label>Alerts to your phone</Label>
                  <div className="mt-1">
                    <Pill tone={o.alerts.telegram_configured ? 'ok' : 'warn'}>{o.alerts.telegram_configured ? 'Telegram is set up' : 'Telegram is not set up'}</Pill>
                  </div>
                  <p className="mt-2 text-xs text-muted">
                    {o.alerts.telegram_configured
                      ? 'You are messaged when a nightly run crashes, is halted or is missed, when the environment check fails, and when a backup fails.'
                      : 'Without it, a failed run only shows here. Add the bot token and chat id to .env.'}
                  </p>
                  <div className="mt-3">
                    <Pill tone={o.alerts.heartbeat_configured ? 'ok' : 'warn'}>{o.alerts.heartbeat_configured ? "Dead man's switch is set up" : "Dead man's switch is not set up"}</Pill>
                  </div>
                  <p className="mt-2 text-xs text-muted">
                    {o.alerts.heartbeat_configured
                      ? 'An outside service messages you if the nightly run goes silent, even if this PC is off.'
                      : 'Alerts sent by this PC cannot fire when the PC is off. Create a free check at healthchecks.io and put its ping URL in .env as HEALTHCHECK_PING_URL.'}
                  </p>
                </Card>

                <Card>
                  <Label>Frozen model</Label>
                  <div className="mt-1">
                    <Pill tone={d.model.matches_freeze ? 'ok' : 'bad'}>
                      {!d.model.file_found ? 'Model file missing' : d.model.matches_freeze ? 'Hash matches freeze' : 'Hash differs: trading refused'}
                    </Pill>
                  </div>
                  <p className="mt-2 text-xs text-muted">Freeze is {d.model.frozen ? 'on' : 'off'}.</p>
                </Card>

                <Card>
                  <Label>Prediction drift</Label>
                  <div className="mt-1 text-sm font-medium">{d.drift.status}</div>
                  <p className="mt-1 text-xs text-muted">{d.drift.recommendation}</p>
                  <p className="mt-2 text-xs text-faint">{d.psi_note}</p>
                </Card>
              </div>

              <Card>
                <div className="mb-2 flex items-center justify-between">
                  <h2 className="text-lg font-semibold">Environment check</h2>
                  <Pill tone={o.environment.ok ? (o.environment.warnings.length ? 'warn' : 'ok') : 'bad'}>
                    {o.environment.ok ? (o.environment.warnings.length ? 'Passed with warnings' : 'Passed') : 'Failing'}
                  </Pill>
                </div>
                <ul className="space-y-1 text-sm">
                  {o.environment.problems.map((p) => (
                    <li key={p} className="text-loss">
                      ✕ {p}
                    </li>
                  ))}
                  {o.environment.warnings.map((w) => (
                    <li key={w} className="text-amber">
                      ! {w}
                    </li>
                  ))}
                  {o.environment.info.map((i) => (
                    <li key={i} className="text-muted">
                      ✓ {i}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-faint">The same check runs before every nightly run and stops it, with an alert, if something that matters is wrong.</p>
              </Card>

              <Card>
                <div className="mb-1 flex items-center justify-between">
                  <h2 className="text-lg font-semibold">Stored price history</h2>
                  <Pill tone={o.data_quality.problems.length ? 'warn' : 'ok'}>
                    {o.data_quality.problems.length ? `${o.data_quality.problems.length} of ${o.data_quality.checked} need attention` : 'All clean'}
                  </Pill>
                </div>
                {o.data_quality.message && <p className="text-sm text-muted">{o.data_quality.message}</p>}
                <ul className="space-y-1.5 text-sm">
                  {o.data_quality.problems.map((p) => (
                    <li key={p.ticker}>
                      <b>{p.ticker}</b> <span className="text-muted">{p.issues.join('; ')}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-faint">Checked for impossible values, stale data and holes of 6 or more trading days. Live trading fetches fresh prices each night, so a hole here affects backtests and training, not tonight's run.</p>
              </Card>

              <Card>
                <h2 className="mb-1 text-lg font-semibold">Stocks skipped by the data check</h2>
                {o.data_skips.skipped.length === 0 ? (
                  <p className="text-sm text-muted">{o.data_skips.message ?? 'No stock was skipped in the latest run.'}</p>
                ) : (
                  <>
                    <p className="mb-2 text-xs text-muted">Latest run: {o.data_skips.date}. A skipped stock is not traded that day.</p>
                    <ul className="space-y-1.5 text-sm">
                      {o.data_skips.skipped.map((s) => (
                        <li key={s.ticker}>
                          <b>{s.ticker}</b> <span className="text-muted">{s.reason}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </Card>
            </div>
          )
        }}
      </Load>
    </>
  )
}
