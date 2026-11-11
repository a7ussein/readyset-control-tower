import { useEffect, useRef, useState } from 'react';
import { names, findingMessage } from './VerdictColumn';
import { Panel } from './Panel';
import { api, citedIds, errorMessage } from './api';
import type { Finding, Rows } from './api';
export function EvidencePanel({ cohort, finding, idField = 'patient_id', onClose }: {
    cohort: string;
    finding: Finding;
    idField?: string;
    onClose: () => void;
}) {
    const [data, setData] = useState<Rows>();
    const [error, setError] = useState('');
    const [offset, setOffset] = useState(0);
    const close = useRef<HTMLButtonElement>(null);
    useEffect(() => { close.current?.focus(); }, []);
    useEffect(() => { let active = true; api.rows(cohort, citedIds(finding), offset, idField).then(result => { if (active)
        setData(result); }).catch(e => { if (active)
        setError(errorMessage(e)); }); return () => { active = false; }; }, [cohort, finding, offset, idField]);
    function summary() {
        const e = finding.evidence;
        const count = (key: string) => Array.isArray(e[key]) ? e[key].length : 0;
        const patients = (n: number) => `${n} ${n === 1 ? 'patient has' : 'patients have'}`;
        switch (finding.check) {
            case 'date_order': return `${patients(count('violating_rows'))} a ${e.earlier_field} after their ${e.later_field}.${count('unparseable_rows') ? ` ${patients(count('unparseable_rows'))} a date that cannot be read.` : ''}`;
            case 'duplicate_ids': {
                const ids = (e.duplicate_ids ?? []) as string[];
                if (ids.length === 1 && data && data.total <= 50) return `${ids[0]} appears ${data.rows.filter(row => row[idField] === ids[0]).length} times.`;
                return `${ids.length} patient ${ids.length === 1 ? 'id appears' : 'ids appear'} more than once.`;
            }
            case 'completeness': return `${patients(count('missing_rows'))} no ${e.field}.`;
            case 'conditional_completeness': return `${patients(count('missing_rows'))} no ${e.field} where ${e.when_field} is ${(e.when_values as string[] ?? []).join(' or ')}.`;
            case 'value_set': return `${patients(Number(e.invalid_rows_total ?? count('invalid_rows')))} a ${e.field} outside the allowed values.`;
            case 'followup_horizon': return `${patients(count('violating_rows'))} follow-up that does not reach ${e.min_days} days.`;
            case 'subgroup_n': return `${patients(Number(e.distinct_in_subgroup))} ${e.field} in ${(e.values as string[] ?? []).join(', ')}.`;
            default: return findingMessage(finding);
        }
    }
    const fields = finding.check === 'duplicate_ids' ? [idField] : [finding.evidence.field, finding.evidence.when_field, finding.evidence.earlier_field, finding.evidence.later_field].filter((x): x is string => typeof x === 'string');
    const columns = data ? [idField, ...new Set(data.rows.flatMap(Object.keys).filter(k => k !== idField))] : [];
    return <Panel label="Cited rows" onClose={onClose}><section className="evidence-panel" aria-label="Cited rows">
    <div className="panel-heading"><div><span className="eyebrow">Evidence · {names[finding.check] ?? finding.check}</span><h2>Rows behind the finding</h2></div><button ref={close} className="icon close-button" aria-label="Close" onClick={onClose}><svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.8"/></svg></button></div>
    <p>{summary()}</p><p className="muted"><code>{cohort}</code>, Highlighted cells are the fields checked. Duplicate records stay separate.</p>
    {error && <p role="alert" className="error">{error}</p>}
    {!data && !error && <p role="status">Loading cited rows…</p>}
    {data && <><p role="status">{data.total} {data.total === 1 ? 'row' : 'rows'}, showing {data.rows.length ? offset + 1 : 0}–{offset + data.rows.length}</p><div className="table-scroll" tabIndex={0} aria-label="Scrollable cited rows"><table><thead><tr>{columns.map(column => <th scope="col" className={fields.includes(column) ? 'evidence-field' : ''} key={column}>{column}</th>)}</tr></thead><tbody>{data.rows.map((row, i) => <tr key={i}>{columns.map(column => <td key={column} className={fields.includes(column) ? ((finding.check === 'completeness' || finding.check === 'conditional_completeness') && row[column] ? 'evidence-field' : 'offending') : ''}>{row[column] || <span className="muted">(blank)</span>}</td>)}</tr>)}</tbody></table></div>
    {!data.rows.length && <p>No records returned for these ids.</p>}{data.total > 50 && <div className="actions"><button disabled={offset === 0} onClick={() => { setData(undefined); setError(''); setOffset(Math.max(0, offset - 50)); }}>Previous rows</button><button disabled={offset + 50 >= data.total} onClick={() => { setData(undefined); setError(''); setOffset(offset + 50); }}>Next rows</button></div>}</>}
  </section></Panel>;
}
