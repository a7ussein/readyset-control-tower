// The method, in the words of a paper's Methods section: what the tool does, how it was tested, what it cannot tell
// you, and who made it. A result is easier to trust when the way it was reached is one click away.
import { useEffect, useState } from 'react'

/** Open the method panel from anywhere on the page. */
export const showMethod = () => window.dispatchEvent(new CustomEvent('readyset-show-method'))

export function Method({ version }: { version?: string }) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const show = () => setOpen(true)
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('readyset-show-method', show); window.addEventListener('keydown', key)
    return () => { window.removeEventListener('readyset-show-method', show); window.removeEventListener('keydown', key) }
  }, [])
  if (!open) return null
  return (
    <div className="data-back" onClick={e => { if (e.target === e.currentTarget) setOpen(false) }}>
      <section className="data-view method" role="dialog" aria-modal="true" aria-label="How it works and how it was tested">
        <header>
          <div>
            <h2>How it works and how it was tested</h2>
            <p>The method behind every answer on this page, and the evidence that it does what it says.</p>
          </div>
          <button type="button" className="ask-close" onClick={() => setOpen(false)} aria-label="Close">×</button>
        </header>
        <div className="method-body">
          <h3>What it does</h3>
          <ol>
            <li><strong>Reads every file in full</strong>, in both releases, and reduces each to a fingerprint (SHA-256). Files whose fingerprints match are identical byte for byte.</li>
            <li><strong>Fingerprints every sample</strong> in each file that differs: one fingerprint of everything that sample holds in that file.</li>
            <li><strong>Compares the fingerprints</strong> to name what happened: samples exchanged, copied under a new id, gone, arrived, relabelled, or blanked. Anything it cannot name is still reported, as a change it could not classify.</li>
            <li><strong>Works out which of your analyses each change reaches</strong>, from exactly which files, rows, columns and samples each analysis reads.</li>
            <li><strong>Reruns those analyses on both releases</strong> and shows the number before and after. Nothing is estimated.</li>
          </ol>
          <p>Values are compared as the exact text in the file. No language model is involved in finding a change, computing a result or writing a sentence: the same two releases always give the same answer. The one optional use of a model is in the Ask panel, to understand an unusually worded question. It is sent only the question, never the data, and it writes none of the answer.</p>

          <h3>What the words mean</h3>
          <ul>
            <li><strong>Ready</strong>: nothing your chosen analyses read has changed. <strong>Conditional</strong>: something they read changed; the results were rerun and a person must review. <strong>Blocked</strong>: an analysis can no longer be run. <strong>Insufficient Evidence</strong>: a file is missing or could not be read, so no answer is given.</li>
            <li><strong>Rerun</strong>: the analysis was computed again on both releases, so the two numbers shown are measured, not estimated.</li>
            <li><strong>Fingerprint</strong>: a short code computed from content. If two fingerprints match, the content is identical; if anything differs, they do not.</li>
            <li><strong>Confidence</strong>: how sure the tool is of what happened. High when the pattern is exact (two samples holding each other&rsquo;s values); low when values changed in a way it cannot name.</li>
          </ul>

          <h3>How a change is rated</h3>
          <ul>
            <li><strong>By what it does to your result</strong>, measured by rerunning the analysis with that one change alone. This is the organisers&rsquo; rule: rate each change by how much it could change the research answer, and say why.</li>
            <li><strong>The half-percent line.</strong> A result is usually quoted to three significant figures. A shift of about half a percent is where such a figure starts to read differently (3.05 becomes 3.07), so below it a change is rated a small effect and at or above it a large one. It is a stated convention, shown here so it can be challenged, not a validated standard.</li>
            <li><strong>Swaps and copies are rated high whatever they measure today.</strong> Which samples get exchanged or copied is chance, so a small effect this time says little about the next.</li>
            <li><strong>A change no chosen analysis reads is rated low for that question</strong> and stays listed, because it is still a real change in the data.</li>
          </ul>

          <h3>How it was tested</h3>
          <ul>
            <li><strong>Against an answer key.</strong> Run blind on the organisers&rsquo; practice release, it reported exactly what had been planted: the exchange, the five removed samples, the five copies and their sources, and nothing else.</li>
            <li><strong>Against the organisers&rsquo; own numbers.</strong> Its two built-in analyses give the same results as the organisers&rsquo; reference script on the trusted release.</li>
            <li><strong>By more than 100 automated tests</strong>, most on a small invented dataset where every expected answer can be checked by eye. They ship with the code.</li>
            <li><strong>By three reviews before submission</strong>: the organiser&rsquo;s review of the code, a judge-style run of the live page, and a rubric review. What they found was fixed, and what could not be fixed in time is listed below.</li>
            <li><strong>On hard inputs.</strong> Empty files, files saved by spreadsheet programs, shuffled rows and columns, repeated sample ids, renamed columns and files that are not tables: each gives an answer or a plain explanation, never a crash.</li>
          </ul>

          <h3>What it cannot tell you</h3>
          <ul>
            <li>Which of the two releases is correct. It shows that they differ, and how.</li>
            <li>Why a change happened. That is a question for the data provider.</li>
            <li>Whether two identical profiles are a copy or two real samples that happen to match.</li>
            <li>That a sample is a copy when a few of its values were altered. It reports that sample as changed, but only names a copy when every value matches.</li>
            <li>That 1.0 and 1 are the same number. Values are compared as the exact text in the file.</li>
            <li>Anything about an analysis it was not told about. It protects the questions you choose.</li>
            <li>Anything clinical. It says whether a research result still holds on a new release, and nothing about a patient.</li>
          </ul>

          <h3>Who made it, and where to check</h3>
          <p>Team Automyte: Ahmed Hussein, Ordi and James, for the OncoSys Cancer AI Lab (Cohort Firewall track), November 2026.{version ? ` Engine version ${version}.` : ''} The code, the tests and the measurements are public under the Apache-2.0 licence at <a href="https://github.com/a7ussein/readyset-control-tower" target="_blank" rel="noreferrer">github.com/a7ussein/readyset-control-tower</a>.</p>
          <p>Every statement on this page can be traced: open a change, then &ldquo;See the data in both files&rdquo; to read the cells it rests on.</p>
        </div>
      </section>
    </div>
  )
}
