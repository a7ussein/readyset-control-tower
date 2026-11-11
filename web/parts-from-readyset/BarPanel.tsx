import { useState } from 'react';
import type { Assessment, Definition, Question } from './api';
import { api, demo, errorMessage } from './api';
import { EvidenceVisual, findingMessage } from './VerdictColumn';
interface Props {
    question: Question;
    value: Definition;
    result?: Assessment;
    error?: string;
    onChange: (v: Definition) => void;
    onReset: () => void;
    onClose: () => void;
    onApproved: (q: Question) => void;
    onDiscarded: () => void;
}
export function BarPanel({ question, value, result, error, onChange, onReset, onClose, onApproved, onDiscarded }: Props) {
    const [by, setBy] = useState(''), [message, setMessage] = useState(''), [working, setWorking] = useState(false);
    function number(label: string, current: number, change: (v: number) => void, fraction = false) { return <label className="number-control">{label}<input aria-label={label} type="number" min="0" max={fraction ? 100 : undefined} step={fraction ? 1 : 1} value={fraction ? Math.round(current * 10000) / 100 : current} onChange={e => { if (e.target.value !== '')
        change(Number(e.target.value) / (fraction ? 100 : 1)); }}/>{fraction ? '%' : ''}</label>; }
    function actual(check: string, field?: string) { const f = result?.findings.find(f => f.check === check && (!field || f.evidence.field === field)); return f ? <div className="actual"><p>{findingMessage(f)}</p><EvidenceVisual finding={f}/></div> : null; }
    async function act(discard = false) { setWorking(true); setMessage(''); try {
        if (discard) {
            await api.discard(question.name);
            onDiscarded();
        }
        else
            onApproved(await api.approve(question.name, by));
    }
    catch (e) {
        setMessage(errorMessage(e));
    }
    finally {
        setWorking(false);
    } }
    return <aside className="bar-panel"><div className="panel-heading"><h2>The bar</h2><button className="icon close-button" aria-label="Close" onClick={onClose}><svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.8"/></svg></button></div><p>{question.text}</p>{value.provenance?.status === 'proposed' && <p className="draft-marker">Unapproved draft</p>}<p className="muted">Change a number and the verdict updates.</p>{demo && <p className="notice">Captured preview. Connect the API to edit thresholds.</p>}{error && <p role="alert" className="error">{error}</p>}
 <section className="control-group"><h3>Columns the question needs</h3><p>{value.required_fields?.join(', ') ?? 'No required columns'}</p></section>{value.population && <section className="control-group"><h3>Patients this question is about</h3><p>{value.population.field} {value.population.contains ? 'contains' : 'is'} {(value.population.contains ?? value.population.values)?.join(', ')}</p>{actual('population')}</section>}
 <fieldset disabled={demo}>
 {Object.entries(value.completeness ?? {}).map(([field, t]) => <section className="control-group" key={field}>{number(`${field} may be blank for at most`, typeof t === 'number' ? t : t.max, max => onChange({ ...value, completeness: { ...value.completeness, [field]: typeof t === 'number' ? max : { ...t, max } } }), true)}{typeof t !== 'number' && t.warn !== undefined && number('Warn above', t.warn, warn => onChange({ ...value, completeness: { ...value.completeness, [field]: { ...t, warn } } }), true)}{actual('completeness', field)}</section>)}
 {value.completeness_when?.map((r, i) => <section className="control-group" key={i}><p>{r.field} is owed where {r.when.field} is {r.when.values.join(', ')}.</p>{number('May be blank for at most', r.max ?? 0, max => onChange({ ...value, completeness_when: value.completeness_when!.map((v, j) => i === j ? { ...v, max } : v) }), true)}{number('Warn above', r.warn ?? r.max ?? 0, warn => onChange({ ...value, completeness_when: value.completeness_when!.map((v, j) => i === j ? { ...v, warn } : v) }), true)}{actual('conditional_completeness', r.field)}</section>)}
 {value.min_n !== undefined && <section className="control-group">{number('At least this many distinct patients', value.min_n, min_n => onChange({ ...value, min_n }))}{actual('min_n')}</section>}
 {value.followup && <section className="control-group"><h3>Follow-up</h3>{(['min_days', 'min_events', 'warn_events', 'min_known_frac'] as const).map(k => number(({ min_days: 'Outcome time point in days', min_events: 'At least this many deaths', warn_events: 'Warn below this many deaths', min_known_frac: 'Outcome known for at least' })[k], value.followup![k] ?? 0, n => onChange({ ...value, followup: { ...value.followup!, [k]: n } }), k === 'min_known_frac'))}{actual('followup_horizon')}</section>}
 {value.subgroup && <section className="control-group"><p>Patients with {value.subgroup.field} in {value.subgroup.values.join(', ')}.</p>{number('At least this many in the subgroup', value.subgroup.min_n, min_n => onChange({ ...value, subgroup: { ...value.subgroup!, min_n } }))}{actual('subgroup_n')}</section>}
 {value.distribution && <section className="control-group"><p>Share with {value.distribution.field} in {value.distribution.values.join(', ')}.</p>{(['min_frac', 'max_frac'] as const).map(k => number(k === 'min_frac' ? 'Minimum share' : 'Maximum share', value.distribution![k], n => onChange({ ...value, distribution: { ...value.distribution!, [k]: n } }), true))}{actual('distribution')}</section>}
 {value.duplicate_ids !== undefined && <section className="control-group"><label><input type="checkbox" checked={value.duplicate_ids} onChange={e => onChange({ ...value, duplicate_ids: e.target.checked })}/> Check that no patient appears twice</label>{actual('duplicate_ids')}</section>}
 <button onClick={onReset}>Reset bar</button></fieldset>
 {value.provenance && <section className="sources"><h2>Sources</h2>{value.provenance.sources.map((s, i) => <section key={i}><h3>{s.rule}</h3><p>{s.says}</p><blockquote>{s.quote}</blockquote><a href={s.url} target="_blank" rel="noreferrer">{s.source}</a></section>)}<section className="uncited"><h2>No source found</h2>{value.provenance.uncited.map((s, i) => <div key={i}><h3>{s.rule}</h3><p>{s.says}. {s.why}</p></div>)}</section>{[...(value.provenance.understood_as?.overruled ?? []), ...(value.provenance.understood_as?.dropped_concepts ?? [])].length > 0 && <section><h3>Removed from the model’s interpretation</h3>{[...(value.provenance.understood_as?.overruled ?? []), ...(value.provenance.understood_as?.dropped_concepts ?? [])].map((s, i) => <p key={i}>{s}</p>)}</section>}</section>}
 {value.provenance?.status === 'proposed' && <section className="approval"><h2>Review this draft</h2><label>Approver’s name<input value={by} onChange={e => setBy(e.target.value)} autoComplete="name"/></label><div className="actions"><button className="primary" disabled={!by.trim() || working} onClick={() => void act()}>Approve</button><button disabled={working} onClick={() => void act(true)}>Discard</button></div></section>}{message && <p role="alert" className="error">{message}</p>}
 <details><summary>Full question definition</summary><pre>{JSON.stringify(value, null, 2)}</pre></details></aside>;
}
