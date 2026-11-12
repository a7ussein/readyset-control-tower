// The judge screen: a list of findings on the left, one finding examined on the right.
// Everything it shows comes from findings.json (docs/OUTPUT-CONTRACT.md). It counts and formats; it computes no results.
import { useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from 'react'
import './bench.css'
import { loadFindings, saveReview, usingExample } from './api'
import type { Analysis, FileInfo, Finding, Findings, Pointer, Repair, Review, Witness } from './findings'
import { useTheme } from './theme'
import { SectionBoundary } from './SectionBoundary'

// ---- reading a file that may be malformed --------------------------------------------------------------------------
const list = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v.filter(x => x && typeof x === 'object' && !Array.isArray(x)) as T[]) : [])
const text = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback)
const words = (v: unknown): string => text(v).replace(/_/g, ' ')
const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`

function read(doc: Findings) {
  const witness = doc.x_readyset?.witness
  const x = doc.x_readyset && typeof doc.x_readyset === 'object' ? doc.x_readyset : undefined
  const titles = doc.x_readyset?.analysis_titles
  return {
    findings: list<Finding>(doc.findings).filter(f => typeof f.id === 'string'),
    analyses: list<Analysis>(doc.analyses).filter(a => typeof a.id === 'string'),
    repairs: list<Repair>(doc.repairs),
    files: list<FileInfo>(doc.x_readyset?.files).filter(f => typeof f.file === 'string'),
    releases: list<{ name?: unknown }>(doc.data?.releases).map(r => text(r.name)).filter(Boolean),
    witness: (witness && typeof witness === 'object' && !Array.isArray(witness) ? witness : {}) as Record<string, Witness>,
    titles: (titles && typeof titles === 'object' && !Array.isArray(titles) ? titles : {}) as Record<string, unknown>,
    rules: (x?.rules && typeof x.rules === 'object' && !Array.isArray(x.rules) ? x.rules : {}) as NonNullable<NonNullable<Findings['x_readyset']>['rules']>,
    reviews: list<Review>(x?.reviews).filter(r => typeof r.finding === 'string'),
    reviewKeys: (x?.review_keys && typeof x.review_keys === 'object' ? x.review_keys : {}) as Record<string, string>,
    available: list<{ id: string; title: string }>(x?.live?.available).filter(a => typeof a.id === 'string'),
    asked: (Array.isArray(x?.analyses_in_question) ? x.analyses_in_question : list<Analysis>(doc.analyses).map(a => a.id)).filter((v): v is string => typeof v === 'string'),
    reads: (x?.analysis_reads && typeof x.analysis_reads === 'object' ? x.analysis_reads : {}) as Record<string, unknown>,
  }
}
type Doc = ReturnType<typeof read>
const nameOf = (doc: Doc, id: string) => text(doc.titles[id]) || `Analysis ${id}`

const KIND: Record<string, string> = {
  sample_swap: 'sample swap', duplicate: 'duplicate', membership_change: 'membership change',
  label_conflict: 'label conflict', missing_data: 'missing data', other: 'other change',
}
const VERDICT: Record<string, { tone: string; mark: string }> = {
  Ready: { tone: 'ready', mark: '✓' }, Conditional: { tone: 'conditional', mark: '!' },
  Blocked: { tone: 'blocked', mark: '×' }, 'Insufficient Evidence': { tone: 'insufficient', mark: '?' },
}
const STATUS: Record<string, string> = { changed: 'changed', unchanged: 'rerun, same result', not_rerun: 'not rerun' }
const FILE_STATUS: Record<string, string> = {
  changed: 'content differs', unchanged: 'identical, not opened', absent: 'in neither release',
  missing_in_one: 'missing in one release', unreadable: 'could not be read',
}

const samplesOf = (f: Finding) => list<Pointer>(f.evidence).filter(e => e.kind === 'sample')
const fileOf = (f: Finding) => {
  const evidence = list<Pointer>(f.evidence)
  return text(evidence.find(e => typeof e.file === 'string')?.file) || text(evidence.find(e => e.kind === 'file')?.id)
}
function titleOf(f: Finding): string {
  const n = samplesOf(f).length
  switch (f.kind) {
    case 'sample_swap': return n === 2 ? 'Two samples traded profiles' : `${n} samples passed their profiles around`
    case 'duplicate': return n === 1 ? 'One new id is a copy of another sample' : `${n} new ids are copies of other samples`
    case 'membership_change': return `${plural(n, 'sample')} left or joined the file`
    case 'label_conflict': return `Labels changed for ${plural(n, 'sample')}`
    case 'missing_data': return `Values went missing for ${plural(n, 'sample')}`
    default: return fileOf(f) ? `Something else changed in ${fileOf(f)}` : 'Something else changed'
  }
}

/** A number as text, rounded for reading; the exact text stays in the tooltip. */
function shown(v: unknown): string {
  if (v === null || v === undefined) return 'absent'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(Number(v.toFixed(3)))
  const s = String(v)
  if (s.trim() === '') return 'blank'
  return /^-?\d+\.\d{4,}(e-?\d+)?$/i.test(s) ? Number(s).toFixed(3) : s
}
const exact = (v: unknown) => (v === null || v === undefined ? 'not in this release' : String(v))

function Chip({ tone, children }: { tone?: string; children: ReactNode }) {
  return <span className={`chip ${tone ?? ''}`}>{children}</span>
}

// ---- the proof: one row of real values -----------------------------------------------------------------------------
function Proof({ finding, witness }: { finding: Finding; witness?: Witness }) {
  const values = list<Witness['values'][number]>(witness?.values).filter(v => typeof v.sample === 'string')
  if (!witness || values.length === 0) return <LabelProof finding={finding} />
  const [a, b] = [text(witness.releases?.[0], 'before'), text(witness.releases?.[1], 'after')]
  const by = new Map(values.map(v => [v.sample, v]))
  let body: ReactNode
  let says = ''

  if (finding.kind === 'sample_swap' && values.length === 2) {
    says = 'Each sample now holds the value the other had.'
    body = (
      <div className="cross" role="img" aria-label={`${values[0].sample} and ${values[1].sample} exchanged values between ${a} and ${b}`}>
        <span /><span className="col-name">{a}</span><span /><span className="col-name">{b}</span>
        {values.map((v, i) => (
          <div className="cross-row" key={v.sample} style={{ gridRow: i + 2 }}>
            <code>{v.sample}</code>
            <span className="cell" title={exact(v.before)}>{shown(v.before)}</span>
            <span />
            <span className="cell pointed" title={exact(v.after)}>{shown(v.after)}</span>
          </div>
        ))}
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0,25 C50,25 50,75 100,75" /><path d="M0,75 C50,75 50,25 100,25" />
        </svg>
      </div>
    )
  } else if (finding.kind === 'duplicate') {
    const pairs = samplesOf(finding)
      .map(e => ({ copy: e.id, source: /^identical to (\S+)/.exec(text(e.note))?.[1] }))
      .filter(p => p.source && by.has(p.copy) && by.has(p.source as string))
    if (pairs.length > 0) {
      says = 'Each new id carries exactly the value of the sample it was copied from.'
      body = (
        <table className="proof-table">
          <thead><tr><th>copied from</th><th>{b}</th><th aria-hidden="true" /><th>new id</th><th>{b}</th></tr></thead>
          <tbody>{pairs.map(p => {
            const source = by.get(p.source as string)!, copy = by.get(p.copy)!
            return (
              <tr key={p.copy}>
                <th scope="row">{p.source}</th><td title={exact(source.after)}>{shown(source.after)}</td>
                <td className="equals" aria-label="equals">=</td>
                <th scope="row">{p.copy}</th><td className="pointed" title={exact(copy.after)}>{shown(copy.after)}</td>
              </tr>
            )
          })}</tbody>
        </table>
      )
    }
  }
  if (!body) {
    says = finding.kind === 'membership_change' ? 'A sample marked absent has no column in that release.' : ''
    body = (
      <table className="proof-table">
        <thead><tr><th>sample</th><th>{a}</th><th>{b}</th></tr></thead>
        <tbody>{values.map(v => (
          <tr key={v.sample}>
            <th scope="row">{v.sample}</th>
            <td title={exact(v.before)} className={v.before === null ? 'absent' : ''}>{shown(v.before)}</td>
            <td title={exact(v.after)} className={v.before !== v.after ? (v.after === null ? 'pointed absent' : 'pointed') : ''}>{shown(v.after)}</td>
          </tr>
        ))}</tbody>
      </table>
    )
  }
  return (
    <figure className="proof">
      {body}
      <figcaption>
        The <code>{witness.row}</code> row of <code>{witness.file}</code>. {says} Numbers are rounded to three places here; hover for
        the exact text, or open both files and check.
      </figcaption>
    </figure>
  )
}

/** Label changes carry their own proof in the evidence notes: "COLUMN: 'old' in A, 'new' in B". */
function LabelProof({ finding }: { finding: Finding }) {
  const rows = samplesOf(finding)
    .map(e => ({ id: e.id, m: /^(.+?): '(.*)' in (.+?), '(.*)' in (.+)$/.exec(text(e.note)) }))
    .filter((r): r is { id: string; m: RegExpExecArray } => r.m !== null)
  if (rows.length === 0) return null
  const [, column, , a, , b] = rows[0].m
  const same = rows.every(r => r.m[1] === column && r.m[3] === a && r.m[5] === b)
  if (!same) return null
  return (
    <figure className="proof">
      <table className="proof-table">
        <thead><tr><th>sample</th><th>{a}</th><th>{b}</th></tr></thead>
        <tbody>{rows.slice(0, 12).map(r => (
          <tr key={r.id}><th scope="row">{r.id}</th><td>{r.m[2] || 'blank'}</td><td className="pointed">{r.m[4] || 'blank'}</td></tr>
        ))}</tbody>
      </table>
      <figcaption>
        The <code>{column}</code> column of <code>{fileOf(finding)}</code>{rows.length > 12 ? `, first 12 of ${rows.length} samples` : ''}. Open both
        files and check.
      </figcaption>
    </figure>
  )
}

// ---- an analysis, before and after ---------------------------------------------------------------------------------
/** {counts: {Basal: 3}} becomes {"counts: Basal": 3}, so every row of the table is one number. */
function flat(v: unknown): Record<string, unknown> | undefined {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return undefined
  const out: Record<string, unknown> = {}
  for (const [k, x] of Object.entries(v)) {
    if (x && typeof x === 'object' && !Array.isArray(x)) for (const [k2, y] of Object.entries(x)) out[`${k}: ${k2}`] = y
    else out[k] = x
  }
  return out
}

function ResultTable({ analysis, releases }: { analysis: Analysis; releases: string[] }) {
  const before = flat(analysis.before), after = flat(analysis.after)
  if (!before && !after) return <p className="quiet">{text(analysis.note, 'No numbers were recorded for this analysis.')}</p>
  const keys = [...new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])]
  return (
    <table className="result-table">
      <thead><tr><th /><th>{releases[0] ?? 'before'}</th><th>{releases[1] ?? 'after'}</th><th>change</th></tr></thead>
      <tbody>{keys.map(k => {
        const x = before?.[k], y = after?.[k]
        const moved = JSON.stringify(x) !== JSON.stringify(y)
        const delta = typeof x === 'number' && typeof y === 'number' && moved
          ? (y - x > 0 ? '+' : '') + String(Number((y - x).toFixed(3))) : moved ? 'changed' : 'same'
        return (
          <tr key={k}>
            <th scope="row">{words(k)}</th><td>{shown(x)}</td>
            <td className={moved ? 'pointed' : ''}>{shown(y)}</td><td className="delta">{delta}</td>
          </tr>
        )
      })}</tbody>
    </table>
  )
}

function TargetList({ items, limit = 8 }: { items: Pointer[]; limit?: number }) {
  const [open, setOpen] = useState(false)
  const visible = open ? items : items.slice(0, limit)
  return (
    <ul className="targets">
      {visible.map((e, i) => (
        <li key={`${e.kind}-${e.id}-${i}`}>
          <code>{text(e.id)}</code>
          {(e.release || e.file) && <span className="quiet"> {[e.release, e.file].filter(Boolean).join(', ')}</span>}
          {e.note && <span className="note"> {e.note}</span>}
        </li>
      ))}
      {items.length > limit && (
        <li><button type="button" className="link" onClick={() => setOpen(o => !o)}>{open ? 'Show fewer' : `Show all ${items.length}`}</button></li>
      )}
    </ul>
  )
}

type ReviewInput = { status: 'confirmed' | 'dismissed' | 'cleared'; reviewer: string; role: string; note: string }
const remembered = (k: string) => { try { return localStorage.getItem(k) ?? '' } catch { return '' } }

/** The step a person takes: nothing here is settled until someone has looked. */
function ReviewCard({ review, onReview }: { review?: Review; onReview: (r: ReviewInput) => void }) {
  const [reviewer, setReviewer] = useState(() => review?.reviewer || remembered('readyset-reviewer'))
  const [role, setRole] = useState(() => review?.role || remembered('readyset-role'))
  const [note, setNote] = useState(review?.note ?? '')
  const send = (status: ReviewInput['status']) => {
    try { localStorage.setItem('readyset-reviewer', reviewer); localStorage.setItem('readyset-role', role) } catch { /* storage may be off */ }
    onReview({ status, reviewer: reviewer.trim(), role: role.trim(), note: note.trim() })
  }
  const named = reviewer.trim().length > 0
  return (
    <section className={`card review-card ${review ? review.status : 'waiting'}`} aria-label="Review by a person">
      <h2>Review by a person
        <Chip tone={review ? (review.status === 'confirmed' ? 'st-unchanged' : '') : 'review'}>
          {review ? (review.status === 'confirmed' ? 'confirmed as a real problem' : 'dismissed as expected') : 'waiting for review'}
        </Chip>
      </h2>
      {review
        ? <p>{review.status === 'confirmed' ? 'Confirmed' : 'Dismissed'} by <strong>{review.reviewer || 'someone who gave no name'}</strong>
            {review.role ? `, ${review.role}` : ''}{review.at ? `, ${review.at.replace('T', ' ').replace(/\+00:00$/, ' UTC')}` : ''}.
            {review.note ? ` Note: ${review.note}` : ''}</p>
        : <p className="quiet">The tool found this and proposes a repair. It decides nothing. Check the values above against the two files, then record what you conclude.</p>}
      <div className="review-form">
        <label>Your name<input id="review-name" value={reviewer} onChange={e => setReviewer(e.target.value)} placeholder="Name" autoComplete="name" /></label>
        <label>Your role<input id="review-role" value={role} onChange={e => setRole(e.target.value)} placeholder="For example: research engineer" /></label>
        <label className="wide">Note<input id="review-note" value={note} onChange={e => setNote(e.target.value)} placeholder="What you checked, optional" /></label>
      </div>
      <p className="review-actions">
        <button type="button" className="primary" disabled={!named} onClick={() => send('confirmed')}>Confirm: a real problem</button>
        <button type="button" className="ghost" disabled={!named} onClick={() => send('dismissed')}>Dismiss: expected change</button>
        {review && <button type="button" className="link" onClick={() => send('cleared')}>Undo review</button>}
        {!named && <span className="quiet">Enter your name to record a review.</span>}
      </p>
    </section>
  )
}

function RuleCard({ rule }: { rule?: { detected_by?: string; impact?: string[]; severity?: string } }) {
  if (!rule) return null
  return (
    <section className="card">
      <h2>How this was decided</h2>
      <dl className="rules">
        <dt>The check that found it</dt><dd>{text(rule.detected_by)}</dd>
        <dt>What it reaches</dt><dd>{(Array.isArray(rule.impact) ? rule.impact : []).map((line, i) => <span className="line" key={i}>{String(line)}</span>)}</dd>
        <dt>Why this severity</dt><dd>{text(rule.severity)}</dd>
      </dl>
    </section>
  )
}

function FindingView({ finding, doc, go, review, onReview }: { finding: Finding; doc: Doc; go: (id: string) => void; review?: Review; onReview: (finding: Finding, r: ReviewInput) => void }) {
  const affected = (Array.isArray(finding.affects_analyses) ? finding.affects_analyses : []).filter(x => typeof x === 'string')
  const spared = (Array.isArray(finding.not_affected_analyses) ? finding.not_affected_analyses : []).filter(x => typeof x === 'string')
  const repairs = doc.repairs.filter(r => Array.isArray(r.addresses) && r.addresses.includes(finding.id))
  const evidence = list<Pointer>(finding.evidence)
  return (
    <article className="detail" key={finding.id}>
      <header className="detail-head">
        <p className="chips">
          <span className="ref">{finding.id}</span>
          <Chip tone="kind">{KIND[finding.kind] ?? words(finding.kind)}</Chip>
          <Chip tone={`sev-${text(finding.severity)}`}>{text(finding.severity, 'unrated')} severity</Chip>
          <Chip>{text(finding.confidence, 'unknown')} confidence</Chip>
          {finding.needs_human_review && <Chip tone="review">needs a person to review</Chip>}
        </p>
        <h1>{titleOf(finding)}</h1>
        <p className="lede">{text(finding.summary)}</p>
      </header>

      <SectionBoundary name="proof"><Proof finding={finding} witness={doc.witness[finding.id]} /></SectionBoundary>

      <SectionBoundary name="review"><ReviewCard key={finding.id} review={review} onReview={r => onReview(finding, r)} /></SectionBoundary>

      <div className="detail-grid">
        <section className="card">
          <h2>What it does to the analyses</h2>
          {affected.length === 0 && <p className="quiet">No registered analysis reads what this finding touches.</p>}
          {affected.map(id => {
            const analysis = doc.analyses.find(a => a.id === id)
            return (
              <div className="effect" key={id}>
                <p className="effect-head">
                  <button type="button" className="link ref" onClick={() => go(id)}>{id}</button>
                  <span>{text(doc.titles[id])}</span>
                  <Chip tone={`st-${text(analysis?.status)}`}>{STATUS[text(analysis?.status)] ?? 'no result'}</Chip>
                </p>
                {analysis && <ResultTable analysis={analysis} releases={doc.releases} />}
              </div>
            )
          })}
          {spared.length > 0 && <p className="quiet">Does not touch {spared.join(', ')}.</p>}
        </section>

        <div className="stack">
          <section className="card">
            <h2>Proposed {repairs.length === 1 ? 'repair' : 'repairs'}</h2>
            {repairs.length === 0 && <p className="quiet">No repair is proposed for this finding.</p>}
            {repairs.map((r, i) => (
              <div className="repair" key={text(r.id, String(i))}>
                <p><span className="ref">{text(r.id)}</span> <strong>{words(r.action)}</strong></p>
                <p>{text(r.justification)}</p>
                <TargetList items={list<Pointer>(r.targets)} limit={4} />
              </div>
            ))}
            <p className="quiet">Proposed only. The tool has changed nothing in the data.</p>
          </section>
          <section className="card">
            <h2>What this cannot tell you</h2>
            <p>{text(finding.limitation, 'No limit was recorded.')}</p>
          </section>
        </div>
      </div>

      <RuleCard rule={doc.rules[finding.id]} />

      <section className="card">
        <h2>Evidence <span className="count">{evidence.length}</span></h2>
        <TargetList items={evidence} />
      </section>
    </article>
  )
}

function AnalysisView({ analysis, doc, go }: { analysis: Analysis; doc: Doc; go: (id: string) => void }) {
  const causes = doc.findings.filter(f => Array.isArray(f.affects_analyses) && f.affects_analyses.includes(analysis.id))
  return (
    <article className="detail" key={analysis.id}>
      <header className="detail-head">
        <p className="chips"><span className="ref">{analysis.id}</span><Chip tone={`st-${text(analysis.status)}`}>{STATUS[text(analysis.status)] ?? words(analysis.status)}</Chip></p>
        <h1>{nameOf(doc, analysis.id)}</h1>
        <p className="lede">{text(analysis.note)}</p>
      </header>
      <section className="card"><h2>Result in each release</h2><ResultTable analysis={analysis} releases={doc.releases} /></section>
      {causes.length > 0 && (
        <section className="card">
          <h2>Findings that touch it</h2>
          <ul className="targets">{causes.map(f => (
            <li key={f.id}><button type="button" className="link ref" onClick={() => go(f.id)}>{f.id}</button> {titleOf(f)}</li>
          ))}</ul>
        </section>
      )}
    </article>
  )
}

function AboutView({ raw, doc }: { raw: Findings; doc: Doc }) {
  const [failed, setFailed] = useState(false)
  const download = () => {
    try {
      const url = URL.createObjectURL(new Blob([JSON.stringify(raw, null, 2)], { type: 'application/json' }))
      const a = Object.assign(document.createElement('a'), { href: url, download: 'findings.json' })
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url); setFailed(false)
    } catch { setFailed(true) }
  }
  const x = raw.x_readyset
  const hashes = list<{ name?: unknown; files?: unknown }>(raw.data?.releases)
  return (
    <article className="detail">
      <header className="detail-head">
        <h1>{doc.findings.length === 0 ? 'Nothing differs that these analyses read' : 'About this result'}</h1>
        <p className="lede">{text(x?.scope, 'No scope statement was recorded.')}</p>
      </header>
      <section className="card">
        <h2>The files</h2>
        <table className="result-table files-table">
          <thead><tr><th>file</th><th>status</th><th>opened</th></tr></thead>
          <tbody>{doc.files.map(f => (
            <tr key={f.file}><th scope="row"><code>{f.file}</code>{f.note && <span className="note block">{f.note}</span>}</th>
              <td>{FILE_STATUS[f.status] ?? words(f.status)}</td><td>{f.opened ? 'yes' : 'no'}</td></tr>
          ))}</tbody>
        </table>
        <p className="quiet">A file whose content hash is identical in both releases is never opened.</p>
      </section>
      <section className="card">
        <h2>The output file</h2>
        <p>{[x?.engine_version && `Engine ${x.engine_version}`, x?.generated_at && `generated ${x.generated_at}`,
          typeof x?.run_seconds === 'number' && `compared in ${x.run_seconds} s`].filter(Boolean).join(', ') || 'No run details were recorded.'}</p>
        <p><button type="button" className="primary" onClick={download}>Download findings.json</button></p>
        {failed && <p className="quiet" role="alert">The download could not be started.</p>}
        <p className="quiet">To check the format, run the organisers' validator on this file (see docs/OUTPUT-CONTRACT.md).</p>
        {hashes.length > 0 && (
          <details>
            <summary>Content hashes</summary>
            {hashes.map((r, i) => (
              <div key={i}>
                <h3>{text(r.name)}</h3>
                <ul className="hashes">{list<{ file?: unknown; sha256?: unknown }>(r.files).map((f, j) => (
                  <li key={j}><code>{text(f.file)}</code><code className="sha">{text(f.sha256)}</code></li>
                ))}</ul>
              </div>
            ))}
          </details>
        )}
      </section>
    </article>
  )
}

// ---- the page ------------------------------------------------------------------------------------------------------
function Bench({ raw, onQuestion, onChanged }: { raw: Findings; onQuestion: (ids: string[]) => void; onChanged: () => void }) {
  const doc = useMemo(() => read(raw), [raw])
  // Reviews recorded while no server could keep them (the built-in example) live here until the page is closed.
  const [local, setLocal] = useState<Record<string, Review | null>>({})
  const reviewOf = (id: string): Review | undefined => (id in local ? local[id] ?? undefined : doc.reviews.find(r => r.finding === id))
  const onReview = async (f: Finding, r: ReviewInput) => {
    const key = doc.reviewKeys[f.id] ?? f.id
    const kept = await saveReview({ key, ...r })
    if (kept) { setLocal(({ [f.id]: _gone, ...rest }) => rest); onChanged() }
    else setLocal(prev => ({ ...prev, [f.id]: r.status === 'cleared' ? null : { finding: f.id, key, status: r.status, reviewer: r.reviewer, role: r.role, note: r.note, at: new Date().toISOString() } }))
  }
  const reviewed = doc.findings.filter(f => reviewOf(f.id)).length
  const toggle = (id: string) => {
    const next = doc.asked.includes(id) ? doc.asked.filter(a => a !== id) : doc.available.map(a => a.id).filter(a => a === id || doc.asked.includes(a))
    if (next.length) onQuestion(next)
  }
  const ids = useMemo(() => [...doc.findings.map(f => f.id), ...doc.analyses.map(a => a.id), 'about'], [doc])
  const first = doc.findings.length ? ids[0] : 'about'
  const fromHash = () => { const h = decodeURIComponent(location.hash.slice(1)); return ids.includes(h) ? h : first }
  const [selected, setSelected] = useState(fromHash)
  useEffect(() => {
    const onHash = () => setSelected(fromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  })
  const go = (id: string) => { setSelected(id); try { history.replaceState(null, '', `#${id}`) } catch { /* not allowed here */ } }
  const onKeys = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()
    const next = ids[Math.min(ids.length - 1, Math.max(0, ids.indexOf(selected) + (e.key === 'ArrowDown' ? 1 : -1)))]
    go(next)
    e.currentTarget.querySelector<HTMLElement>(`[data-id="${next}"]`)?.focus()
  }

  const verdict = text(raw.verdict)
  const tone = VERDICT[verdict] ?? { tone: 'insufficient', mark: '?' }
  const changedFiles = doc.files.filter(f => f.status !== 'unchanged' && f.status !== 'absent').length
  const touching = doc.findings.filter(f => Array.isArray(f.affects_analyses) && f.affects_analyses.length > 0).length
  const sentence = [
    `${plural(doc.findings.length, 'finding')}${doc.files.length ? ` in ${changedFiles} of ${plural(doc.files.length, 'file')}` : ''}.`,
    doc.findings.length > 0 && touching === 0 ? 'None of them touches what this question reads.' : '',
    ...doc.analyses.map(a => `${a.id} ${STATUS[text(a.status)] ?? words(a.status)}.`),
    doc.findings.length > 0 ? `${reviewed} of ${doc.findings.length} reviewed by a person.` : '',
  ].filter(Boolean).join(' ')
  const finding = doc.findings.find(f => f.id === selected)
  const analysis = doc.analyses.find(a => a.id === selected)

  return (
    <>
      <section className={`verdict-bar ${tone.tone}`} aria-label="Verdict">
        <p className="verdict" role="status"><span className="mark" aria-hidden="true">{tone.mark}</span>{verdict || 'No verdict'}</p>
        <p className="sentence">{sentence}</p>
        {doc.files.length > 0 && (
          <ul className="file-chips" aria-label="The files in the release">
            {doc.files.map(f => (
              <li key={f.file} className={`file ${f.status}${f.note ? ' same-values' : ''}`} title={`${FILE_STATUS[f.status] ?? f.status}${f.note ? `. ${f.note}` : ''}`}>
                {f.file.replace(/\.tsv(\.gz)?$/, '')}
              </li>
            ))}
          </ul>
        )}
      </section>

      {doc.asked.length > 0 && (
        <section className="question-bar" aria-label="The question">
          <span className="question-label">This release is needed for</span>
          <ul>
            {(doc.available.length ? doc.available : doc.asked.map(id => ({ id, title: text(doc.titles[id]) }))).map(a => {
              const on = doc.asked.includes(a.id)
              return (
                <li key={a.id}>
                  {doc.available.length
                    ? <button type="button" className={`ask${on ? ' on' : ''}`} aria-pressed={on} disabled={on && doc.asked.length === 1}
                        title={on && doc.asked.length === 1 ? 'A question needs at least one analysis' : text(doc.reads[a.id]) ? `Reads ${text(doc.reads[a.id])}` : ''}
                        onClick={() => toggle(a.id)}><span className="ref">{a.id}</span> {a.title}</button>
                    : <span className="ask on fixed"><span className="ref">{a.id}</span> {a.title}</span>}
                </li>
              )
            })}
          </ul>
          <span className="quiet">{doc.available.length ? 'Change the question and the verdict follows.' : 'Fixed in this file. Start the page on two release folders to change it.'}</span>
        </section>
      )}

      <div className="bench">
        <nav className="rail" aria-label="Findings and analyses" onKeyDown={onKeys}>
          <h2>Findings <span className="count">{doc.findings.length}</span></h2>
          {doc.findings.length === 0 && <p className="quiet">Nothing was found that differs between the two releases.</p>}
          <ul>{doc.findings.map(f => (
            <li key={f.id}>
              <button type="button" data-id={f.id} className={`item${selected === f.id ? ' on' : ''}`} aria-current={selected === f.id} onClick={() => go(f.id)}>
                <span className="ref">{f.id}</span>
                <span className="item-text"><b>{titleOf(f)}</b>
                  <small>{KIND[f.kind] ?? words(f.kind)}, {Array.isArray(f.affects_analyses) && f.affects_analyses.length ? `affects ${f.affects_analyses.join(', ')}` : 'affects no analysis'}</small></span>
                <Chip tone={`sev-${text(f.severity)}`}>{text(f.severity)}</Chip>
                <span className={`tick${reviewOf(f.id) ? ' done' : ''}`} title={reviewOf(f.id) ? 'Reviewed by a person' : 'Waiting for review'} aria-label={reviewOf(f.id) ? 'reviewed' : 'not reviewed'}>{reviewOf(f.id) ? '✓' : ''}</span>
              </button>
            </li>
          ))}</ul>
          <h2>Analyses</h2>
          <ul>{doc.analyses.map(a => (
            <li key={a.id}>
              <button type="button" data-id={a.id} className={`item slim${selected === a.id ? ' on' : ''}`} aria-current={selected === a.id} onClick={() => go(a.id)}>
                <span className="ref">{a.id}</span><span className="item-text"><b>{nameOf(doc, a.id)}</b></span>
                <Chip tone={`st-${text(a.status)}`}>{STATUS[text(a.status)] ?? words(a.status)}</Chip>
              </button>
            </li>
          ))}</ul>
          <ul><li><button type="button" data-id="about" className={`item slim${selected === 'about' ? ' on' : ''}`} aria-current={selected === 'about'} onClick={() => go('about')}>
            <span className="item-text"><b>About this result</b><small>files, hashes, download</small></span></button></li></ul>
          <p className="hint">Use the up and down arrow keys to move through the list.</p>
        </nav>

        <div className="stage">
          <SectionBoundary name="detail">
            {finding ? <FindingView finding={finding} doc={doc} go={go} review={reviewOf(finding.id)} onReview={onReview} />
              : analysis ? <AnalysisView analysis={analysis} doc={doc} go={go} />
              : <AboutView raw={raw} doc={doc} />}
          </SectionBoundary>
        </div>
      </div>
    </>
  )
}

