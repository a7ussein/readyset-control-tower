// The shell: header, theme, loading findings.json, footer. The real screen goes where the comment below says.
// Everything it shows comes from findings.json (docs/OUTPUT-CONTRACT.md). It computes no numbers.
import { useEffect, useState } from 'react'
import './App.css'
import { loadFindings, usingExample } from './api'
import type { Findings } from './findings'
import { useTheme } from './theme'

const verdictClass = (verdict: string) => verdict.toLowerCase().replace(/ /g, '-')

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
        <div className="workspace-heading"><div><h1>{doc.question}</h1><p>{doc.data.releases.map(r => r.name).join(' compared with ')}</p></div></div>

        {/* ------------------------------------------------------------------------------------------
            THE SCREEN GOES HERE. What a judge needs on one screen, all of it already in `doc`:
              1. the verdict banner, with doc.x_readyset.run_seconds and one line per file (x_readyset.files)
              2. the findings: severity, confidence, sample ids, affects / does not affect, limitation, review flag
              3. the analyses: before and after, or "not rerun" with its note
              4. the proposed repairs, each tied to the findings it addresses
              5. a download of findings.json with the validator's result
            Reusable pieces from ReadySet are in web/parts-from-readyset/ (see web/README.md).
            What is below is a placeholder that proves the data arrives.
        ------------------------------------------------------------------------------------------- */}
        {doc.verdict && <p className={`verdict ${verdictClass(doc.verdict)}`} role="status">{doc.verdict}</p>}
        <p className="verdict-summary">
          {doc.findings.length} {doc.findings.length === 1 ? 'finding' : 'findings'}, {' '}
          {(doc.analyses ?? []).filter(a => a.status !== 'not_rerun').length} of {(doc.analyses ?? []).length} analyses rerun, {' '}
          {(doc.repairs ?? []).length} proposed {(doc.repairs ?? []).length === 1 ? 'repair' : 'repairs'}
        </p>
        <ul>{doc.findings.map(f => <li key={f.id}><code>{f.id}</code> {f.summary}</li>)}</ul>
      </>}
    </main>
    <footer>Built by team Automyte. De-identified TCGA research data. Research use only, not a clinical tool.</footer>
  </>
}
