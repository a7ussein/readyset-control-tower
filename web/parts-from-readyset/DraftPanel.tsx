import { useEffect, useState } from 'react';
import { api, errorMessage } from './api';
import type { Question } from './api';
import { Panel } from './Panel';
export function DraftPanel({ open, cohort, onClose, onDraft }: {
    open: boolean;
    cohort: string;
    onClose: () => void;
    onDraft: (q: Question) => void;
}) {
    const [status, setStatus] = useState<{
        available: boolean;
        reason: string;
    }>(), [text, setText] = useState(''), [error, setError] = useState(''), [running, setRunning] = useState(false), [elapsed, setElapsed] = useState(0), [done, setDone] = useState('');
    useEffect(() => { if (open && !status)
        api.draftStatus().then(setStatus).catch(e => setStatus({ available: false, reason: errorMessage(e) })); }, [open, status]);
    useEffect(() => { if (!running)
        return; const start = Date.now(); const t = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000); return () => clearInterval(t); }, [running]);
    async function draft() { setRunning(true); setElapsed(0); setError(''); setDone(''); try {
        const q = await api.draft(text, cohort);
        onDraft(q);
        setDone('Draft added to the comparison. Review its bar and sources before approval.');
    }
    catch (e) {
        setError(errorMessage(e));
    }
    finally {
        setRunning(false);
    } }
    const progress = running ? <p role="status" className="notice">{elapsed < 15 ? 'Reading the question' : elapsed < 40 ? 'Writing the rules' : 'Finding sources'}… {elapsed}s elapsed. Usually 30–90 seconds. You can close this panel and keep working.</p> : null;
    if (!open)
        return running ? <div className="draft-progress">{progress}</div> : done ? <div className="draft-progress" role="status">{done}<button onClick={() => setDone('')} aria-label="Dismiss draft notification">×</button></div> : null;
    return <Panel label="Ask a new question" onClose={onClose}><div className="panel-heading"><h2>Ask a new question</h2><button className="icon close-button" aria-label="Close" onClick={onClose}><svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.8"/></svg></button></div><p>Draft a bar for <strong>{cohort}</strong>.</p><p className="muted">Write the question in plain words. You will review the thresholds and sources before approving it.</p>{!status && <p role="status">Checking the local drafting model…</p>}{status && !status.available && <p className="notice">{status.reason}</p>}<label className="question-input">Your question<textarea rows={6} minLength={12} maxLength={400} disabled={!status?.available || running} value={text} onChange={e => setText(e.target.value)} placeholder="Can this cohort support a model predicting 2-year survival in stage III lung cancer?"/></label><p className="muted">{text.length} of 400 characters</p><button className="primary" disabled={!status?.available || running || text.trim().length < 12} onClick={() => void draft()}>Draft the bar</button>{progress}{error && <p role="alert" className="error">{error}</p>}{done && <p role="status" className="notice">{done}</p>}</Panel>;
}
