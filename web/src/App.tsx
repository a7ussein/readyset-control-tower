// The shell: header, theme, loading findings.json, footer. The real screen goes where the comment below says.
// Everything it shows comes from findings.json (docs/OUTPUT-CONTRACT.md). It computes no numbers.
import { useEffect, useState } from 'react'
import './App.css'
import './screen.css'
import { loadFindings, usingExample } from './api'
import type { Finding, Findings } from './findings'
import { useTheme } from './theme'
import { Analyses } from './Analyses'
import { FindingsList } from './FindingsList'
import { Repairs } from './Repairs'
import { ResultDetails } from './ResultDetails'
import { SectionBoundary } from './SectionBoundary'

function getVerdictInfo(verdict?: string) {
  if (typeof verdict !== 'string' || !verdict) return null
  const key = verdict.toLowerCase().replace(/ /g, '-')
  if (key === 'ready') return { className: 'ready', mark: '✓', text: verdict }
  if (key === 'conditional') return { className: 'conditional', mark: '!', text: verdict }
  if (key === 'blocked') return { className: 'blocked', mark: '×', text: verdict }
  if (key === 'insufficient-evidence') return { className: 'insufficient-evidence', mark: '?', text: verdict }
  return { className: 'unknown', mark: '?', text: verdict }
}

export function VerdictBanner({ doc }: { doc: Findings }) {
  const verdictInfo = typeof doc.verdict === 'string' ? getVerdictInfo(doc.verdict) : null

  const findingsPart =
    doc.findings !== undefined && !Array.isArray(doc.findings)
      ? 'findings could not be read'
      : `${Array.isArray(doc.findings) ? doc.findings.length : 0} ${
          Array.isArray(doc.findings) && doc.findings.length === 1 ? 'finding' : 'findings'
        }`

  const analyses = Array.isArray(doc.analyses) ? doc.analyses : []
  const rerunCount = analyses.filter(a => a && typeof a === 'object' && a.status !== 'not_rerun').length
  const registeredCount = Array.isArray(doc.x_readyset?.analyses_registered)
    ? doc.x_readyset.analyses_registered.length
    : analyses.length

  const analysesPart =
    doc.analyses !== undefined && !Array.isArray(doc.analyses)
      ? 'analyses could not be read'
      : `${rerunCount} of ${registeredCount} analyses rerun`

  const repairsCount = Array.isArray(doc.repairs) ? doc.repairs.length : 0
  const repairsPart =
    doc.repairs !== undefined && !Array.isArray(doc.repairs)
      ? 'proposed repairs could not be read'
      : `${repairsCount} proposed ${repairsCount === 1 ? 'repair' : 'repairs'}`

  const runSeconds =
    typeof doc.x_readyset?.run_seconds === 'number' && !isNaN(doc.x_readyset.run_seconds)
      ? doc.x_readyset.run_seconds
      : undefined

  return (
    <div className="verdict-banner">
      {verdictInfo ? (
        <p className={`verdict ${verdictInfo.className}`} role="status">
          <span className="verdict-mark" aria-hidden="true">{verdictInfo.mark}</span>
          {verdictInfo.text}
        </p>
      ) : (
        <p className="verdict-missing muted" role="status">This file has no verdict.</p>
      )}
      <p className="verdict-summary">
        {findingsPart},{' '}
        {analysesPart},{' '}
        {repairsPart}
        {typeof runSeconds === 'number' && ` · compared in ${runSeconds} s`}
      </p>
    </div>
  )
}

function getFileStatusWords(status: string): string {
  switch (status) {
    case 'changed':
      return 'changed'
    case 'unchanged':
      return 'unchanged'
    case 'absent':
      return 'in neither release'
    case 'missing_in_one':
      return 'missing in one release'
    case 'unreadable':
      return 'unreadable'
    default:
      return status || 'unknown'
  }
}

function getFileStatusClass(status: string): string {
  switch (status) {
    case 'changed':
      return 'status-conditional'
    case 'unchanged':
      return 'status-ready'
    case 'missing_in_one':
    case 'unreadable':
      return 'status-blocked'
    default:
      return 'status-neutral'
  }
}

