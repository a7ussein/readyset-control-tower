import { useState } from 'react'
import type { Pointer, Repair } from './findings'

function humaniseWord(word: unknown): string {
  if (typeof word !== 'string' || !word) return 'unknown'
  return word.replace(/_/g, ' ')
}

function getActionBadge(action: unknown) {
  const act = typeof action === 'string' ? action : 'unknown'
  switch (act) {
    case 'restore_from_previous_release':
      return { className: 'action-restore', mark: '↺', label: 'restore from previous release' }
    case 'exclude':
      return { className: 'action-exclude', mark: '×', label: 'exclude' }
    case 'relabel':
      return { className: 'action-relabel', mark: '✎', label: 'relabel' }
    case 'flag_for_review':
      return { className: 'action-review', mark: '!', label: 'flag for review' }
    case 'other':
      return { className: 'action-neutral', mark: '•', label: 'other' }
    default:
      return { className: 'action-neutral', mark: '•', label: act }
  }
}

interface RepairCardProps {
  repair: Repair
  findingIdSet: Set<string>
}

function RepairCard({ repair, findingIdSet }: RepairCardProps) {
  const [expanded, setExpanded] = useState(false)
  const actionInfo = getActionBadge(repair.action)

  const rawTargets = Array.isArray(repair.targets) ? repair.targets : []
  const targets: Pointer[] = []
  for (const t of rawTargets) {
    if (t && typeof t === 'object' && !Array.isArray(t)) {
      targets.push(t as Pointer)
    }
  }

  const rawAddresses = Array.isArray(repair.addresses) ? repair.addresses : []
  const addresses: string[] = []
  for (const a of rawAddresses) {
    if (typeof a === 'string') {
      addresses.push(a)
    }
  }

  const count = targets.length
  const INITIAL_LIMIT = 6
  const displayed = expanded ? targets : targets.slice(0, INITIAL_LIMIT)
  const hasMore = count > INITIAL_LIMIT

  const repairId = typeof repair.id === 'string' && repair.id ? repair.id : 'unknown'

  return (
    <article id={`repair-${repairId}`} className="repair-card">
      <div className="repair-header">
        <code className="repair-id">{repairId}</code>
        <span className={`badge ${actionInfo.className}`}>
          <span className="badge-mark" aria-hidden="true">
            {actionInfo.mark}
          </span>{' '}
          {actionInfo.label}
        </span>
        {addresses.length > 0 ? (
          <span className="repair-addresses muted">
            Addresses{' '}
            {addresses.map((fid, idx) => {
              const isPresent = findingIdSet.has(fid)
              return (
                <span key={`${fid}-${idx}`} className="repair-address-item">
                  {isPresent ? (
                    <a
                      href={`#finding-${fid}`}
                      className="finding-link"
                      title={`Jump to finding ${fid}`}
                    >
                      <code>{fid}</code>
                    </a>
                  ) : (
                    <span className="finding-missing">
                      <code>{fid}</code> <span className="muted">(not in this file)</span>
                    </span>
                  )}
                </span>
              )
            })}
          </span>
        ) : (
          <span className="repair-addresses muted">Addresses no findings</span>
        )}
      </div>

      {typeof repair.justification === 'string' && repair.justification && (
        <p className="repair-justification">{repair.justification}</p>
      )}

      <div className="targets-section">
        <div className="targets-header">
          <strong>Targets</strong> <span className="muted">({count})</span>
        </div>

        {count > 0 && (
          <div className={`targets-box ${expanded ? 'expanded-box' : ''}`}>
            <ul className="targets-list">
              {displayed.map((t, idx) => {
                const tKind = t && typeof t.kind === 'string' ? humaniseWord(t.kind) : 'unknown'
                const tId = t && typeof t.id === 'string' ? t.id : '–'
                const tRelease = t && typeof t.release === 'string' ? t.release : null
                const tFile = t && typeof t.file === 'string' ? t.file : null
                const tNote = t && typeof t.note === 'string' ? t.note : null

                return (
                  <li key={`${tId}-${idx}`} className="target-item">
                    <span className="target-kind">{tKind}</span>{' '}
                    <code className="target-id">{tId}</code>
                    {(tRelease || tFile) && (
                      <span className="target-loc muted">
                        {' ('}
                        {tRelease && <span>{tRelease}</span>}
                        {tRelease && tFile && ' · '}
                        {tFile && <code>{tFile}</code>}
                        {')'}
                      </span>
                    )}
                    {tNote && <span className="target-note"> — {tNote}</span>}
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        {hasMore && (
          <button
            type="button"
            className="text-button targets-toggle"
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

export interface RepairsProps {
  repairs?: unknown
  findingIds?: string[] | Set<string>
}

export function Repairs({ repairs, findingIds }: RepairsProps) {
  const findingIdSet = Array.isArray(findingIds)
    ? new Set(findingIds)
    : findingIds instanceof Set
    ? findingIds
    : new Set<string>()

  if (!Array.isArray(repairs) || repairs.length === 0) {
    return (
      <section className="repairs-section" aria-label="Proposed repairs">
        <h2>Proposed repairs</h2>
        <p className="repairs-subtitle muted">
          Proposed by the tool. Nothing in the data has been changed.
        </p>
        <p className="repairs-empty muted">No proposed repairs in this file.</p>
      </section>
    )
  }

  let skippedCount = 0
  const validRepairs: Repair[] = []

  for (const item of repairs) {
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      validRepairs.push(item as Repair)
    } else {
      skippedCount++
    }
  }

  return (
    <section className="repairs-section" aria-label="Proposed repairs">
      <h2>Proposed repairs</h2>
      <p className="repairs-subtitle muted">
        Proposed by the tool. Nothing in the data has been changed.
      </p>

      {skippedCount > 0 && (
        <p className="muted" style={{ margin: '8px 0 16px' }}>
          {skippedCount} {skippedCount === 1 ? 'entry' : 'entries'} could not be displayed.
        </p>
      )}

      {validRepairs.length === 0 && (
        <p className="repairs-empty muted">No proposed repairs in this file.</p>
      )}

      {validRepairs.length > 0 && (
        <div className="repairs-list">
          {validRepairs.map((r, idx) => (
            <RepairCard key={r.id || idx} repair={r} findingIdSet={findingIdSet} />
          ))}
        </div>
      )}
    </section>
  )
}
