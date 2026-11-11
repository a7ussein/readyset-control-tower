import { useState } from 'react'
import type { Finding, Pointer } from './findings'

const SEVERITY_RANK: Record<string, number> = {
  high: 0,
  medium: 1,
  low: 2,
  none: 3,
}

function getSeverityRank(sev: unknown): number {
  if (typeof sev === 'string' && sev in SEVERITY_RANK) {
    return SEVERITY_RANK[sev]
  }
  return 4
}

function getSeverityBadge(severity: unknown) {
  const sevStr = typeof severity === 'string' ? severity : 'unknown'
  switch (sevStr) {
    case 'high':
      return { className: 'severity-high', mark: '×', label: 'high' }
    case 'medium':
      return { className: 'severity-medium', mark: '!', label: 'medium' }
    case 'low':
      return { className: 'severity-low', mark: '–', label: 'low' }
    case 'none':
      return { className: 'severity-none', mark: '–', label: 'none' }
    default:
      return { className: 'severity-neutral', mark: '?', label: sevStr }
  }
}

function humaniseWord(word: unknown): string {
  if (typeof word !== 'string' || !word) return 'unknown'
  return word.replace(/_/g, ' ')
}

function getCountLine(items: Finding[]): string {
  const total = items.length
  const noun = total === 1 ? 'finding' : 'findings'
  if (total === 0) return `0 ${noun}`

  const counts: Record<string, number> = {}
  for (const f of items) {
    const s = typeof f.severity === 'string' ? f.severity : 'unknown'
    counts[s] = (counts[s] ?? 0) + 1
  }

  const parts: string[] = []
  for (const s of ['high', 'medium', 'low', 'none']) {
    if (counts[s]) {
      parts.push(`${counts[s]} ${s}`)
    }
  }
  for (const s of Object.keys(counts)) {
    if (!['high', 'medium', 'low', 'none'].includes(s) && counts[s]) {
      parts.push(`${counts[s]} ${s}`)
    }
  }

  if (parts.length === 0) return `${total} ${noun}`
  return `${total} ${noun}: ${parts.join(', ')}`
}