export function FileStrip({ files }: { files?: unknown }) {
  if (!Array.isArray(files) || files.length === 0) {
    return <p className="file-strip-empty muted">No per-file status in this file.</p>
  }

  const validFiles = files.filter(
    (f): f is { file: string; status: string; opened: boolean } =>
      Boolean(f && typeof f === 'object' && typeof (f as { file?: unknown }).file === 'string')
  )

  if (validFiles.length === 0) {
    return <p className="file-strip-empty muted">No per-file status in this file.</p>
  }

  return (
    <ul className="file-strip" aria-label="Per-file status">
      {validFiles.map((f, idx) => {
        const statusClass = getFileStatusClass(f.status)
        const statusWords = getFileStatusWords(f.status)
        const openedWords = f.opened ? 'opened' : 'not opened'
        return (
          <li key={`${f.file}-${idx}`} className={`file-row ${statusClass}`}>
            <span className={`file-mark ${statusClass}`} aria-hidden="true" />
            <code className="file-name">{f.file}</code>
            <span className={`file-status ${statusClass}`}>{statusWords}</span>
            <span className="file-opened muted">{openedWords}</span>
          </li>
        )
      })}
    </ul>
  )
}

export default function App() {
  const { theme, toggle } = useTheme()
  const [doc, setDoc] = useState<unknown>()
  const [error, setError] = useState('')
  useEffect(() => { loadFindings().then(setDoc).catch(e => setError(e instanceof Error ? e.message : String(e))) }, [])

  const isDocValid: boolean = doc !== null && typeof doc === 'object' && !Array.isArray(doc)
  const typedDoc = isDocValid ? (doc as Findings) : null

  const releaseNames = typedDoc && Array.isArray(typedDoc.data?.releases)
    ? typedDoc.data.releases
        .map(r => (r && typeof r === 'object' && typeof r.name === 'string' ? r.name : ''))
        .filter(Boolean)
        .join(' compared with ')
    : ''

  const findingIds = typedDoc && Array.isArray(typedDoc.findings)
    ? typedDoc.findings
        .filter(f => f && typeof f === 'object' && !Array.isArray(f))
        .map(f => (f as Finding).id)
        .filter((id): id is string => typeof id === 'string')
    : []

  return <>
    <header className="app-header">
      <a className="wordmark" href="./">
        <img className="logo-light" src="/brand/mark-light.png" alt="" />
        <img className="logo-dark" src="/brand/mark-dark.png" alt="" />
        ReadySet
      </a>
      <span className="cohort-meta">Control Tower</span>
      <button className="theme-toggle icon" style={{ marginLeft: 'auto' }} onClick={toggle} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}>{theme === 'dark' ? '☀' : '☾'}</button>
    </header>
    <main>
      {error && <p className="error" role="alert">{error}</p>}
      {!doc && !error && <p className="muted">Loading findings…</p>}
      {doc !== undefined && !isDocValid && (
        <p className="error" role="alert">findings.json did not contain a result.</p>
      )}
      {typedDoc && <>
        {(usingExample || typedDoc.x_readyset?.example_notice) && <p className="demo-note">{typedDoc.x_readyset?.example_notice ?? 'Showing the hand-written example file.'}</p>}
        <div className="workspace-heading">
          <div>
            <h1>{typedDoc.question || 'Comparison'}</h1>
            <p>{releaseNames || 'No release information'}</p>
          </div>
        </div>

        {/* Piece 1: VerdictBanner and FileStrip */}
        <SectionBoundary name="verdict banner">
          <VerdictBanner doc={typedDoc} />
        </SectionBoundary>
        <SectionBoundary name="file strip">
          <FileStrip files={typedDoc.x_readyset?.files} />
        </SectionBoundary>

        {/* Piece 2: Analyses */}
        <SectionBoundary name="analyses">
          <Analyses analyses={typedDoc.analyses} />
        </SectionBoundary>

        {/* Piece 3: Findings */}
        <SectionBoundary name="findings">
          <FindingsList findings={typedDoc.findings} />
        </SectionBoundary>

        {/* Piece 4: Proposed repairs */}
        <SectionBoundary name="repairs">
          <Repairs repairs={typedDoc.repairs} findingIds={findingIds} />
        </SectionBoundary>

        {/* Piece 5: Result details & download */}
        <SectionBoundary name="result details">
          <ResultDetails doc={typedDoc} />
        </SectionBoundary>

        {/* Pieces still to build:
            Only hardening and polish remain.
        */}
      </>}
    </main>
    <footer>Built by team Automyte. De-identified TCGA research data. Research use only, not a clinical tool.</footer>
  </>
}
