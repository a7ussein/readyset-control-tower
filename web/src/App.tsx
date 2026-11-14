// The judge screen: one column. The answer, what you need the data for, then each change as a step you open and decide on.
// Everything it shows comes from findings.json (docs/OUTPUT-CONTRACT.md). It counts and formats; it computes no results.
import { useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent, type ReactNode } from 'react'
import './bench.css'
import { addAnalysis, analysisOptions, auditReport, changelogUrl, columnValues, loadFindings, openEnvelope, pastComparisons, releaseState, reportUrl, rowNames, saveReview, setRelease, uploadRelease, usingExample, type AnalysisOptions, type PastComparison, type ReleaseState } from './api'
import type { Analysis, FileInfo, Finding, Findings, Pointer, Repair, Review, Witness } from './findings'
import { useTheme } from './theme'
import { SectionBoundary } from './SectionBoundary'
import { Ask } from './Ask'
import { DataView, showData } from './DataView'
import { Method, showMethod } from './Method'

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
    notes: (Array.isArray(x?.notes) ? x.notes : []).filter((n): n is string => typeof n === 'string'),
    effects: (x?.effects && typeof x.effects === 'object' ? x.effects : {}) as NonNullable<NonNullable<Findings['x_readyset']>['effects']>,
    priority: (x?.repair_priority && typeof x.repair_priority === 'object' ? x.repair_priority : {}) as Record<string, { level?: string; why?: string }>,
  }
}
type Doc = ReturnType<typeof read>
const nameOf = (doc: Doc, id: string) => text(doc.titles[id]) || `Analysis ${id}`

