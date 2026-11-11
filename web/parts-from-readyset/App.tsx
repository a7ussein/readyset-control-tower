import { useEffect, useRef, useState } from 'react';
import { api, demo, errorMessage } from './api';
import type { Assessment, Cohort, Definition, Finding, Question } from './api';
import { Panel } from './Panel';
import { BarPanel } from './BarPanel';
import { EvidencePanel } from './EvidencePanel';
import { VerdictColumn } from './VerdictColumn';
import { DraftPanel } from './DraftPanel';
import './App.css';
function App() {
    const [cohorts, setCohorts] = useState<Cohort[]>([]), [questions, setQuestions] = useState<Question[]>([]), [cohort, setCohort] = useState('synthetic_defects.csv'), [hidden, setHidden] = useState<string[]>([]), [definitions, setDefinitions] = useState<Record<string, Definition>>({}), [results, setResults] = useState<Record<string, Assessment>>({}), [errors, setErrors] = useState<Record<string, string>>({}), [busy, setBusy] = useState<Record<string, boolean>>({}), [error, setError] = useState(''), [loading, setLoading] = useState(true), [tuning, setTuning] = useState<string>(), [evidence, setEvidence] = useState<{
        finding: Finding;
        idField?: string;
    }>(), [ask, setAsk] = useState(false), [uploading, setUploading] = useState(false), [drag, setDrag] = useState(false);
    const input = useRef<HTMLInputElement>(null);
    const [theme, setTheme] = useState(() => { try {
        return localStorage.getItem('readyset-theme') ?? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    }
    catch {
        return 'light';
    } });
    useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
    useEffect(() => {
        const preference = matchMedia('(prefers-color-scheme: dark)');
        const update = () => {
            try { if (localStorage.getItem('readyset-theme')) return; } catch { /* Storage may be disabled. */ }
            setTheme(preference.matches ? 'dark' : 'light');
        };
        preference.addEventListener('change', update);
        return () => preference.removeEventListener('change', update);
    }, []);
    useEffect(() => { let live = true; Promise.all([api.cohorts(), api.questions(), api.proposals()]).then(([cs, qs, ps]) => { if (!live)
        return; setCohorts(cs); setQuestions([...qs, ...ps]); if (!cs.some(c => c.name === cohort))
        setCohort(cs[0]?.name ?? ''); }).catch(e => { if (live)
        setError(errorMessage(e)); }).finally(() => { if (live)
        setLoading(false); }); return () => { live = false; }; }, []);
    useEffect(() => { let live = true; setResults({}); setErrors({}); const timers = questions.map(q => { setBusy(b => ({ ...b, [q.name]: true })); return setTimeout(() => { api.assess(cohort, q.name, definitions[q.name] ?? (q.definition.provenance?.status === 'proposed' ? q.definition : undefined)).then(r => { if (live)
        setResults(rs => ({ ...rs, [q.name]: r })); }).catch(e => { if (live)
        setErrors(es => ({ ...es, [q.name]: errorMessage(e) })); }).finally(() => { if (live)
        setBusy(b => ({ ...b, [q.name]: false })); }); }, definitions[q.name] ? 300 : 0); }); return () => { live = false; timers.forEach(clearTimeout); }; }, [cohort, questions, definitions]);
    async function upload(file?: File) { if (!file)
        return; setUploading(true); setError(''); try {
        const c = await api.upload(file);
        setCohorts(cs => [...cs.filter(x => x.name !== c.name), c]);
        setCohort(c.name);
    }
    catch (e) {
        setError(errorMessage(e));
    }
    finally {
        setUploading(false);
    } }
    useEffect(() => { let depth = 0; const over = (e: DragEvent) => { if (e.dataTransfer?.types.includes('Files')) {
        e.preventDefault();
    } }; const enter = (e: DragEvent) => { if (e.dataTransfer?.types.includes('Files')) {
        e.preventDefault();
        depth++;
        setDrag(true);
    } }; const leave = () => { depth--; if (depth <= 0)
        setDrag(false); }; const drop = (e: DragEvent) => { e.preventDefault(); depth = 0; setDrag(false); void upload(e.dataTransfer?.files[0]); }; window.addEventListener('dragover', over); window.addEventListener('dragenter', enter); window.addEventListener('dragleave', leave); window.addEventListener('drop', drop); return () => { window.removeEventListener('dragover', over); window.removeEventListener('dragenter', enter); window.removeEventListener('dragleave', leave); window.removeEventListener('drop', drop); }; }, []);
    const chosen = cohorts.find(c => c.name === cohort), active = questions.find(q => q.name === tuning), visible = questions.filter(q => !hidden.includes(q.name));
    return <><header className="app-header"><a className="wordmark" href={demo ? '?demo=1' : './'}><img className="logo-light" src="/brand/mark-light.png" alt=""/><img className="logo-dark" src="/brand/mark-dark.png" alt=""/>ReadySet</a><div className="cohort-control"><label htmlFor="cohort">Cohort</label><select id="cohort" value={cohort} disabled={loading} onChange={e => setCohort(e.target.value)}>{cohorts.map(c => <option key={c.name}>{c.name}</option>)}</select></div><span className="cohort-meta">{chosen ? `${chosen.rows.toLocaleString()} ${chosen.rows === 1 ? 'row' : 'rows'}, ${chosen.columns.length} ${chosen.columns.length === 1 ? 'column' : 'columns'}` : 'Loading cohorts…'}</span><button onClick={() => input.current?.click()} disabled={uploading}>{uploading ? 'Uploading…' : 'Upload CSV'}</button><input hidden ref={input} type="file" accept=".csv,text/csv" onChange={e => { void upload(e.target.files?.[0]); e.target.value = ''; }}/><button className="theme-toggle icon" aria-label={`Use ${theme === 'dark' ? 'light' : 'dark'} theme`} onClick={() => { const next = theme === 'dark' ? 'light' : 'dark'; setTheme(next); try { localStorage.setItem('readyset-theme', next); } catch { /* Storage may be disabled. */ } }}>{theme === 'dark' ? '☀' : '☾'}</button></header>
 <main>{demo && <p className="demo-note">Offline preview. Real captured assessments; edits, uploads and drafting need the local API.</p>}{error && <p className="error" role="alert">{error} Try reloading after checking the API.</p>}<div className="workspace-heading"><div><h1>Is this data ready for…</h1><p>One cohort. A verdict for every question.</p></div><button className="primary" onClick={() => setAsk(true)}>Ask a new question</button></div>
 {hidden.length > 0 && <details className="add-question"><summary>Add a question ({hidden.length})</summary>{questions.filter(q => hidden.includes(q.name)).map(q => <button key={q.name} onClick={() => setHidden(h => h.filter(n => n !== q.name))}>{q.text}{q.definition.provenance?.status === 'proposed' ? ' — Unapproved draft' : ''}</button>)}</details>}
 {loading ? <div className="comparison skeleton-columns">{[1, 2, 3].map(n => <div className="skeleton" key={n}><i /><i /><i /></div>)}</div> : <section className={`comparison ${visible.length > 3 ? 'many' : ''}`} style={{ gridTemplateColumns: `repeat(${Math.max(1, visible.length)}, minmax(${visible.length > 3 ? '340px' : '0'}, 1fr))` }} aria-label="Questions assessed against the same cohort">{visible.map(q => <VerdictColumn key={q.name} question={q} result={results[q.name]} busy={!!busy[q.name]} error={errors[q.name]} tuned={!!definitions[q.name]} onApproved={approved => setQuestions(qs => qs.map(item => item.name === approved.name ? approved : item))} onDiscarded={() => setQuestions(qs => qs.filter(item => item.name !== q.name))} onHide={() => setHidden(h => [...h, q.name])} onTune={() => setTuning(q.name)} onFinding={finding => setEvidence({ finding, idField: results[q.name]?.bar.id_field })}/>)}</section>}{!loading && !visible.length && <p className="empty">Add a question above to compare its readiness.</p>}
 </main><footer>Built by team Automyte. Synthetic and public de-identified data only. Not a clinical-decision tool.</footer>
 {active && <Panel label="View the bar" onClose={() => setTuning(undefined)}><BarPanel question={active} value={definitions[active.name] ?? active.definition} result={results[active.name]} error={errors[active.name]} onChange={v => setDefinitions(ds => ({ ...ds, [active.name]: v }))} onReset={() => setDefinitions(ds => { const n = { ...ds }; delete n[active.name]; return n; })} onClose={() => setTuning(undefined)} onApproved={q => setQuestions(qs => qs.map(x => x.name === q.name ? q : x))} onDiscarded={() => { setQuestions(qs => qs.filter(q => q.name !== active.name)); setTuning(undefined); }}/></Panel>}
 {evidence && <EvidencePanel cohort={cohort} finding={evidence.finding} idField={evidence.idField} onClose={() => setEvidence(undefined)}/>}
 <DraftPanel open={ask} cohort={cohort} onClose={() => setAsk(false)} onDraft={q => setQuestions(qs => [...qs.filter(x => x.name !== q.name), q])}/>{drag && <div className="drop-state">Drop a CSV to assess this cohort</div>}</>;
}
export default App;
