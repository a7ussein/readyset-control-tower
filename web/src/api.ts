// The only place the page talks to the server.
import type { Findings } from './findings'
import example from '../../docs/example-findings.json'

// The built page talks to whichever server delivered it. `npm run dev` uses the local server on :8010.
const base = (import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8010' : '')).replace(/\/$/, '')

// `?example=1` shows the hand-written example with no server at all.
export const usingExample = new URLSearchParams(location.search).get('example') === '1'

export async function loadFindings(analyses?: string[]): Promise<Findings> {
  if (usingExample) return example as unknown as Findings
  let response: Response
  const query = analyses && analyses.length ? `?for=${encodeURIComponent(analyses.join(','))}` : ''
  try { response = await fetch(`${base}/api/findings${query}`) } catch {
    throw new Error('Cannot reach the local server. Start it with ./run.sh, or add ?example=1 to the address to see the example file.')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `The server answered ${response.status}.`)
  }
  return response.json()
}

/** Record (or clear) a person's review of a finding. Resolves to false when there is no server to keep it. */
export async function saveReview(review: { key: string; status: 'confirmed' | 'dismissed' | 'cleared'; fix?: 'approved' | ''; reviewer?: string; role?: string; note?: string }): Promise<boolean> {
  if (usingExample) return false
  try {
    // text/plain keeps this a simple request; the server reads the body as JSON and checks where it came from.
    const response = await fetch(`${base}/api/reviews`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(review) })
    return response.ok
  } catch { return false }
}

export interface ReleaseState { trusted: string | null; new: string | null; trusted_name: string | null; new_name: string | null; files: string[]; ai_understanding?: string; voice?: boolean }

async function answer(response: Response): Promise<ReleaseState> {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `The server answered ${response.status}.`)
  return body as ReleaseState
}

/** Which two releases the page is comparing. Null when there is no server (the built-in example). */
export async function releaseState(): Promise<ReleaseState | null> {
  if (usingExample) return null
  try { return await answer(await fetch(`${base}/api/state`)) } catch { return null }
}

/** Point the page at a release by its path on this computer: a folder or a zip. */
export async function setRelease(change: { path?: string; trusted?: string }): Promise<ReleaseState> {
  return answer(await fetch(`${base}/api/release`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(change) }))
}

/** Send dropped files (the release's own files, or one zip) and compare them. `progress` is told what is being sent. */
export async function uploadRelease(files: File[], name: string, known: string[], progress: (text: string) => void): Promise<ReleaseState> {
  const wanted = files.filter(f => known.includes(f.name) || f.name.toLowerCase().endsWith('.zip'))
  if (wanted.length === 0) throw new Error(`None of the release's files were in what you dropped. Looking for ${known.slice(0, 2).join(', ')} and the others, or a zip of them.`)
  const batch = (crypto.randomUUID ? crypto.randomUUID() : `drop-${Date.now()}-${Math.random().toString(16).slice(2)}`).replace(/[^A-Za-z0-9-]/g, '')
  for (const [i, file] of wanted.entries()) {
    progress(`Reading ${file.name} (${i + 1} of ${wanted.length})`)
    const response = await fetch(`${base}/api/upload?batch=${batch}&name=${encodeURIComponent(file.name)}`, { method: 'POST', body: file })
    if (!response.ok) await answer(response)
  }
  progress('Comparing')
  return answer(await fetch(`${base}/api/release`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ batch, name }) }))
}

/** Where the plain-English audit report for the current question can be downloaded. Null when there is no server. */
export function reportUrl(analyses: string[]): string | null {
  if (usingExample) return null
  return `${base}/api/report${analyses.length ? `?for=${encodeURIComponent(analyses.join(','))}` : ''}`
}

export interface AnalysisOptions { columns: string[]; files: string[] }
async function json<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `The server answered ${response.status}.`)
  return body as T
}
/** What a new analysis can be built from, read from the trusted release. */
export const analysisOptions = async () => json<AnalysisOptions>(await fetch(`${base}/api/options`))
export const columnValues = async (column: string) => json<{ values: { value: string; samples: number }[]; distinct: number }>(await fetch(`${base}/api/options?column=${encodeURIComponent(column)}`))
export const rowNames = async (file: string, typed: string) => json<{ rows: string[]; total: number }>(await fetch(`${base}/api/options?file=${encodeURIComponent(file)}&q=${encodeURIComponent(typed)}`))
export const addAnalysis = async (spec: Record<string, unknown>) => json<{ id: string; title: string }>(await fetch(`${base}/api/question`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(spec) }))

export interface AskReply {
  question: string; can_answer: boolean; understood_as: string | null; understood_by?: string; intent: string | null; answer: string[]
  trace: { step: string; detail: string }[]; suggestions: string[]; fingerprint: string; based_on: string
  sources: { finding: string; file: string; samples: string[]; check?: { row: string; releases: string[]; values: { sample: string; before: string; after: string }[] } }[]
  action: { finding: string; key: string; status: 'confirmed' | 'dismissed'; fix: 'approved' | ''; reviewer: string; role: string; note: string } | null
  consistency?: { asked: number; different_answers: number; fingerprint: string }
}
/** Ask a question in plain words. Answered from the findings by fixed patterns: no language model. */
export const askQuestion = async (body: { q: string; for?: string; name?: string; role?: string; check?: number; ai?: boolean }) =>
  json<AskReply>(await fetch(`${base}/api/ask`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(body) }))

/** Open a sealed envelope (its number and four-word code) and compare its release with the trusted one. */
export const openEnvelope = async (number: string, words: string) =>
  answer(await fetch(`${base}/api/envelope`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ number, words }) }))

/** Give (or, with an empty string, forget) the user's own Anthropic key. Kept in the local tool's memory only. */
export const setModelKey = async (key: string) =>
  json<{ ai_understanding: string }>(await fetch(`${base}/api/model-key`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ key }) }))

/** Where the change log (a spreadsheet, one row per affected sample) can be downloaded. Null when there is no server. */
export function changelogUrl(analyses: string[]): string | null {
  if (usingExample) return null
  return `${base}/api/changelog${analyses.length ? `?for=${encodeURIComponent(analyses.join(','))}` : ''}`
}

export interface PastComparison {
  trusted: string; new: string; trusted_name: string; new_name: string; verdict: string; first_compared: string; last_changed: string
  changes: { id: string; kind: string; severity: string; summary: string; decision: string }[]
  available: boolean; current: boolean
}
/** Every comparison this tool has made on this computer, newest first. Empty when there is no server. */
export async function pastComparisons(): Promise<PastComparison[]> {
  if (usingExample) return []
  try { return (await json<{ comparisons: PastComparison[] }>(await fetch(`${base}/api/history`))).comparisons ?? [] } catch { return [] }
}

/** An answer read aloud in a natural voice, as a playable address. Null when the tool has no voice key. */
export async function spokenAudio(text: string): Promise<string | null> {
  try {
    const response = await fetch(`${base}/api/speak`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ text }) })
    return response.ok ? URL.createObjectURL(await response.blob()) : null
  } catch { return null }
}
