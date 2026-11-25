import { useQuery } from '@tanstack/react-query'
import { Card, Label, Load, PageHeader, Pill } from '../components/ui'
import { api } from '../lib/api'

export function Health() {
  const q = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 60_000 })
  return (
    <>
      <PageHeader eyebrow="Health" title="System health" />
      <Load q={q}>
        {(d) => (
          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <Label>Last pipeline run</Label>
              <div className="mt-1">
                <Pill tone={d.pipeline.status === 'SUCCESS' ? 'ok' : d.pipeline.status === 'NO_RUNS' ? 'neutral' : 'bad'}>
                  {d.pipeline.status}
                </Pill>
              </div>
              <p className="mt-2 text-xs text-muted">{d.pipeline.message}</p>
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
            </Card>
            <Card>
              <Label>PSI protection</Label>
              <p className="mt-1 text-sm text-muted">{d.psi_note}</p>
            </Card>
          </div>
        )}
      </Load>
    </>
  )
}
