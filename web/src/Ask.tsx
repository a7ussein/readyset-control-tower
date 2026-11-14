// Ask: a person asks about this comparison in plain words (typed or spoken) and gets an answer built from the
// findings by fixed patterns. No language model. Every answer shows how it was reached and a fingerprint that is
// the same every time the same question is asked of the same findings.
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { askQuestion, saveReview, type AskReply } from './api'

const STARTERS = ['Can I use the new release?', 'Why does it matter for my results?', 'What should I do next?',
  'What can the tool not tell me?', 'Will you give the same answer next time?']
const remembered = (key: string) => { try { return localStorage.getItem(key) ?? '' } catch { return '' } }
const remember = (key: string, value: string) => { try { localStorage.setItem(key, value) } catch { /* not kept */ } }

interface Turn { id: number; q: string; reply?: AskReply; problem?: string; recorded?: 'yes' | 'failed'; checking?: boolean }
type Listener = { start: () => void; stop: () => void; onresult: ((e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null; lang: string; interimResults: boolean }

export function Ask({ asked, onChanged }: { asked?: string[]; onChanged: () => void }) {
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [text, setText] = useState('')
  const [name, setName] = useState(() => remembered('readyset-reviewer'))
  const [role, setRole] = useState(() => remembered('readyset-role'))
  const [aloud, setAloud] = useState(false)
  const [listening, setListening] = useState(false)
  const next = useRef(1)
  const end = useRef<HTMLDivElement>(null)
  const heard = useRef<Listener | null>(null)
  const Recognition = (window as unknown as Record<string, unknown>).SpeechRecognition ?? (window as unknown as Record<string, unknown>).webkitSpeechRecognition
  const canSpeak = typeof window.speechSynthesis !== 'undefined'

  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [turns, open])
  useEffect(() => { if (!open && canSpeak) window.speechSynthesis.cancel() }, [open, canSpeak])
  const patch = (id: number, change: Partial<Turn>) => setTurns(all => all.map(t => (t.id === id ? { ...t, ...change } : t)))
  const body = (q: string) => ({ q, for: asked?.join(','), name: name.trim(), role: role.trim() })

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q) return
    const id = next.current++
    setTurns(all => [...all, { id, q }])
    setText('')
    try {
      const reply = await askQuestion(body(q))
      patch(id, { reply })
      if (aloud && canSpeak) { window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance(reply.answer.slice(0, 3).join(' '))) }
    } catch (e) { patch(id, { problem: e instanceof Error ? e.message : 'The question could not be answered.' }) }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); void ask(text) }

  const again = async (t: Turn) => {
    patch(t.id, { checking: true })
    try { patch(t.id, { reply: { ...t.reply!, consistency: (await askQuestion({ ...body(t.q), check: 100 })).consistency }, checking: false }) }
    catch { patch(t.id, { checking: false }) }
  }
  const record = async (t: Turn) => {
    const a = t.reply?.action
    if (!a) return
    const kept = await saveReview({ key: a.key, status: a.status, fix: a.fix, reviewer: a.reviewer, role: a.role, note: a.note })
    patch(t.id, { recorded: kept ? 'yes' : 'failed' })
    if (kept) onChanged()
  }
  const listen = () => {
    if (listening) { heard.current?.stop(); return }
    const r = new (Recognition as new () => Listener)()
    r.lang = 'en-US'; r.interimResults = false
    r.onresult = e => { const said = e.results[0][0].transcript; setText(said); void ask(said) }
    r.onend = () => setListening(false)
    r.onerror = () => setListening(false)
    heard.current = r
    setListening(true)
    try { r.start() } catch { setListening(false) }
  }

  if (!open) return <button type="button" className="ask-open" onClick={() => setOpen(true)}>Ask about this release</button>
  return (
    <section className="ask" aria-label="Ask about this release">
      <header>
        <div>
          <h2>Ask about this release</h2>
          <p>Answers come only from the findings. No language model: the same question always gets the same answer.</p>
        </div>
        <button type="button" className="ask-close" onClick={() => setOpen(false)} aria-label="Close">×</button>
      </header>
      <div className="ask-who">
        <span>Working for</span>
        <input id="ask-name" value={name} placeholder="Your name" aria-label="Your name" onChange={e => { setName(e.target.value); remember('readyset-reviewer', e.target.value) }} />
        <input id="ask-role" value={role} placeholder="Your role" aria-label="Your role" onChange={e => { setRole(e.target.value); remember('readyset-role', e.target.value) }} />
      </div>
      <div className="ask-log" aria-live="polite">
        {turns.length === 0 && (
          <div className="ask-start">
            <p>Ask in your own words, or start with one of these. To record a decision, say for example “confirm F1”. It has your rights on this page and no more.</p>
            {STARTERS.map(s => <button key={s} type="button" className="ask-chip" onClick={() => void ask(s)}>{s}</button>)}
          </div>
        )}
        {turns.map(t => (
          <div key={t.id} className="ask-turn">
            <p className="ask-q">{t.q}</p>
            {!t.reply && !t.problem && <p className="quiet">Reading the findings…</p>}
            {t.problem && <p className="error inline" role="alert">{t.problem}</p>}
            {t.reply && (
              <div className={`ask-a${t.reply.can_answer ? '' : ' cannot'}`}>
                {t.reply.understood_as && <p className="ask-as">Understood as: {t.reply.understood_as}</p>}
                {t.reply.answer.map((line, i) => <p key={i}>{line}</p>)}
                {t.reply.action && t.recorded !== 'yes' && (
                  <button type="button" className="primary" onClick={() => void record(t)}>Record it as {t.reply.action.reviewer}</button>
                )}
                {t.recorded === 'yes' && <p className="ask-done">Recorded in your name. It is now in the findings file and the audit report.</p>}
                {t.recorded === 'failed' && <p className="error inline" role="alert">It could not be recorded.</p>}
                <details>
                  <summary>How I got this answer</summary>
                  <ol className="ask-trace">{t.reply.trace.map((s, i) => <li key={i}><strong>{s.step}.</strong> {s.detail}</li>)}</ol>
                </details>
                <p className="ask-proof">
                  Answer fingerprint <code>{t.reply.fingerprint}</code>
                  {t.reply.consistency
                    ? <span className="ask-same"> Asked {t.reply.consistency.asked} more times: {t.reply.consistency.different_answers === 1 ? 'the same answer every time' : `${t.reply.consistency.different_answers} different answers`}, fingerprint <code>{t.reply.consistency.fingerprint}</code>.</span>
                    : <button type="button" className="ask-again" disabled={t.checking} onClick={() => void again(t)}>{t.checking ? 'Asking…' : 'Ask it 100 more times'}</button>}
                </p>
              </div>
            )}
          </div>
        ))}
        <div ref={end} />
      </div>
      <form className="ask-form" onSubmit={submit}>
        <input id="ask-text" value={text} onChange={e => setText(e.target.value)} placeholder="Ask a question" aria-label="Your question" maxLength={500} autoComplete="off" />
        {Boolean(Recognition) && (
          <button type="button" className={`ask-mic${listening ? ' on' : ''}`} onClick={listen} aria-pressed={listening}
            title="Speak your question. Your browser turns speech into text and may use its maker's service to do it. The data itself never leaves this computer.">{listening ? 'Listening…' : 'Speak'}</button>
        )}
        <button type="submit" className="primary" disabled={!text.trim()}>Ask</button>
      </form>
      {canSpeak && <label className="ask-aloud"><input id="ask-aloud" type="checkbox" checked={aloud} onChange={e => setAloud(e.target.checked)} /> Read answers aloud</label>}
    </section>
  )
}