const KIND: Record<string, string> = {
  sample_swap: 'sample swap', duplicate: 'duplicate', membership_change: 'membership change',
  label_conflict: 'label conflict', missing_data: 'missing data', other: 'other change',
}
const VERDICT: Record<string, { tone: string; mark: string; means: string }> = {
  Ready: { tone: 'ready', mark: '✓', means: 'You can use the new release for this. Nothing your analyses read has changed.' },
  Conditional: { tone: 'conditional', mark: '!', means: 'Something your analyses read has changed. Review each change below before you use the new release.' },
  Blocked: { tone: 'blocked', mark: '×', means: 'Do not use the new release yet. A change broke an analysis so badly it could not be rerun.' },
  'Insufficient Evidence': { tone: 'insufficient', mark: '?', means: 'The two releases could not be fully compared, because a file is missing or unreadable.' },
}
const STATUS: Record<string, string> = { changed: 'result changed', unchanged: 'rerun, same result', not_rerun: 'untouched' }
const FILE_STATUS: Record<string, string> = {
  changed: 'content differs', unchanged: 'identical: every byte was read and matches', absent: 'in neither release',
  missing_in_one: 'missing in one release', not_in_both: 'in only one release; not needed, so not compared', unreadable: 'could not be read',
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
    default: {
      const said = text(f.summary), file = fileOf(f)
      if (/ but not in /.test(said)) return `${file || 'A file'} is missing from one release`
      if (/could not be read/.test(said)) return `${file || 'A file'} could not be read`
      if (/^The shape of /.test(said)) return `Rows or columns appeared or disappeared in ${file || 'a file'}`
      return file ? `Values were edited in ${file}` : 'Something else changed'
    }
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

function ResultTable({ analysis, releases, own }: { analysis: Analysis; releases: string[]; own?: { before?: unknown; after?: unknown } }) {
  const before = flat(own ? own.before : analysis.before), after = flat(own ? own.after : analysis.after)
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

type ReviewInput = { status: 'confirmed' | 'dismissed' | 'cleared'; fix: 'approved' | ''; reviewer: string; role: string; note: string }
const remembered = (k: string) => { try { return localStorage.getItem(k) ?? '' } catch { return '' } }

const HEADLINE: Record<string, (reaching: number, total: number) => string> = {
  Ready: (_r, total) => total === 0 ? 'Yes, you can use it' : 'Yes, for the analyses you chose',
  Conditional: (n, total) => n === total ? `Not yet. ${n === 1 ? 'One change needs' : `${n} changes need`} your review`
    : `Not yet. ${n} of ${total} changes reach your analyses`,
  Blocked: () => 'No. An analysis can no longer run',
  'Insufficient Evidence': () => 'Cannot tell. A file is missing or unreadable',
}

/** The step a person takes. The tool finds and proposes; a person decides. */
function Decision({ review, onReview, hasFix, waiting = 0, onAll }: { review?: Review; onReview: (r: ReviewInput) => void; hasFix: boolean; waiting?: number; onAll?: (r: ReviewInput) => void }) {
  const [fix, setFix] = useState(review?.fix === 'approved')
  const [reviewer, setReviewer] = useState(() => review?.reviewer || remembered('readyset-reviewer'))
  const [role, setRole] = useState(() => review?.role || remembered('readyset-role'))
  const [note, setNote] = useState(review?.note ?? '')
  // Once a person has said who they are, the page remembers it: later decisions are one click, not a form.
  const [editing, setEditing] = useState(() => !(review?.reviewer || remembered('readyset-reviewer')).trim())
  const send = (status: ReviewInput['status']) => {
    try { localStorage.setItem('readyset-reviewer', reviewer); localStorage.setItem('readyset-role', role) } catch { /* storage may be off */ }
    onReview({ status, fix: status === 'confirmed' && fix ? 'approved' : '', reviewer: reviewer.trim(), role: role.trim(), note: note.trim() })
  }
  const named = reviewer.trim().length > 0
  return (
    <section className={`decision ${review ? review.status : 'waiting'}`} aria-label="Your decision">
      <h3>Your decision</h3>
      {review
        ? <p className="decided"><span className="decided-mark" aria-hidden="true">{review.status === 'confirmed' ? '✓' : '–'}</span>
            <span><strong>{review.status === 'confirmed' ? 'Confirmed as a real problem' : 'Dismissed as an expected change'}</strong>
              {review.status === 'confirmed' && (review.fix === 'approved' ? ' The suggested fix is approved.' : ' The suggested fix is not approved yet.')}<br />
              by {review.reviewer || 'someone who gave no name'}{review.role ? `, ${review.role}` : ''}{review.note ? `. "${review.note}"` : ''}</span></p>
        : <p className="quiet">The tool found this. It decides nothing. Check the proof, then say what it is. Your decision is written into the report.</p>}
      {!editing && <p className="deciding-as">Deciding as <strong>{reviewer.trim()}</strong>{role.trim() ? `, ${role.trim()}` : ''}. <button type="button" className="link" onClick={() => setEditing(true)}>Change</button></p>}
      <div className="who">
        {editing && <>
          <label>Your name<input id="review-name" value={reviewer} onChange={e => setReviewer(e.target.value)} placeholder="Name" autoComplete="name" /></label>
          <label>Your role<input id="review-role" value={role} onChange={e => setRole(e.target.value)} placeholder="Research engineer" /></label>
        </>}
        <label className="wide">Note, optional<input id="review-note" value={note} onChange={e => setNote(e.target.value)} placeholder="What you checked" /></label>
      </div>
      {hasFix && <label className="also"><input id="review-fix" type="checkbox" checked={fix} onChange={e => setFix(e.target.checked)} /> Also approve the suggested fix</label>}
      <div className="decide">
        <button type="button" className="big confirm" disabled={!named} onClick={() => send('confirmed')}>This is a real problem</button>
        <button type="button" className="big dismiss" disabled={!named} onClick={() => send('dismissed')}>This is expected</button>
      </div>
      {!named && <p className="quiet">Enter your name once to record a decision. The page remembers it for the rest.</p>}
      {named && onAll && waiting > 1 && (
        <details className="decide-all">
          <summary>Many changes? Decide all {waiting} still waiting at once</summary>
          <p>Use this only when you have checked them and they call for the same decision. Each one is recorded in your name, and the note says it was decided together with the others.</p>
          <div className="decide">
            <button type="button" className="ghost" onClick={() => onAll({ status: 'confirmed', fix: '', reviewer: reviewer.trim(), role: role.trim(), note: note.trim() })}>All {waiting} are real problems</button>
            <button type="button" className="ghost" onClick={() => onAll({ status: 'dismissed', fix: '', reviewer: reviewer.trim(), role: role.trim(), note: note.trim() })}>All {waiting} are expected</button>
          </div>
        </details>
      )}
      {review && <button type="button" className="link" onClick={() => send('cleared')}>Undo this decision</button>}
    </section>
  )
}

function More({ title, children, open }: { title: string; children: ReactNode; open?: boolean }) {
  return <details className="more" open={open}><summary>{title}</summary><div className="more-body">{children}</div></details>
}

function ChangePanel({ finding, doc, index, total, review, onReview, step, waiting, onAll }: {
  finding: Finding; doc: Doc; index: number; total: number; review?: Review
  onReview: (finding: Finding, r: ReviewInput) => void; step: (by: number) => void
  waiting: number; onAll: (r: ReviewInput) => void
}) {
  const affected = (Array.isArray(finding.affects_analyses) ? finding.affects_analyses : []).filter(x => typeof x === 'string')
  const repairs = doc.repairs.filter(r => Array.isArray(r.addresses) && r.addresses.includes(finding.id))
  const evidence = list<Pointer>(finding.evidence)
  const rule = doc.rules[finding.id]
  const together = (id: string) => doc.findings.filter(f => Array.isArray(f.affects_analyses) && f.affects_analyses.includes(id)).map(f => f.id)
  const own = (id: string) => doc.effects[finding.id]?.[id]
  const percent = (v: unknown) => (typeof v === 'number' ? (v >= 1 ? 'more than 100%' : `${(v * 100).toFixed(v < 0.01 ? 2 : 1)}%`) : 'an unknown amount')
  return (
    <article className="panel" key={finding.id} aria-label={`Change ${index + 1} of ${total}`}>
      <header className="panel-head">
        <p className="eyebrow">Change {index + 1} of {total} <span className="ref">{finding.id}</span>{' '}<span className="sev">{KIND[finding.kind] ?? words(finding.kind)}</span>{' '}<span className={`sev sev-${text(finding.severity)}`}>{text(finding.severity, 'unrated')} severity</span></p>
        <h2>{titleOf(finding)}</h2>
        <p className="lede">{text(finding.summary)}</p>
        {(() => {
          // "So what?": the consequence for the person's own results, in one line, built from the findings.
          const hit = affected.map(id => ({ id, e: own(id) })).filter(x => x.e)
          const first = hit[0]
          const urgency = repairs.map(r => doc.priority[text(r.id)]?.level).find(Boolean)
          const consequence = affected.length === 0
            ? 'Nothing, for the analyses you chose: none of them reads what changed here. It is still a real change in the data.'
            : first
              ? `${first.id} (${doc.titles[first.id] ?? 'your analysis'}) gives a different answer: on its own this change moves its ${words(first.e?.measure) || 'result'} by ${percent(first.e?.moved_by)}.`
              : `It reaches ${affected.join(' and ')}, which ${affected.length === 1 ? 'reads' : 'read'} what changed here.`
          return <p className="so-what"><strong>So what?</strong> {consequence}{affected.length > 0 && urgency ? (urgency === 'before use' ? ' Deal with it before you use this release.' : ` That is a ${urgency}: the suggested fix below says what to check.`) : ''}</p>
        })()}
      </header>

      <div className="panel-grid">
        <div className="panel-main">
          <h3>The proof</h3>
          <SectionBoundary name="proof"><Proof finding={finding} witness={doc.witness[finding.id]} /></SectionBoundary>
          {!usingExample && <p className="see-data"><button type="button" className="ghost" onClick={() => showData(finding.id)}>See the data in both files, side by side</button></p>}
          <h3>What it does to your analyses</h3>
          {affected.length === 0 && <p className="plain">Nothing. None of the analyses you chose reads what changed here.</p>}
          {affected.map(id => {
            const analysis = doc.analyses.find(a => a.id === id)
            return (
              <div className="effect" key={id}>
                <p className="effect-head"><span className="ref">{id}</span> {nameOf(doc, id)}
                  <Chip tone={`st-${text(analysis?.status)}`}>{text(analysis?.status) === 'not_rerun' ? 'could not be rerun' : STATUS[text(analysis?.status)] ?? 'no result'}</Chip></p>
                {text(analysis?.status) === 'not_rerun' && Boolean(analysis?.before || analysis?.after) && <p className="plain">{text(analysis?.note)}</p>}
                {own(id)
                  ? <>
                      <p className="plain">{own(id)?.size === 'none' ? 'On its own, this change leaves the result exactly the same.'
                        : own(id)?.size === 'small'
                          ? `On its own, this change moves the result only slightly: ${words(own(id)?.measure)} by ${percent(own(id)?.moved_by)}, and no headline number (the difference, a group mean or a share) by half a percent.`
                          : `On its own, this change moves the result clearly: ${words(own(id)?.measure)} by ${percent(own(id)?.moved_by)}. Half a percent on a headline number is the line.`}{' '}
                        <span className={`sev size-${text(own(id)?.size)}`}>{own(id)?.size === 'none' ? 'no effect' : `${text(own(id)?.size)} effect`}</span></p>
                      {analysis && <ResultTable analysis={analysis} releases={[doc.releases[0] ?? 'before', 'this change alone']} own={own(id)} />}
                      {together(id).length > 1 && <p className="quiet">With all {together(id).length} changes that reach {id} in ({together(id).join(', ')}), the result is the one shown under "What I need it for".</p>}
                    </>
                  : <>
                      {together(id).length > 1 && <p className="quiet">These numbers are the effect of all {together(id).length} changes that reach {id} together ({together(id).join(', ')}).</p>}
                      {analysis && <ResultTable analysis={analysis} releases={doc.releases} />}
                    </>}
              </div>
            )
          })}
        </div>

        <aside className="panel-side">
          <SectionBoundary name="decision"><Decision key={finding.id} review={review} onReview={r => onReview(finding, r)} hasFix={repairs.length > 0} waiting={waiting} onAll={onAll} /></SectionBoundary>
          <section className="fix">
            <h3>Suggested fix</h3>
            {repairs.length === 0 && <p className="quiet">None proposed.</p>}
            {repairs.map((r, i) => (
              <div key={text(r.id, String(i))}>
                {doc.priority[text(r.id)]?.level && <p className={`urgency u-${text(doc.priority[text(r.id)].level).replace(/ /g, '-')}`}><b>{text(doc.priority[text(r.id)].level).replace(/^./, c => c.toUpperCase())}.</b> {text(doc.priority[text(r.id)].why)}</p>}
                <p><strong>{words(r.action).replace(/^./, c => c.toUpperCase())}.</strong> {text(r.justification)}</p>
                <TargetList items={list<Pointer>(r.targets)} limit={3} />
              </div>
            ))}
            <p className="quiet">Suggested only. The tool has changed nothing in the data.</p>
          </section>
        </aside>
      </div>

      <div className="mores">
        <More title="What this cannot tell you" open><p>{text(finding.limitation, 'No limit was recorded.')}</p></More>
        {rule && (
          <More title="How the tool decided this">
            <dl className="rules">
              <dt>The check that found it</dt><dd>{text(rule.detected_by)}</dd>
              <dt>What it reaches</dt><dd>{(Array.isArray(rule.impact) ? rule.impact : []).map((line, i) => <span className="line" key={i}>{String(line)}</span>)}</dd>
              <dt>Why this severity</dt><dd>{text(rule.severity)}</dd>
            </dl>
          </More>
        )}
        <More title={`All the evidence (${evidence.length})`}><TargetList items={evidence} limit={12} /></More>
      </div>

      <nav className="pager" aria-label="Move between changes">
        <button type="button" className="ghost" disabled={index === 0} onClick={() => step(-1)}>Previous change</button>
        <span className="quiet">{index + 1} of {total}</span>
        <button type="button" className="ghost" disabled={index === total - 1} onClick={() => step(1)}>Next change</button>
      </nav>
    </article>
  )
}

function FilesAndDownload({ raw, doc }: { raw: Findings; doc: Doc }) {
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
    <section className="block" id="files">
      <h2 className="block-title">The files and the report</h2>
      <div className="two">
        <div className="card">
          <h3>What was compared</h3>
          <table className="result-table files-table">
            <thead><tr><th>file</th><th>status</th></tr></thead>
            <tbody>{doc.files.map(f => (
              <tr key={f.file}><th scope="row"><code>{f.file}</code>{f.note && <span className="note block-note">{f.note}</span>}</th>
                <td>{FILE_STATUS[f.status] ?? words(f.status)}</td></tr>
            ))}</tbody>
          </table>
          <p className="quiet">Every file is read in full in both releases. When the whole content matches byte for byte, the file is identical and there is nothing inside it left to compare.</p>
        </div>
        <div className="card">
          <h3>The report, in two forms</h3>
          <p><strong>For people:</strong> the audit report says in plain English what changed, the proof, what it did to each result, the suggested fix and who reviewed it. Open it, print it or save it as a PDF.</p>
          {reportUrl(doc.asked)
            ? <ReportButton asked={doc.asked} />
            : <p className="quiet">The audit report is available when the page is comparing real releases.</p>}
          {changelogUrl(doc.asked) && <>
            <p><strong>For a spreadsheet:</strong> the change log has one row per affected sample: the change, the value before and after, the analysis it touches, the suggested fix and the decision.</p>
            <p><a className="ghost as-button" href={changelogUrl(doc.asked) ?? undefined} download="change-log.csv">Download the change log (CSV)</a></p>
          </>}
          <p><strong>For other tools:</strong> the same findings as one file the organisers' checker and the review team's tool can read.</p>
          <p><button type="button" className="ghost" onClick={download}>Download findings.json</button></p>
          {failed && <p className="quiet" role="alert">The download could not be started.</p>}
          <p className="quiet">{text(x?.scope)}</p>
          <p className="quiet">{[x?.engine_version && `Engine ${x.engine_version}`, typeof x?.run_seconds === 'number' && `compared in ${x.run_seconds} s`].filter(Boolean).join(', ')}</p>
          {hashes.length > 0 && (
            <More title="Content hashes of every file">
              {hashes.map((r, i) => (
                <div key={i}><h4>{text(r.name)}</h4>
                  <ul className="hashes">{list<{ file?: unknown; sha256?: unknown }>(r.files).map((f, j) => (
                    <li key={j}><code>{text(f.file)}</code><code className="sha">{text(f.sha256)}</code></li>
                  ))}</ul></div>
              ))}
            </More>
          )}
        </div>
      </div>
    </section>
  )
}

/** Build a new analysis from what the trusted release holds: no typing of file or column names from memory. */
function AddAnalysis({ onAdded }: { onAdded: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const [options, setOptions] = useState<AnalysisOptions | null>(null)
  const [kind, setKind] = useState<'mean_by_group' | 'category_mix'>('mean_by_group')
  const [file, setFile] = useState('')
  const [row, setRow] = useState('')
  const [rows, setRows] = useState<string[]>([])
  const [column, setColumn] = useState('')
  const [values, setValues] = useState<{ value: string; samples: number }[]>([])
  const [groups, setGroups] = useState<string[]>([])
  const [problem, setProblem] = useState('')
  const fail = (e: unknown) => setProblem(e instanceof Error ? e.message : String(e))
  useEffect(() => { if (open && !options) analysisOptions().then(o => { setOptions(o); setFile(o.files.find(f => f.startsWith('protein')) ?? o.files[0] ?? '') }).catch(fail) }, [open, options])
  useEffect(() => {
    if (!(open && file && kind === 'mean_by_group')) return
    let current = true                                     // only the answer to the latest typing counts
    rowNames(file, row).then(r => { if (current) setRows(r.rows) }).catch(() => { if (current) setRows([]) })
    return () => { current = false }
  }, [open, file, row, kind])
  useEffect(() => { setGroups([]); setValues([]); if (column) columnValues(column).then(v => setValues(v.values)).catch(fail) }, [column])
  const ready = column && (kind === 'category_mix' || (file && row.trim() && groups.length > 0))
  const submit = async () => {
    setProblem('')
    try {
      const spec = kind === 'category_mix' ? { type: kind, column, title: `Mix of ${column}` }
        : { type: kind, file, row: row.trim(), column, groups, title: `${row.trim()} by ${column}` }
      const made = await addAnalysis(spec)
      setOpen(false); setRow(''); setColumn(''); onAdded(made.id)
    } catch (e) { fail(e) }
  }
  if (!open) return <li className="analysis add"><button type="button" className="ghost" onClick={() => setOpen(true)}>Add an analysis of your own</button>
    <p className="quiet">Describe another result you rely on and the tool will protect it the same way.</p></li>
  return (
    <li className="analysis on add-form">
      <b className="form-title">A new analysis</b>
      <fieldset className="kinds">
        <label><input type="radio" name="kind" checked={kind === 'mean_by_group'} onChange={() => setKind('mean_by_group')} /> Compare a measurement between groups</label>
        <label><input type="radio" name="kind" checked={kind === 'category_mix'} onChange={() => setKind('category_mix')} /> Count tumours in each category</label>
      </fieldset>
      {kind === 'mean_by_group' && <>
        <label>Which file holds the measurement?
          <select id="add-file" value={file} onChange={e => { setFile(e.target.value); setRow('') }}>{(options?.files ?? []).map(f => <option key={f}>{f}</option>)}</select></label>
        <label>Which row? Start typing a name.
          <input id="add-row" value={row} onChange={e => setRow(e.target.value)} list="add-rows" placeholder="For example HER2" autoComplete="off" spellCheck={false} />
          <datalist id="add-rows">{rows.map(r => <option key={r} value={r} />)}</datalist></label>
      </>}
      <label>{kind === 'mean_by_group' ? 'Split the samples by which clinical column?' : 'Which clinical column?'}
        <select id="add-column" value={column} onChange={e => setColumn(e.target.value)}><option value="">Choose a column</option>{(options?.columns ?? []).map(c => <option key={c}>{c}</option>)}</select></label>
      {kind === 'mean_by_group' && values.length > 0 && (
        <fieldset className="groups"><legend>Which groups to compare? Pick two for a difference.</legend>
          {values.map(v => <label key={v.value}><input type="checkbox" checked={groups.includes(v.value)} onChange={e => setGroups(g => e.target.checked ? [...g, v.value] : g.filter(x => x !== v.value))} /> {v.value} <span className="quiet">({v.samples})</span></label>)}
        </fieldset>
      )}
      {problem && <p className="error inline" role="alert">{problem}</p>}
      <p className="form-actions"><button type="button" className="primary" disabled={!ready} onClick={submit}>Add it to the question</button>
        <button type="button" className="link" onClick={() => setOpen(false)}>Cancel</button></p>
    </li>
  )
}

/** The one number that best says what happened to an analysis. */
function headlineNumber(a: Analysis): string {
  const before = flat(a.before), after = flat(a.after)
  if (!before || !after) return ''
  const moved = Object.keys(after).filter(k => JSON.stringify(before[k]) !== JSON.stringify(after[k]))
  const key = moved.includes('difference') ? 'difference' : moved[0]
  return key ? `${words(key)} ${shown(before[key])} to ${shown(after[key])}` : ''
}

// ---- bringing in a new release ----------------------------------------------------------------------------------------
/** Every file in what was dropped: loose files, or the files inside a dropped folder (two levels deep is plenty). */
async function droppedFiles(data: DataTransfer): Promise<{ files: File[]; name: string }> {
  const entries = Array.from(data.items).map(i => i.webkitGetAsEntry?.()).filter((e): e is FileSystemEntry => !!e)
  if (entries.length === 0) return { files: Array.from(data.files), name: data.files[0]?.name ?? '' }
  const asFile = (e: FileSystemFileEntry) => new Promise<File>((ok, no) => e.file(ok, no))
  const children = (d: FileSystemDirectoryEntry) => new Promise<FileSystemEntry[]>((ok, no) => {
    const reader = d.createReader(); const all: FileSystemEntry[] = []
    const more = () => reader.readEntries(batch => { if (batch.length === 0) ok(all); else { all.push(...batch); more() } }, no)
    more()
  })
  const files: File[] = []
  const walk = async (e: FileSystemEntry, depth: number) => {
    if (e.isFile) files.push(await asFile(e as FileSystemFileEntry))
    else if (e.isDirectory && depth < 3) for (const child of await children(e as FileSystemDirectoryEntry)) await walk(child, depth + 1)
  }
  for (const e of entries) await walk(e, 0)
  return { files, name: entries[0].name }
}

/** The audit report is produced for a named person. It asks who is running it once, and remembers. */
function ReportButton({ asked }: { asked: string[] }) {
  const [name, setName] = useState(() => remembered('readyset-reviewer'))
  const [role, setRole] = useState(() => remembered('readyset-role'))
  const [asking, setAsking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState('')
  const produce = async () => {
    if (!name.trim()) { setAsking(true); return }
    try { localStorage.setItem('readyset-reviewer', name); localStorage.setItem('readyset-role', role) } catch { /* storage may be off */ }
    setBusy(true); setProblem('')
    try {
      const url = URL.createObjectURL(new Blob([await auditReport(asked, name.trim(), role.trim())], { type: 'text/html' }))
      const a = Object.assign(document.createElement('a'), { href: url, download: 'audit-report.html' })
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
      setAsking(false)
    } catch (e) { setProblem(e instanceof Error ? e.message : String(e)) }
    setBusy(false)
  }
  return (
    <div className="report-button">
      {asking && (
        <form className="who report-who" onSubmit={e => { e.preventDefault(); void produce() }}>
          <p className="wide">An audit report says who ran it. Who is producing this one?</p>
          <label>Your name<input id="report-name" value={name} onChange={e => setName(e.target.value)} placeholder="Name" autoComplete="name" autoFocus /></label>
          <label>Your role<input id="report-role" value={role} onChange={e => setRole(e.target.value)} placeholder="Research engineer" /></label>
        </form>
      )}
      <p>
        <button type="button" className="primary" disabled={busy || (asking && !name.trim())} onClick={() => void produce()}>{busy ? 'Writing the report…' : 'Download the audit report'}</button>
        {!asking && name.trim() && <span className="quiet report-as"> as {name.trim()}{role.trim() ? `, ${role.trim()}` : ''}. <button type="button" className="link" onClick={() => setAsking(true)}>Change</button></span>}
      </p>
      {problem && <p className="error inline" role="alert">{problem}</p>}
    </div>
  )
}

// Every comparison made on this computer, so a person can go back to an earlier release and see what had changed.
function History({ state, onLoaded }: { state: ReleaseState; onLoaded: (s: ReleaseState) => void }) {
  const [past, setPast] = useState<PastComparison[]>([])
  const [problem, setProblem] = useState('')
  useEffect(() => { let on = true; void pastComparisons().then(p => { if (on) setPast(p) }); return () => { on = false } }, [state.trusted, state.new])
  if (past.length === 0) return null
  const open = async (p: PastComparison) => {
    setProblem('')
    try { onLoaded(await setRelease({ trusted: p.trusted, path: p.new })) } catch (e) { setProblem(e instanceof Error ? e.message : String(e)) }
  }
  const when = (iso: string) => { const d = new Date(iso); return isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) }
  return (
    <details className="history">
      <summary>History: {plural(past.length, 'comparison')} on this computer</summary>
      <ol>
        {past.map(p => (
          <li key={`${p.trusted}|${p.new}`} className={p.current ? 'current' : undefined}>
            <div className="history-row">
              <span className="history-when">{when(p.first_compared)}</span>
              <span><code>{p.trusted_name}</code> <span aria-hidden="true">→</span> <code>{p.new_name}</code></span>
              <span className={`history-verdict ${(VERDICT[p.verdict] ?? { tone: 'insufficient' }).tone}`}>{p.verdict}</span>
              {p.current ? <span className="quiet">showing now</span>
                : p.available ? <button type="button" className="link" onClick={() => void open(p)}>Open it again</button>
                : <span className="quiet">its files are no longer on this computer</span>}
            </div>
            {p.changes.length > 0
              ? <ul>{p.changes.map(c => <li key={c.id}><strong>{c.id}</strong> {c.summary}{c.decision ? ` (${c.decision})` : ''}</li>)}</ul>
              : <p className="quiet">Nothing had changed.</p>}
          </li>
        ))}
      </ol>
      {problem && <p className="error inline" role="alert">{problem}</p>}
    </details>
  )
}

type Staged = { files: File[]; name: string }

/** One side of a comparison: files are collected here, and nothing runs until Compare is pressed. */
function SideBox({ id, title, hint, staged, using, busy, onAdd, onRemove, onClear }: {
  id: string; title: string; hint: string; staged: Staged; using?: string | null; busy: boolean
  onAdd: (files: File[], name: string) => void; onRemove: (name: string) => void; onClear: () => void
}) {
  const [over, setOver] = useState(false)
  const folder = useRef<HTMLInputElement>(null)
  const files = useRef<HTMLInputElement>(null)
  const zip = useRef<HTMLInputElement>(null)
  const drop = async (e: DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setOver(false)
    try { const got = await droppedFiles(e.dataTransfer); onAdd(got.files, got.name) } catch { /* the parent says what to do instead */ }
  }
  const size = (n: number) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} kB`)
  return (
    <div className={`side${over ? ' over' : ''}`} data-side={id} onDragOver={e => { e.preventDefault(); e.stopPropagation(); setOver(true) }} onDragLeave={() => setOver(false)} onDrop={drop}>
      <h3>{title}</h3>
      <p className="quiet">{hint}</p>
      {staged.files.length === 0 && using && <p className="side-using">Using <code>{using}</code>. Add files here to use a different one.</p>}
      {staged.files.length > 0 && (
        <ul className="staged">
          {staged.files.map(f => <li key={f.name}><code>{f.name}</code><span>{size(f.size)}</span><button type="button" className="link" disabled={busy} onClick={() => onRemove(f.name)} aria-label={`Remove ${f.name}`}>Remove</button></li>)}
        </ul>
      )}
      <p className="drop-buttons">
        <button type="button" className="ghost" disabled={busy} onClick={() => files.current?.click()}>{staged.files.length ? 'Add more files' : 'Choose files'}</button>
        <button type="button" className="ghost" disabled={busy} onClick={() => folder.current?.click()}>Choose a folder</button>
        <button type="button" className="ghost" disabled={busy} onClick={() => zip.current?.click()}>Choose a zip</button>
        {staged.files.length > 0 && <button type="button" className="link" disabled={busy} onClick={onClear}>Clear</button>}
      </p>
      <input ref={files} id={`${id}-files`} type="file" hidden multiple onChange={e => { const f = Array.from(e.target.files ?? []); if (f.length) onAdd(f, ''); e.target.value = '' }} />
      <input ref={folder} id={`${id}-folder`} type="file" hidden multiple {...{ webkitdirectory: '' }} onChange={e => { const f = Array.from(e.target.files ?? []); if (f.length) onAdd(f, (f[0].webkitRelativePath || '').split('/')[0] || ''); e.target.value = '' }} />
      <input ref={zip} id={`${id}-zip`} type="file" hidden accept=".zip" onChange={e => { const f = Array.from(e.target.files ?? []); if (f.length) onAdd(f, f[0].name); e.target.value = '' }} />
    </div>
  )
}

function ReleaseBox({ state, onLoaded }: { state: ReleaseState; onLoaded: (s: ReleaseState) => void }) {
  const [open, setOpen] = useState(!state.new)
  const [busy, setBusy] = useState('')
  const [problem, setProblem] = useState('')
  const [path, setPath] = useState('')
  const [trusted, setTrusted] = useState('')
  const [envelope, setEnvelope] = useState('')
  const [code, setCode] = useState('')
  const [before, setBefore] = useState<Staged>({ files: [], name: '' })
  const [after, setAfter] = useState<Staged>({ files: [], name: '' })
  const run = async (work: () => Promise<ReleaseState>) => {
    setProblem('')
    try { const next = await work(); setBusy(''); setOpen(!next.new); setPath(''); setBefore({ files: [], name: '' }); setAfter({ files: [], name: '' }); onLoaded(next) }
    catch (e) { setBusy(''); setProblem(e instanceof Error ? e.message : String(e)) }
  }
  // Files are collected, not sent: a release is usually several files, and the two sides may hold files of the same name.
  const [taken, setTaken] = useState('')
  const adder = (set: (change: (old: Staged) => Staged) => void, other: () => Staged) => (files: File[], name: string) => {
    const isZip = (f: File) => f.name.toLowerCase().endsWith('.zip')
    // A packed file that someone unpacked to edit keeps its place: x.tsv stands in for x.tsv.gz.
    const stem = (n: string) => n.replace(/\.gz$/i, '').replace(/\.(tsv|csv|xlsx|txt|numbers)$/i, '').toLowerCase()
    // People rename files: "clinical updated.csv", "protein v2.xlsx". The word that says which table it is decides.
    const words: [RegExp, string][] = [[/clinic/, 'clinical'], [/surviv/, 'survival'], [/mutation/, 'mutation_gene_level'], [/protein|rppa/, 'protein_rppa'],
      [/copy.?number|gistic|cnv/, 'copy_number_gistic'], [/rna|hiseq|expression/, 'rna_hiseq']]
    const guesses: string[] = []
    const loose = files.filter(f => !isZip(f) && !f.name.startsWith('.') && !state.files.some(k => k === f.name || stem(k) === stem(f.name)))
    const byWord = (n: string) => { const hit = words.filter(([re]) => re.test(stem(n))); return hit.length === 1 ? state.files.find(k => stem(k) === hit[0][1]) ?? '' : '' }
    // One file on each side is a person comparing two versions of one table, whatever the second is called.
    const lone = other().files.length === 1 && !isZip(other().files[0]) && files.filter(f => !isZip(f) && !f.name.startsWith('.')).length === 1 ? other().files[0].name : ''
    const proper = (n: string) => {
      const exact = state.files.find(f => f === n) ?? state.files.find(f => stem(f) === stem(n))
      if (exact) return exact
      const guess = byWord(n) || (loose.length === 1 ? lone : '')
      if (guess) guesses.push(`${n} is taken as ${guess}`)
      return guess
    }
    const byName = new Map<string, File>()
    const both: string[] = []
    for (const f of files) {
      if (isZip(f)) { byName.set(f.name, f); continue }
      const n = proper(f.name)
      if (!n) continue
      const had = byName.get(n)
      if (had) both.push(n)
      if (!had || f.lastModified >= had.lastModified) byName.set(n, f.name === n ? f : new File([f], n, { type: f.type, lastModified: f.lastModified }))
    }
    const wanted = [...byName.values()]
    const left = files.filter(f => !isZip(f) && !f.name.startsWith('.') && ![...byName.values()].some(k => k === f || (k.size === f.size && k.lastModified === f.lastModified))).map(f => f.name)
    setTaken([...new Set(guesses)].join('. ') + (guesses.length ? '.' : ''))
    setProblem(left.length && wanted.length === 0
      ? `None of those is one of a release's files. A release's files are named ${state.files.map(f => f.replace(/\.tsv(\.gz)?$/, '')).join(', ')} (as .tsv, .csv or .xlsx; a name that contains one of those words works too), or give a zip of them.`
      : [left.length ? `Left out, because ${left.length === 1 ? 'it is not one' : 'they are not'} of a release's files: ${left.slice(0, 6).join(', ')}.` : '',
         both.length ? `Both a packed and an unpacked copy of ${both.join(', ')} were there. The one changed most recently was used.` : ''].filter(Boolean).join(' '))
    if (wanted.length === 0) return
    set(old => {
      const zipped = wanted.find(isZip)
      if (zipped) return { files: [zipped], name: name || zipped.name }                         // a zip is the whole release
      const kept = old.files.filter(f => !isZip(f) && !wanted.some(w => w.name === f.name))     // a file chosen again replaces the earlier one
      return { files: [...kept, ...wanted], name: name || old.name }
    })
  }
  const addBefore = adder(setBefore, () => after), addAfter = adder(setAfter, () => before)
  const canCompare = after.files.length > 0 && (before.files.length > 0 || !!state.trusted) && !busy
  const compare = () => run(async () => {
    setBusy('Reading')
    if (before.files.length) await uploadRelease(before.files, before.name || 'before', state.files, setBusy, 'trusted')
    return uploadRelease(after.files, after.name || 'after', state.files, setBusy)
  })
  // A drop anywhere on the page adds to the After side, so nobody has to aim.
  useEffect(() => {
    const enter = (e: globalThis.DragEvent) => { if (e.dataTransfer?.types.includes('Files')) { e.preventDefault(); setOpen(true) } }
    const dropped = async (e: globalThis.DragEvent) => {
      if (!e.dataTransfer?.types.includes('Files') || (e.target as HTMLElement | null)?.closest?.('.side')) return
      e.preventDefault()
      try { const got = await droppedFiles(e.dataTransfer); addAfter(got.files, got.name) } catch { setProblem('That could not be read. Use the Choose buttons instead.') }
    }
    window.addEventListener('dragover', enter); window.addEventListener('drop', dropped)
    return () => { window.removeEventListener('dragover', enter); window.removeEventListener('drop', dropped) }
  }, [state.files])   // eslint-disable-line react-hooks/exhaustive-deps

  if (!open && state.new) {
    return (
      <section className="release-line" aria-label="The two releases">
        <p>Comparing the trusted release <code>{state.trusted_name}</code> with the new release <code>{state.new_name}</code>.</p>
        <button type="button" className="ghost small" onClick={() => setOpen(true)}>Compare a different release</button>
        <History state={state} onLoaded={onLoaded} />
      </section>
    )
  }
  return (
    <section className="release-box" aria-label="Compare two releases">
      <div className="block-row">
        <h2 className="block-title">Compare two releases</h2>
        {state.new && <button type="button" className="link" onClick={() => setOpen(false)}>Close</button>}
      </div>
      <p className="block-sub">Put the trusted release on the left and the new one on the right, then press Compare. Add as many files as each has; the two sides can hold files with the same names. Nothing runs until you press Compare.</p>
      <div className="sides">
        <SideBox id="before" title="Before: the trusted release" hint="The version your results were made with." staged={before} using={state.trusted_name} busy={!!busy}
          onAdd={addBefore} onRemove={n => setBefore(o => ({ ...o, files: o.files.filter(f => f.name !== n) }))} onClear={() => setBefore({ files: [], name: '' })} />
        <SideBox id="after" title="After: the new release" hint="The version you want to check. Dropping files anywhere on the page adds them here." staged={after} busy={!!busy}
          onAdd={addAfter} onRemove={n => setAfter(o => ({ ...o, files: o.files.filter(f => f.name !== n) }))} onClear={() => setAfter({ files: [], name: '' })} />
      </div>
      <p className="compare-row">
        <button type="button" className="primary big-compare" disabled={!canCompare} onClick={compare}>{busy ? `${busy}…` : 'Compare'}</button>
        {!busy && !canCompare && <span className="quiet">{after.files.length === 0 ? 'Add the new release on the right.' : 'Add the trusted release on the left.'}</span>}
      </p>
      {taken && <p className="taken-note" role="status">{taken} Rename it if that is wrong.</p>}
      {problem && <p className="error inline" role="alert">{problem}</p>}
      <form className="path-row envelope-row" onSubmit={e => { e.preventDefault(); if (envelope.trim() && code.trim()) { setBusy('Opening the envelope'); run(() => openEnvelope(envelope.trim(), code.trim())) } }}>
        <label htmlFor="envelope-number">Or open a sealed envelope: its number and its four words</label>
        <input id="envelope-number" className="short" value={envelope} onChange={e => setEnvelope(e.target.value)} placeholder="07" spellCheck={false} autoComplete="off" />
        <input id="envelope-code" value={code} onChange={e => setCode(e.target.value)} placeholder="amber falcon river quartz" spellCheck={false} autoComplete="off" aria-label="The four words" />
        <button type="submit" className="primary" disabled={!envelope.trim() || code.trim().split(/\s+/).length !== 4 || !!busy}>Open and compare</button>
      </form>
      <details className="dev-mode">
        <summary>Or give paths on this computer</summary>
        <form className="path-row" onSubmit={e => { e.preventDefault(); if (trusted.trim()) run(() => setRelease({ trusted: trusted.trim() })) }}>
          <label htmlFor="trusted-path">The trusted release's folder</label>
          <input id="trusted-path" value={trusted} onChange={e => setTrusted(e.target.value)} placeholder="/path/to/oncosys-hackathon-challenge/data/tcga-brca/raw" spellCheck={false} />
          <button type="submit" className="primary" disabled={!trusted.trim() || !!busy}>Use this</button>
        </form>
        <form className="path-row" onSubmit={e => { e.preventDefault(); if (path.trim()) { setBusy('Comparing'); run(() => setRelease({ path: path.trim() })) } }}>
          <label htmlFor="new-path">The new release's folder or zip</label>
          <input id="new-path" value={path} onChange={e => setPath(e.target.value)} placeholder="/Users/you/Desktop/hidden-release" spellCheck={false} disabled={!state.trusted} />
          <button type="submit" className="primary" disabled={!path.trim() || !state.trusted || !!busy}>Compare</button>
        </form>
      </details>
      <History state={state} onLoaded={onLoaded} />
      <details className="dev-mode">
        <summary>Developer mode</summary>
        <p>Everything on this page can also be run from a terminal, for scripts and pipelines. Compare two releases: <code>python3 -m control_tower compare TRUSTED NEW --out findings.json</code>. Open an envelope: <code>python3 -m control_tower envelope 07 amber falcon river quartz</code>. The README has the rest.</p>
      </details>
    </section>
  )
}