function FindingCard({ finding }: { finding: Finding }) {
  const [expanded, setExpanded] = useState(false)
  const sev = getSeverityBadge(finding.severity)
  const rawEvidence = Array.isArray(finding.evidence) ? finding.evidence : []
  const evidence: Pointer[] = rawEvidence.filter(
    (p): p is Pointer => Boolean(p && typeof p === 'object' && !Array.isArray(p))
  )
  const count = evidence.length
  const INITIAL_LIMIT = 6
  const displayed = expanded ? evidence : evidence.slice(0, INITIAL_LIMIT)
  const hasMore = count > INITIAL_LIMIT

  const rawAffects = Array.isArray(finding.affects_analyses) ? finding.affects_analyses : []
  const affects: string[] = rawAffects.filter((a): a is string => typeof a === 'string')

  const rawNotAffects = Array.isArray(finding.not_affected_analyses)
    ? finding.not_affected_analyses
    : []
  const notAffects: string[] = rawNotAffects.filter((a): a is string => typeof a === 'string')

  const findingId = typeof finding.id === 'string' && finding.id ? finding.id : 'unknown'

  return (
    <article id={`finding-${findingId}`} className="finding-card">
      <div className="finding-header">
        <code className="finding-id">{findingId}</code>
        <span className="badge kind-badge">{humaniseWord(finding.kind)}</span>
        <span className={`badge ${sev.className}`}>
          <span className="badge-mark" aria-hidden="true">
            {sev.mark}
          </span>{' '}
          {sev.label}
        </span>
        <span className="badge confidence-badge">
          confidence: {humaniseWord(finding.confidence)}
        </span>
      </div>

      {typeof finding.summary === 'string' && (
        <p className="finding-summary">{finding.summary}</p>
      )}

      {finding.needs_human_review === true && (
        <div style={{ margin: '6px 0 10px' }}>
          <span className="badge review-badge">
            <span className="badge-mark" aria-hidden="true">
              !
            </span>{' '}
            Needs human review
          </span>
        </div>
      )}

      <div className="impact-line">
        {affects.length > 0 ? (
          <span className="impact-part">
            Affects{' '}
            {affects.map((a, aIdx) => (
              <code key={`${a}-${aIdx}`} className="analysis-chip">
                {a}
              </code>
            ))}
          </span>
        ) : (
          <span className="impact-part">Affects no registered analysis</span>
        )}
        {notAffects.length > 0 && (
          <span className="impact-part muted">
            Does not affect{' '}
            {notAffects.map((a, aIdx) => (
              <code key={`${a}-${aIdx}`} className="analysis-chip">
                {a}
              </code>
            ))}
          </span>
        )}
      </div>

      {typeof finding.limitation === 'string' && finding.limitation && (
        <p className="finding-limitation muted">
          <span className="limitation-label">Limitation:</span> {finding.limitation}
        </p>
      )}

      <div className="evidence-section">
        <div className="evidence-header">
          <strong>Evidence</strong> <span className="muted">({count})</span>
        </div>

        {count > 0 && (
          <div className={`evidence-box ${expanded ? 'expanded-box' : ''}`}>
            <ul className="pointers-list">
              {displayed.map((p, idx) => {
                const pKind = p && typeof p.kind === 'string' ? humaniseWord(p.kind) : 'unknown'
                const pId = p && typeof p.id === 'string' ? p.id : '–'
                const pRelease = p && typeof p.release === 'string' ? p.release : null
                const pFile = p && typeof p.file === 'string' ? p.file : null
                const pNote = p && typeof p.note === 'string' ? p.note : null

                return (
                  <li key={`${pId}-${idx}`} className="pointer-item">
                    <span className="pointer-kind">{pKind}</span>{' '}
                    <code className="pointer-id">{pId}</code>
                    {(pRelease || pFile) && (
                      <span className="pointer-loc muted">
                        {' ('}
                        {pRelease && <span>{pRelease}</span>}
                        {pRelease && pFile && ' · '}
                        {pFile && <code>{pFile}</code>}
                        {')'}
                      </span>
                    )}
                    {pNote && <span className="pointer-note"> — {pNote}</span>}
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        {hasMore && (
          <button
            type="button"
            className="text-button evidence-toggle"
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? 'Show fewer' : `Show all ${count}`}
          </button>
        )}
      </div>
    </article>
  )
}

export function FindingsList({ findings }: { findings?: unknown }) {
  if (findings === undefined || (Array.isArray(findings) && findings.length === 0)) {
    return (
      <section className="findings-section" aria-label="Findings">
        <h2>Findings</h2>
        <p className="findings-empty muted">No findings in this file.</p>
      </section>
    )
  }

  if (!Array.isArray(findings)) {
    return (
      <section className="findings-section" aria-label="Findings">
        <h2>Findings</h2>
        <p className="error" role="alert">
          The findings in this file could not be read.
        </p>
      </section>
    )
  }

  let skippedCount = 0
  const validFindings: Finding[] = []

  for (const item of findings) {
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      validFindings.push(item as Finding)
    } else {
      skippedCount++
    }
  }

  const sortedFindings = [...validFindings].sort((a, b) => {
    return getSeverityRank(a.severity) - getSeverityRank(b.severity)
  })

  return (
    <section className="findings-section" aria-label="Findings">
      <h2>Findings</h2>
      <p className="findings-count-line muted">{getCountLine(sortedFindings)}</p>

      {skippedCount > 0 && (
        <p className="muted" style={{ margin: '8px 0 16px' }}>
          {skippedCount} {skippedCount === 1 ? 'entry' : 'entries'} could not be displayed.
        </p>
      )}

      {sortedFindings.length === 0 && (
        <p className="findings-empty muted">No findings in this file.</p>
      )}

      {sortedFindings.length > 0 && (
        <div className="findings-list">
          {sortedFindings.map((f, idx) => (
            <FindingCard key={`${f.id || 'finding'}-${idx}`} finding={f} />
          ))}
        </div>
      )}
    </section>
  )
}
