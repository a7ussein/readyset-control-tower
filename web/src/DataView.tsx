// The data itself: the two files side by side for the samples a change names, exactly as written, with the cells that
// differ marked. Opened from a change on the page or from a source in the Ask panel, so nobody has to take it on trust.
import { useEffect, useState } from 'react'
import { dataBehind, type DataView as View } from './api'

/** Open the data view for a change from anywhere on the page. */
export const showData = (finding: string) => window.dispatchEvent(new CustomEvent('readyset-show-data', { detail: finding }))

export function DataView() {
  const [finding, setFinding] = useState<string | null>(null)
  const [view, setView] = useState<View | null>(null)
  const [problem, setProblem] = useState('')
  const [onlyChanged, setOnlyChanged] = useState(true)

  useEffect(() => {
    const open = (e: Event) => setFinding(String((e as CustomEvent).detail))
    window.addEventListener('readyset-show-data', open)
    return () => window.removeEventListener('readyset-show-data', open)
  }, [])
  useEffect(() => {
    if (!finding) return
    let on = true
    setView(null); setProblem(''); setOnlyChanged(true)
    dataBehind(finding).then(v => { if (on) setView(v) }).catch(e => { if (on) setProblem(e instanceof Error ? e.message : String(e)) })
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setFinding(null) }
    window.addEventListener('keydown', key)
    return () => { on = false; window.removeEventListener('keydown', key) }
  }, [finding])

  if (!finding) return null
  const rows = view ? (onlyChanged && view.rows_that_differ > 0 ? view.rows.filter(r => r.changed) : view.rows) : []
  const [old, fresh] = view ? [view.releases[0], view.releases[view.releases.length - 1]] : ['', '']
  const cell = (text: string | null) => (text === null ? <span className="absent">not in this release</span> : text === '' ? <span className="absent">blank</span> : text)
  return (
    <div className="data-back" onClick={e => { if (e.target === e.currentTarget) setFinding(null) }}>
      <section className="data-view" role="dialog" aria-modal="true" aria-label="The data behind this change">
        <header>
          <div>
            <h2>The data behind {finding}{view ? <> in <code>{view.file}</code></> : null}</h2>
            <p>Read straight from the two files, exactly as written. Nothing is rounded. Cells that differ between <code>{old || 'the trusted release'}</code> and <code>{fresh || 'the new release'}</code> are marked.</p>
          </div>
          <button type="button" className="ask-close" onClick={() => setFinding(null)} aria-label="Close">×</button>
        </header>
        {!view && !problem && <p className="quiet pad">Opening the two files…</p>}
        {problem && <p className="error inline" role="alert">{problem}</p>}
        {view && <>
          {view.note && <p className="data-note">{view.note}</p>}
          <p className="data-count">
            {view.rows_in_file !== null
              ? <>{view.rows_that_differ} of {view.rows_in_file} rows differ for {view.samples.length === 1 ? 'this sample' : `these ${view.samples.length} samples`}. Each row is {view.what_a_row_is}.</>
              : <>Each row is {view.what_a_row_is}.</>}
            {view.more_samples > 0 && <> {view.more_samples} more {view.more_samples === 1 ? 'sample is' : 'samples are'} involved and not shown.</>}
            {view.rows_in_file !== null && view.rows_that_differ > 0 && view.rows_that_differ < view.rows_in_file && (
              <label><input id="data-only-changed" type="checkbox" checked={onlyChanged} onChange={e => setOnlyChanged(e.target.checked)} /> Only rows that differ</label>
            )}
          </p>
          <div className="data-scroll">
            <table>
              <thead>
                <tr><th rowSpan={2}>{view.what_a_row_is.startsWith('a column') ? 'Clinical column' : 'Row'}</th>
                  {view.samples.map(s => <th key={s.id} colSpan={2} className="sample">{s.id}</th>)}</tr>
                <tr>{view.samples.map(s => [<th key={s.id + 'a'} className="rel">{old}</th>, <th key={s.id + 'b'} className="rel">{fresh}</th>])}</tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.name}>
                    <th>{r.name}</th>
                    {r.cells.map((c, i) => [
                      <td key={i + 'a'} className={c.changed ? 'was' : undefined}>{cell(c.before)}</td>,
                      <td key={i + 'b'} className={c.changed ? 'now' : undefined}>{cell(c.after)}</td>,
                    ])}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {view.rows_left_out > 0 && <p className="quiet">{view.rows_left_out} more rows are in the file and not shown here.</p>}
        </>}
      </section>
    </div>
  )
}