// ---- the page ------------------------------------------------------------------------------------------------------
function Bench({ raw, onQuestion, onChanged, release }: { raw: Findings; onQuestion: (ids: string[]) => void; onChanged: () => void; release?: ReactNode }) {
  const doc = useMemo(() => read(raw), [raw])
  const ids = doc.findings.map(f => f.id)
  const fromHash = () => { const h = decodeURIComponent(location.hash.slice(1)); return ids.includes(h) ? h : ids[0] }
  const [selected, setSelected] = useState(fromHash)
  useEffect(() => {
    const onHash = () => setSelected(fromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  })
  const current = ids.includes(selected) ? selected : ids[0]
  const go = (id: string) => { setSelected(id); try { history.replaceState(null, '', `#${id}`) } catch { /* not allowed here */ } }
  const step = (by: number) => {
    const next = ids[Math.min(ids.length - 1, Math.max(0, ids.indexOf(current) + by))]
    if (next) { go(next); document.getElementById('changes')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  }
  const onKeys = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); step(e.key === 'ArrowRight' ? 1 : -1) }
  }

  // Decisions recorded while no server could keep them (the built-in example) live here until the page is closed.
  const [local, setLocal] = useState<Record<string, Review | null>>({})
  const reviewOf = (id: string): Review | undefined => (id in local ? local[id] ?? undefined : doc.reviews.find(r => r.finding === id))
  const onReview = async (f: Finding, r: ReviewInput) => {
    const key = doc.reviewKeys[f.id] ?? f.id
    const kept = await saveReview({ key, ...r })
    if (kept) { setLocal(({ [f.id]: _gone, ...rest }) => rest); onChanged() }
    else setLocal(prev => ({ ...prev, [f.id]: r.status === 'cleared' ? null : { finding: f.id, key, status: r.status, fix: r.fix, reviewer: r.reviewer, role: r.role, note: r.note, at: new Date().toISOString() } }))
  }
  const reviewed = doc.findings.filter(f => reviewOf(f.id)).length
  // One decision for every change still waiting, each recorded on its own in the person's name.
  const onAll = async (r: ReviewInput) => {
    const waiting = doc.findings.filter(f => !reviewOf(f.id))
    const note = [r.note, `Decided together with ${waiting.length - 1} other ${waiting.length - 1 === 1 ? 'change' : 'changes'}.`].filter(Boolean).join(' ')
    let kept = true
    for (const f of waiting) kept = (await saveReview({ key: doc.reviewKeys[f.id] ?? f.id, ...r, note })) && kept
    if (kept) { setLocal({}); onChanged() }
    else setLocal(prev => ({ ...prev, ...Object.fromEntries(waiting.map(f => [f.id, { finding: f.id, key: doc.reviewKeys[f.id] ?? f.id, status: r.status, fix: r.fix, reviewer: r.reviewer, role: r.role, note, at: new Date().toISOString() } as Review])) }))
  }
  const toggle = (id: string) => {
    const next = doc.asked.includes(id) ? doc.asked.filter(a => a !== id) : doc.available.map(a => a.id).filter(a => a === id || doc.asked.includes(a))
    if (next.length) onQuestion(next)
  }

  const verdict = text(raw.verdict)
  const tone = VERDICT[verdict] ?? { tone: 'insufficient', mark: '?', means: '' }
  const touching = doc.findings.filter(f => Array.isArray(f.affects_analyses) && f.affects_analyses.length > 0).length
  const changed = doc.files.filter(f => f.status !== 'unchanged' && f.status !== 'absent' && f.status !== 'not_in_both')
  const compared = doc.files.filter(f => f.status !== 'absent' && f.status !== 'not_in_both').length
  const finding = doc.findings.find(f => f.id === current)
  const reached = (id: string) => doc.findings.some(f => Array.isArray(f.affects_analyses) && f.affects_analyses.includes(id))
  const newName = doc.releases[1] ?? 'the new release'
  const choices = doc.available.length ? doc.available : doc.asked.map(id => ({ id, title: text(doc.titles[id]) }))

  return (
    <div className="page">
      {release}
      <section className={`hero ${tone.tone}`} aria-label="The answer">
        <p className="ask-line">Can I use <code>{newName}</code> for my analyses?</p>
        <h1 role="status"><span className="mark" aria-hidden="true">{tone.mark}</span>{(HEADLINE[verdict] ?? (() => verdict || 'No verdict'))(touching, doc.findings.length)}</h1>
        <p className="means">{verdict === 'Ready' && doc.findings.length > 0
          ? `Nothing these analyses read has changed. ${plural(doc.findings.length, 'change')} elsewhere in the release ${doc.findings.length === 1 ? 'is' : 'are'} listed below: real problems in the data, but not for these analyses.`
          : tone.means}</p>
        {(verdict === 'Insufficient Evidence' || verdict === 'Blocked') && doc.findings.filter(f => /could not be read|cannot be compared for this file|shape of/.test(text(f.summary))).slice(0, 2).map(f => (
          <p key={f.id} className="means-why"><strong>Why:</strong> {text(f.summary).replace(/^.*so the two releases cannot be compared for this file\.\s*/, '')}</p>
        ))}
        <p className="facts">
          <span className="verdict-chip">Verdict: {verdict || 'none'}</span>
          {doc.files.length > 0 && <span>{changed.length === 0 ? `All ${compared} compared files are identical`
            : (['changed', 'missing_in_one', 'unreadable'] as const).filter(k => changed.some(f => f.status === k)).map(k =>
                `${changed.filter(f => f.status === k).length} of ${compared} files ${k === 'changed' ? 'changed' : k === 'unreadable' ? 'unreadable' : 'missing from one release'}: ${changed.filter(f => f.status === k).map(f => f.file.replace(/\.tsv(\.gz)?$/, '')).join(', ')}`).join('; ')}</span>}
          {doc.findings.length > 0 && touching < doc.findings.length && <span>{doc.findings.length - touching} {doc.findings.length - touching === 1 ? 'change does' : 'changes do'} not reach your analyses</span>}
          {doc.notes.map((n, i) => <span key={i} className={/not compared/.test(n) ? undefined : 'warn'}>{/not compared/.test(n) ? n.split('. ')[0].replace(/ is in .* but not in .*/, ' is not in the new release and is not needed') : n}</span>)}
        </p>
        <p className="basis">
          {(() => {
            const when = text(raw.x_readyset?.generated_at)
            const d = when ? new Date(when) : null
            const same = doc.files.filter(f => f.status === 'unchanged').length
            const rerun = doc.analyses.filter(a => a.status === 'changed' || a.status === 'unchanged').length
            return <>
              {d && !isNaN(d.getTime()) && <span>Checked {d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}{typeof raw.x_readyset?.run_seconds === 'number' ? `, in ${raw.x_readyset.run_seconds} s` : ''}.</span>}
              {compared > 0 && <span>{plural(compared, 'file')} read in full{same > 0 ? `, ${same} exactly identical` : ''}.</span>}
              {rerun > 0 && <span>{plural(rerun, 'result')} rerun on both releases, not estimated.</span>}
              <span>No AI wrote this answer.</span>
            </>
          })()}
          <button type="button" className="link" onClick={showMethod}>How it works and how it was tested</button>
        </p>
      </section>

      {choices.length > 0 && (
        <section className="block" aria-label="What you need the release for">
          <h2 className="block-title">What I need it for</h2>
          <p className="block-sub">{doc.available.length ? 'These are your analyses. Switch one off and the answer above changes.' : 'The analyses this result was worked out for.'}</p>
          <ul className="analyses">
            {choices.map(a => {
              const on = doc.asked.includes(a.id)
              const analysis = doc.analyses.find(x => x.id === a.id)
              const status = text(analysis?.status)
              return (
                <li key={a.id} className={`analysis${on ? ' on' : ''} ${on ? `is-${status}` : ''}`}>
                  <div className="analysis-top">
                    {doc.available.length > 0 && (
                      <button type="button" role="switch" aria-checked={on} className="switch" disabled={on && doc.asked.length === 1}
                        title={on && doc.asked.length === 1 ? 'Keep at least one analysis' : on ? 'Leave this analysis out' : 'Include this analysis'}
                        aria-label={`${on ? 'Leave out' : 'Include'} ${a.title || a.id}`} onClick={() => toggle(a.id)}><span /></button>
                    )}
                    <div className="analysis-name"><span className="ref">{a.id}</span><b>{a.title || `Analysis ${a.id}`}</b></div>
                  </div>
                  {on && analysis
                    ? <p className={`outcome ${reached(a.id) && status === 'not_rerun' ? 'stuck' : status}`}>{status === 'changed' ? `Result changed: ${headlineNumber(analysis)}${doc.findings.filter(f => Array.isArray(f.affects_analyses) && f.affects_analyses.includes(a.id)).length > 1 ? ' (all changes together)' : ''}`
                        : status === 'unchanged' ? 'Rerun. The result is the same.'
                        : reached(a.id) ? `Could not be rerun ${text(analysis.note).replace(/^(Affected, but )?could not be (re)?run /i, '')}`
                        : 'Untouched. Nothing it reads has changed.'}</p>
                    : <p className="outcome off">Left out of the question.</p>}
                  {on && analysis && (analysis.before || analysis.after) && <More title="See the numbers"><ResultTable analysis={analysis} releases={doc.releases} /></More>}
                </li>
              )
            })}
            {doc.available.length > 0 && <AddAnalysis onAdded={id => onQuestion([...doc.asked, id])} />}
          </ul>
        </section>
      )}

      <section className="block" id="changes" aria-label="What changed" onKeyDown={onKeys}>
        <div className="block-row">
          <h2 className="block-title">{doc.findings.length === 0 ? 'Nothing changed' : `${plural(doc.findings.length, 'change')} to look at`}</h2>
          {doc.findings.length > 0 && (
            <p className="progress" aria-label={`${reviewed} of ${doc.findings.length} decided`}>
              <span className="bar"><span style={{ width: `${(100 * reviewed) / doc.findings.length}%` }} /></span>{reviewed} of {doc.findings.length} decided
            </p>
          )}
        </div>
        {doc.findings.length === 0 && <p className="block-sub">The two releases hold the same values in every file.</p>}
        {doc.findings.length > 0 && <>
          <p className="block-sub">Open each one, check the proof, and decide. The arrow keys move between them.</p>
          <ol className="steps" role="tablist" aria-label="Changes">
            {doc.findings.map((f, i) => {
              const r = reviewOf(f.id)
              return (
                <li key={f.id}>
                  <button type="button" role="tab" aria-selected={f.id === current} className={`stepper${f.id === current ? ' on' : ''}${r ? ` ${r.status}` : ''}`} onClick={() => go(f.id)}>
                    <span className="num" aria-hidden="true">{r ? (r.status === 'confirmed' ? '✓' : '–') : i + 1}</span>
                    <span className="stepper-text"><b>{titleOf(f)}</b>
                      <small>{r ? (r.status === 'confirmed' ? 'Confirmed' : 'Dismissed')
                        : Array.isArray(f.affects_analyses) && f.affects_analyses.length ? 'Waiting for you' : 'Does not reach your analyses'}{' '}
                        <span className={`sev sev-${text(f.severity)}`}>{text(f.severity)}{!(Array.isArray(f.affects_analyses) && f.affects_analyses.length) && text(f.severity) === 'low' ? ' for these analyses' : ''}</span></small></span>
                  </button>
                </li>
              )
            })}
          </ol>
          {finding && <ChangePanel finding={finding} doc={doc} index={ids.indexOf(finding.id)} total={ids.length} review={reviewOf(finding.id)} onReview={onReview} step={step} waiting={doc.findings.length - reviewed} onAll={onAll} />}
        </>}
      </section>

      <SectionBoundary name="files"><FilesAndDownload raw={raw} doc={doc} /></SectionBoundary>
    </div>
  )
}

