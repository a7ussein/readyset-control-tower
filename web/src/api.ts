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
export async function saveReview(review: { key: string; status: 'confirmed' | 'dismissed' | 'cleared'; reviewer?: string; role?: string; note?: string }): Promise<boolean> {
  if (usingExample) return false
  try {
    // text/plain keeps this a simple request; the server reads the body as JSON and checks where it came from.
    const response = await fetch(`${base}/api/reviews`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(review) })
    return response.ok
  } catch { return false }
}
