// The shell: header, theme, loading findings.json, footer. The real screen goes where the comment below says.
// Everything it shows comes from findings.json (docs/OUTPUT-CONTRACT.md). It computes no numbers.
import { useEffect, useState } from 'react'
import './App.css'
import './screen.css'
import { loadFindings, usingExample } from './api'
import type { Findings } from './findings'
import { useTheme } from './theme'
import { Analyses } from './Analyses'
import { FindingsList } from './FindingsList'
import { Repairs } from './Repairs'

function getVerdictInfo(verdict?: string) {
  if (!verdict) return null
  const key = verdict.toLowerCase().replace(/ /g, '-')
  if (key === 'ready') return { className: 'ready', mark: '✓', text: verdict }
  if (key === 'conditional') return { className: 'conditional', mark: '!', text: verdict }
  if (key === 'blocked') return { className: 'blocked', mark: '×', text: verdict }
  if (key === 'insufficient-evidence') return { className: 'insufficient-evidence', mark: '?', text: verdict }
  return { className: 'unknown', mark: '?', text: verdict }
}

export function VerdictBanner({ doc }: { doc: Findings }) {
  const verdictInfo = getVerdictInfo(doc.verdict)
  const findingsCount = doc.findings?.length ?? 0
  const analyses = doc.analyses ?? []
  const rerunCount = analyses.filter(a => a.status !== 'not_rerun').length
  const registeredCount = doc.x_readyset?.analyses_registered?.length ?? analyses.length
  const repairsCount = doc.repairs?.length ?? 0
  const runSeconds = doc.x_readyset?.run_seconds

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
        {findingsCount} {findingsCount === 1 ? 'finding' : 'findings'},{' '}
        {rerunCount} of {registeredCount} analyses rerun,{' '}
        {repairsCount} proposed {repairsCount === 1 ? 'repair' : 'repairs'}
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

export function FileStrip({ files }: { files?: { file: string; status: string; opened: boolean }[] }) {
  if (!files || files.length === 0) {
    return <p className="file-strip-empty muted">No per-file status in this file.</p>
  }

  return (
    <ul className="file-strip" aria-label="Per-file status">
      {files.map(f => {
        const statusClass = getFileStatusClass(f.status)
        const statusWords = getFileStatusWords(f.status)
        const openedWords = f.opened ? 'opened' : 'not opened'
        return (
          <li key={f.file} className={`file-row ${statusClass}`}>
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
  const [doc, setDoc] = useState<Findings>()
  const [error, setError] = useState('')
  useEffect(() => { loadFindings().then(setDoc).catch(e => setError(e instanceof Error ? e.message : String(e))) }, [])

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
      {doc && <>
        {(usingExample || doc.x_readyset?.example_notice) && <p className="demo-note">{doc.x_readyset?.example_notice ?? 'Showing the hand-written example file.'}</p>}
        <div className="workspace-heading">
          <div>
            <h1>{doc.question || 'Comparison'}</h1>
            <p>{doc.data?.releases?.map(r => r.name).filter(Boolean).join(' compared with ') || 'No release information'}</p>
          </div>
        </div>

        {/* Piece 1: VerdictBanner and FileStrip */}
        <VerdictBanner doc={doc} />
        <FileStrip files={doc.x_readyset?.files} />

        {/* Piece 2: Analyses */}
        <Analyses analyses={doc.analyses} />

        {/* Piece 3: Findings */}
        <FindingsList findings={doc.findings} />

        {/* Piece 4: Proposed repairs */}
        <Repairs
          repairs={doc.repairs}
          findingIds={(doc.findings ?? []).map(f => f.id).filter((id): id is string => typeof id === 'string')}
        />

        {/* Pieces still to build:
            1. download: export of findings.json with the validator's result
        */}
      </>}
    </main>
    <footer>Built by team Automyte. De-identified TCGA research data. Research use only, not a clinical tool.</footer>
  </>
}
