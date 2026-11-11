import type { Analysis } from './findings'

const SKIP_FIELDS = new Set(['analysis', 'inputs', 'n_ids_listed'])

interface MetricRow {
  label: string
  beforeText: string
  afterText: string
  changed: boolean
}

function humaniseKey(key: string): string {
  return key.replace(/_/g, ' ')
}

function formatValue(val: unknown): string {
  if (val === undefined || val === null) {
    return '–'
  }
  if (typeof val === 'boolean') {
    return val ? 'yes' : 'no'
  }
  if (Array.isArray(val)) {
    return val.join(', ')
  }
  return String(val)
}

function areValuesEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (a === undefined || a === null || b === undefined || b === null) return false
  if (typeof a === 'boolean' && typeof b === 'boolean') return a === b
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, idx) => item === b[idx])
  }
  return String(a) === String(b)
}

function extractRows(
  beforeObj: Record<string, unknown>,
  afterObj: Record<string, unknown>
): MetricRow[] {
  const topKeys: string[] = []

  for (const k of Object.keys(beforeObj)) {
    if (!SKIP_FIELDS.has(k) && !topKeys.includes(k)) {
      topKeys.push(k)
    }
  }
  for (const k of Object.keys(afterObj)) {
    if (!SKIP_FIELDS.has(k) && !topKeys.includes(k)) {
      topKeys.push(k)
    }
  }

  const rows: MetricRow[] = []

  for (const k of topKeys) {
    const valB = beforeObj[k]
    const valA = afterObj[k]

    const isBObj = typeof valB === 'object' && valB !== null && !Array.isArray(valB)
    const isAObj = typeof valA === 'object' && valA !== null && !Array.isArray(valA)

    if (isBObj || isAObj) {
      const subObjB = (isBObj ? valB : {}) as Record<string, unknown>
      const subObjA = (isAObj ? valA : {}) as Record<string, unknown>

      const subKeys: string[] = []
      for (const sk of Object.keys(subObjB)) {
        if (!subKeys.includes(sk)) subKeys.push(sk)
      }
      for (const sk of Object.keys(subObjA)) {
        if (!subKeys.includes(sk)) subKeys.push(sk)
      }

      for (const sk of subKeys) {
        const itemB = Object.prototype.hasOwnProperty.call(subObjB, sk) ? subObjB[sk] : undefined
        const itemA = Object.prototype.hasOwnProperty.call(subObjA, sk) ? subObjA[sk] : undefined
        const changed = !areValuesEqual(itemB, itemA)

        rows.push({
          label: `${humaniseKey(k)}: ${sk}`,
          beforeText: formatValue(itemB),
          afterText: formatValue(itemA),
          changed,
        })
      }
    } else {
      const changed = !areValuesEqual(valB, valA)
      rows.push({
        label: humaniseKey(k),
        beforeText: formatValue(valB),
        afterText: formatValue(valA),
        changed,
      })
    }
  }

  return rows
}

function getStatusInfo(status: string) {
  switch (status) {
    case 'changed':
      return { className: 'status-conditional', mark: '!', text: 'result changed' }
    case 'unchanged':
      return { className: 'status-ready', mark: '✓', text: 'rerun, same result' }
    case 'not_rerun':
      return { className: 'status-neutral', mark: '—', text: 'not rerun' }
    default:
      return { className: 'status-neutral', mark: '?', text: status || 'unknown' }
  }
}

function AnalysisCard({ analysis }: { analysis: Analysis }) {
  const statusInfo = getStatusInfo(analysis.status)
  const isRerun = analysis.status === 'changed' || analysis.status === 'unchanged'

  const isBeforeObj =
    analysis.before !== null &&
    typeof analysis.before === 'object' &&
    !Array.isArray(analysis.before)
  const isAfterObj =
    analysis.after !== null &&
    typeof analysis.after === 'object' &&
    !Array.isArray(analysis.after)

  const rows =
    isRerun && isBeforeObj && isAfterObj
      ? extractRows(
          analysis.before as Record<string, unknown>,
          analysis.after as Record<string, unknown>
        )
      : []

  return (
    <article className="analysis-card">
      <div className="analysis-header">
        <h3>
          Analysis <code>{analysis.id}</code>
        </h3>
        <span className={`analysis-status ${statusInfo.className}`}>
          <span className="analysis-status-mark" aria-hidden="true">
            {statusInfo.mark}
          </span>
          {statusInfo.text}
        </span>
      </div>

      {typeof analysis.note === 'string' && analysis.note && (
        <p className="analysis-note">{analysis.note}</p>
      )}

      {isRerun && (!isBeforeObj || !isAfterObj || rows.length === 0) && (
        <p className="analysis-missing-note muted">
          Before and after numbers are not in this file.
        </p>
      )}

      {isRerun && isBeforeObj && isAfterObj && rows.length > 0 && (
        <div className="analysis-table-wrap">
          <table className="analysis-table">
            <caption className="visually-hidden">
              Comparison of analysis {analysis.id} before and after
            </caption>
            <thead>
              <tr>
                <th scope="col">Measure</th>
                <th scope="col">Before</th>
                <th scope="col">After</th>
                <th scope="col">
                  <span className="visually-hidden">Change</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.label} className={row.changed ? 'row-changed' : undefined}>
                  <th scope="row" className="measure-name">
                    {row.label}
                  </th>
                  <td className="measure-val">
                    <code>{row.beforeText}</code>
                  </td>
                  <td className="measure-val">
                    <code>{row.afterText}</code>
                  </td>
                  <td className="row-change-cell">
                    {row.changed ? <span className="change-word">changed</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </article>
  )
}

export function Analyses({ analyses }: { analyses?: unknown }) {
  if (!Array.isArray(analyses) || analyses.length === 0) {
    return (
      <section className="analyses-section" aria-label="Analyses">
        <h2>Analyses</h2>
        <p className="analyses-empty muted">No analyses in this file.</p>
      </section>
    )
  }

  return (
    <section className="analyses-section" aria-label="Analyses">
      <h2>Analyses</h2>
      <div className="analyses-list">
        {analyses.map((a: Analysis, idx) => (
          <AnalysisCard key={a.id || idx} analysis={a} />
        ))}
      </div>
    </section>
  )
}