export default function App() {
  const { theme, toggle } = useTheme()
  const [doc, setDoc] = useState<unknown>()
  const [error, setError] = useState('')
  const [asked, setAsked] = useState<string[] | undefined>()
  const load = (ids?: string[]) => loadFindings(ids).then(d => { setDoc(d); setError('') }).catch(e => setError(e instanceof Error ? e.message : String(e)))
  useEffect(() => { load() }, [])
  const onQuestion = (ids: string[]) => { setAsked(ids); load(ids) }
  const valid = doc !== null && typeof doc === 'object' && !Array.isArray(doc)
  const raw = valid ? (doc as Findings) : null
  const releases = raw ? list<{ name?: unknown }>(raw.data?.releases).map(r => text(r.name)).filter(Boolean) : []

  return (
    <>
      <header className="app-header">
        <a className="wordmark" href="./">
          <img className="logo-light" src="/brand/mark-light.png" alt="" />
          <img className="logo-dark" src="/brand/mark-dark.png" alt="" />
          ReadySet
        </a>
        <span className="product">Control Tower</span>
        {releases.length === 2 && <p className="pair"><code>{releases[0]}</code> compared with <code>{releases[1]}</code></p>}
        <button type="button" className="theme-toggle" onClick={toggle} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}>{theme === 'dark' ? '☀' : '☾'}</button>
      </header>
      <main>
        {error && <p className="error" role="alert">{error}</p>}
        {doc === undefined && !error && <p className="quiet pad">Loading findings…</p>}
        {doc !== undefined && !valid && <p className="error" role="alert">findings.json did not contain a result.</p>}
        {raw && (usingExample || raw.x_readyset?.example_notice) && (
          <p className="demo-note">{raw.x_readyset?.example_notice ?? 'Showing the hand-written example file.'}</p>
        )}
        {raw && <SectionBoundary name="result"><Bench raw={raw} onQuestion={onQuestion} onChanged={() => load(asked)} /></SectionBoundary>}
      </main>
      <footer>Built by team Automyte. De-identified TCGA research data. Research use only, not a clinical tool.</footer>
    </>
  )
}