export default function App() {
  const { theme, toggle } = useTheme()
  const [doc, setDoc] = useState<unknown>()
  const [error, setError] = useState('')
  const [asked, setAsked] = useState<string[] | undefined>()
  const [working, setWorking] = useState(false)
  const load = (ids?: string[]) => {
    setWorking(true)
    return loadFindings(ids).then(d => { setDoc(d); setError('') }).catch(e => setError(e instanceof Error ? e.message : String(e))).finally(() => setWorking(false))
  }
  useEffect(() => { load() }, [])
  const onQuestion = (ids: string[]) => { setAsked(ids); load(ids) }
  const [state, setState] = useState<ReleaseState | null>(null)
  useEffect(() => { releaseState().then(setState) }, [])
  // The envelope command can hand the page a new release from the terminal: notice it and show it.
  useEffect(() => {
    const timer = setInterval(async () => {
      const next = await releaseState()
      if (next && state && (next.new !== state.new || next.trusted !== state.trusted)) { setDoc(undefined); setState(next); setAsked(undefined); load() }
    }, 2000)
    return () => clearInterval(timer)
  })
  const onLoaded = (next: ReleaseState) => { setDoc(undefined); setState(next); setAsked(undefined); try { history.replaceState(null, '', location.pathname) } catch { /* fine */ } load() }
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
        {state?.trusted && !state.new
          ? <p className="pair">Trusted <code>{state.trusted_name}</code></p>
          : releases.length === 2 && <p className="pair">Trusted <code>{releases[0]}</code> <span aria-hidden="true">→</span> new <code>{releases[1]}</code></p>}
        {!(state?.trusted && !state.new) && <a className="header-link" href="#files">Get the report</a>}
        <button type="button" className="theme-toggle" onClick={toggle} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}>{theme === 'dark' ? '☀' : '☾'}</button>
      </header>
      <main>
        {error && <p className="error" role="alert">{error}</p>}
        {doc === undefined && !error && <p className="quiet pad">Comparing the two releases…</p>}
        {doc !== undefined && !valid && <p className="error" role="alert">findings.json did not contain a result.</p>}
        {raw && !(state?.trusted && !state.new) && (usingExample || raw.x_readyset?.example_notice) && (
          <p className="demo-note">{raw.x_readyset?.example_notice ?? 'Showing the hand-written example file.'}</p>
        )}
        {working && raw && <p className="working" role="status">Comparing the two releases…</p>}
        {state?.trusted && !state.new && (
          <div className="page"><ReleaseBox key={`${state.trusted}|waiting`} state={state} onLoaded={onLoaded} />
            <p className="waiting-note">Nothing is being compared yet. Give it a new release and the answer appears here.</p></div>
        )}
        {raw && !(state?.trusted && !state.new) && <SectionBoundary name="result"><div className={working ? 'stale' : undefined}><Bench raw={raw} onQuestion={onQuestion} onChanged={() => load(asked)}
          release={state && <ReleaseBox key={`${state.trusted}|${state.new}`} state={state} onLoaded={onLoaded} />} /></div></SectionBoundary>}
      </main>
      {raw && valid && !usingExample && !(state?.trusted && !state.new) && <Ask asked={asked} onChanged={() => load(asked)} canUseModel={state?.ai_understanding} voice={!!state?.voice} offerKey={state !== null && state.ai_understanding !== undefined} />}
      <DataView />
      <Method version={text(raw?.x_readyset?.engine_version)} />
      <footer>
        <p><strong>ReadySet Control Tower</strong>{raw?.x_readyset?.engine_version ? `, engine ${text(raw.x_readyset.engine_version)}` : ''}. Built by team Automyte (Ahmed Hussein, Ordi, James) for the OncoSys Cancer AI Lab, November 2026.</p>
        <p>Open source under Apache-2.0: <a href="https://github.com/a7ussein/readyset-control-tower" target="_blank" rel="noreferrer">the code, the tests and the method</a>. <button type="button" className="link" onClick={showMethod}>How it works and how it was tested</button></p>
        <p>Data: TCGA breast cancer (TCGA-BRCA), de-identified. Research use only. Not a clinical tool: it makes no diagnosis, treatment advice or risk score.</p>
      </footer>
    </>
  )
}
