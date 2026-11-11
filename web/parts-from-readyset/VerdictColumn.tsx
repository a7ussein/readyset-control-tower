import { useEffect, useRef, useState } from 'react';
import { api, citedIds, errorMessage } from './api';
import type { Assessment, Finding, Question } from './api';
export const names: Record<string, string> = { required_fields: 'Columns the question needs', input_tidying: 'How the file was read', value_range: 'Values in a believable range', population: 'Patients this question is about', completeness: 'Blank values', conditional_completeness: 'Blank where it is owed', value_set: 'Allowed values', date_order: 'Dates in order', followup_horizon: 'Follow-up reaches the time point', min_n: 'Enough patients', duplicate_ids: 'No patient twice', subgroup_n: 'Enough patients in the subgroup', distribution: 'Subgroup share', no_checks: 'Nothing was checked', no_rows: 'No data rows' };
const marks = { PASS: '✓', WARN: '!', FAIL: '×', UNKNOWN: '?' };
export const percent = (value: unknown) => `${Number((Number(value) * 100).toFixed(1))}%`;
// The engine writes the message from the rows it counted. Show it exactly as written: the page never recomputes a number.
export function findingMessage(finding: Finding) {
    return finding.evidence.missing_frac === null && finding.check === 'completeness' ? 'This column is not in the file.' : finding.message;
}
export function Chevron({ open = false }: { open?: boolean }) {
    return <svg className={`chevron ${open ? 'open' : ''}`} width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.8"/></svg>;
}
function ReportMenu({ download, copy, check }: { download: () => void; copy: () => void; check: () => void }) {
    const [open, setOpen] = useState(false);
    const root = useRef<HTMLDivElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    useEffect(() => {
        if (!open) return;
        const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
        document.addEventListener('pointerdown', outside);
        return () => document.removeEventListener('pointerdown', outside);
    }, [open]);
    function focusItem(index: number) {
        const items = root.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]');
        if (items?.length) items[(index + items.length) % items.length].focus();
    }
    return <div className="report-menu" ref={root} onKeyDown={event => {
        if (event.key === 'Escape') { event.stopPropagation(); setOpen(false); trigger.current?.focus(); }
        if (event.key === 'Tab') setOpen(false);
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
            event.preventDefault();
            const items = Array.from(root.current?.querySelectorAll('[role="menuitem"]') ?? []);
            const index = items.indexOf(document.activeElement as Element);
            setOpen(true);
            setTimeout(() => focusItem(event.key === 'Home' ? 0 : event.key === 'End' ? 2 : index < 0 ? (event.key === 'ArrowUp' ? 2 : 0) : index + (event.key === 'ArrowUp' ? -1 : 1)), 0);
        }
    }}><button ref={trigger} className="text-button" aria-haspopup="menu" aria-expanded={open} onClick={() => { setOpen(!open); if (!open) setTimeout(() => focusItem(0), 0); }}>Report <Chevron open={open}/></button>{open && <div role="menu" aria-label="Report">{[['Download report', download], ['Copy checksum', copy], ['Check a report', check]].map(([label, action]) => <button role="menuitem" tabIndex={-1} key={String(label)} onClick={() => { setOpen(false); trigger.current?.focus(); (action as () => void)(); }}>{String(label)}</button>)}</div>}</div>;
}
export function EvidenceVisual({ finding }: {
    finding: Finding;
}) {
    const e = finding.evidence;
    const pct = percent;
    if (e.missing_frac === null) return null;
    if (finding.check === 'population' && e.matching !== undefined)
        return <div className="visual"><div className="population-track"><span style={{ width: pct(Number(e.matching) / Number(e.rows)) }}/></div><p>{String(e.matching)} in population, {String(e.excluded)} left out</p><small>{Object.entries((e.excluded_values ?? {}) as Record<string, number>).map(([k, v]) => `${k} ${v}`).join(', ')}</small></div>;
    if (typeof e.missing_frac === 'number' && typeof e.max_missing_frac === 'number') {
        const end = Math.min(1, Math.max(2 * e.max_missing_frac, 1.25 * e.missing_frac, 0.1));
        const position = (value: unknown) => `${Math.min(100, Number(value) / end * 100)}%`;
        return <div className="visual"><div className="meter"><span style={{ width: position(e.missing_frac) }}/>{typeof e.warn_missing_frac === 'number' && <i title={`Warning ${pct(e.warn_missing_frac)}`} style={{ left: position(e.warn_missing_frac) }}/>}<b title={`Limit ${pct(e.max_missing_frac)}`} style={{ left: position(e.max_missing_frac) }}/></div><div className="meter-scale"><small>0%</small><small>{pct(end)}</small></div><small>{pct(e.missing_frac)} blank, limit {pct(e.max_missing_frac)}{typeof e.warn_missing_frac === 'number' ? `, warn above ${pct(e.warn_missing_frac)}` : ''}</small></div>;
    }
    if (finding.check === 'followup_horizon' && e.known !== undefined)
        return <div className="followup visual"><p><strong>{String(e.known)}</strong> of {Math.round(Number(e.known) / Number(e.known_frac))} outcomes known <small>Minimum {pct(e.min_known_frac)}</small></p><p><strong>{String(e.events)}</strong> deaths within {String(e.min_days)} days <small>Minimum {String(e.min_events ?? 0)}, warn below {String(e.warn_events ?? 0)}</small></p></div>;
    return null;
}
export function VerdictColumn({ question, result, busy, error, tuned, onTune, onFinding, onHide, onApproved, onDiscarded }: {
    question: Question;
    result?: Assessment;
    busy: boolean;
    error?: string;
    tuned: boolean;
    onTune: () => void;
    onFinding: (f: Finding) => void;
    onHide: () => void;
    onApproved: (q: Question) => void;
    onDiscarded: () => void;
}) {
    const [active, setActive] = useState<number>();
    const [passes, setPasses] = useState(false);
    const [expanded, setExpanded] = useState(false);
    const [notice, setNotice] = useState('');
    const [by, setBy] = useState('');
    const [working, setWorking] = useState(false);
    async function review(discard = false) {
        setWorking(true);
        try { if (discard) { await api.discard(question.name); onDiscarded(); } else onApproved(await api.approve(question.name, by)); }
        catch (error) { setNotice(errorMessage(error)); }
        finally { setWorking(false); }
    }
    const file = useRef<HTMLInputElement>(null);
    const findings = result?.findings ?? [];
    const counts = (s: string) => findings.filter(f => f.status === s).length;
    const title = question.id === 'q1-os-stage3-nsclc' ? '2-year survival, stage III lung' : question.id === 'q2-pdl1-io-response' ? 'PD-L1 and immunotherapy' : question.id === 'q4-stage-distribution' ? 'Stage-stratified analysis' : question.text;
    function download() { if (!result)
        return; const url = URL.createObjectURL(new Blob([result.report], { type: 'application/json' })); const a = document.createElement('a'); a.href = url; a.download = 'readyset-report.json'; a.click(); URL.revokeObjectURL(url); }
    async function verify(f?: File) { if (!f || !result)
        return; setNotice('Checking report…'); try {
        const v = await api.verify(await f.text(), result.cohort);
        setNotice(`${v.ok ? 'Checksum matches.' : 'Checksum does not match.'} ${v.message} ${v.data_ok === true ? 'Made from this data.' : v.data_ok === false ? 'Made from different data.' : ''} ${v.data_message ?? ''}`);
    }
    catch (e) {
        setNotice(errorMessage(e));
    } }
    return <article className={`verdict-column ${expanded ? 'expanded' : ''}`} aria-busy={busy}>
 <div className="question-heading"><div className="column-title"><h2 title={question.text}>{title}</h2>{question.definition.provenance?.status === 'proposed' && <span className="draft-marker">Unapproved draft</span>}</div><button className="icon" onClick={onHide} aria-label={`Hide ${title}`}>×</button></div>
 {question.definition.provenance?.status === 'proposed' && <div className="draft-review"><label>Approver’s name<input value={by} onChange={e => setBy(e.target.value)} autoComplete="name"/></label><div className="actions"><button disabled={!by.trim() || working} onClick={() => void review()}>Approve</button><button disabled={working} onClick={() => void review(true)}>Discard</button></div></div>}{notice && !result && <p role="status">{notice}</p>}{tuned && <span className="edited">Edited bar</span>}
 {error && <p role="alert" className="error">{error}</p>}
 {busy ? <div className="skeleton" role="status" aria-label="Assessing question"><i /><i /><i /></div> : result && <><div aria-live="polite" className={`verdict ${result.verdict.toLowerCase().replaceAll(' ', '-')}`} style={{ animationDelay: `${findings.length * 30}ms` }}>{result.verdict}</div><p className="verdict-summary">{counts('FAIL') ? `${counts('FAIL')} of ${findings.length} checks failed` : counts('WARN') ? `${counts('WARN')} ${counts('WARN') === 1 ? 'caveat' : 'caveats'}` : counts('UNKNOWN') ? `${counts('UNKNOWN')} ${counts('UNKNOWN') === 1 ? 'check needs' : 'checks need'} more evidence` : 'All checks passed'}</p>
 <div className="check-strip" aria-label={findings.map(f => `${names[f.check]}: ${f.status}`).join('; ')}>{findings.map((f, i) => <button key={i} className={`strip-cell ${f.status.toLowerCase()} ${active === i ? 'pointed' : ''}`} style={{ animationDelay: `${i * 30}ms` }} title={`${names[f.check]}: ${f.status}`} aria-label={`${names[f.check]}: ${f.status}`} onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(undefined)} onFocus={() => setActive(i)} onBlur={() => setActive(undefined)} onClick={() => { setPasses(true); setExpanded(true); setTimeout(() => document.getElementById(`${question.id}-${i}`)?.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }), 0); }}>{marks[f.status]}<span className="strip-label">{names[f.check] ?? f.check}</span></button>)}</div>
 <button className="mobile-expand text-button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? 'Hide findings' : 'Explore findings'}</button>
 <div className="column-body"><div className="column-tools"><button className="text-button" onClick={onTune}>View the bar</button><ReportMenu download={download} copy={() => { navigator.clipboard.writeText(result.sha256).then(() => setNotice('Checksum copied.')).catch(() => setNotice(`Checksum: ${result.sha256}`)); }} check={() => file.current?.click()}/><input hidden ref={file} type="file" accept=".json,application/json" onChange={e => { void verify(e.target.files?.[0]); e.target.value = ''; }}/></div>{notice && <p className="notice" role="status">{notice}</p>}
 <div className="findings">{findings.map((f, i) => ({ f, i })).sort((a, b) => ({ FAIL: 0, WARN: 1, UNKNOWN: 2, PASS: 3 }[a.f.status] - { FAIL: 0, WARN: 1, UNKNOWN: 2, PASS: 3 }[b.f.status])).filter(({ f }) => passes || f.status !== 'PASS').map(({ f, i }) => <section tabIndex={-1} id={`${question.id}-${i}`} className={`finding ${active === i ? 'pointed' : ''}`} key={i}><span className={`status-mark ${f.status.toLowerCase()}`} aria-label={f.status}>{marks[f.status]}</span><div><h3 title={f.check}>{names[f.check] ?? f.check}</h3><p>{findingMessage(f)}</p><EvidenceVisual finding={f}/>{citedIds(f).length > 0 && <button className="text-button" onClick={() => onFinding(f)}>Show {citedIds(f).length} {citedIds(f).length === 1 ? 'row' : 'rows'}</button>}{Object.entries(f.evidence).some(([k, v]) => k.endsWith('_truncated') && v === true) && <small>Partial citation list</small>}</div></section>)}</div>
 {counts('PASS') > 0 && <button className="passed-toggle" aria-expanded={passes} onClick={() => setPasses(!passes)}>✓ {counts('PASS')} {counts('PASS') === 1 ? 'check' : 'checks'} passed <span>{passes ? 'Hide' : 'Show'} <Chevron open={passes}/></span></button>}</div></>}
 </article>;
}
