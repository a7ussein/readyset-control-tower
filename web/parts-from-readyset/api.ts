export interface Provenance {
    [key: string]: unknown;
    status: string;
    sources: {
        [key: string]: unknown;
        rule: string;
        says: string;
        quote: string;
        source: string;
        url: string;
    }[];
    uncited: {
        rule: string;
        says: string;
        why: string;
    }[];
    understood_as?: {
        [key: string]: unknown;
        overruled?: string[];
        dropped_concepts?: string[];
    };
}
export type Verdict = 'Ready' | 'Conditional' | 'Insufficient Evidence' | 'Blocked';
export interface Definition {
    id: string;
    text: string;
    id_field?: string;
    provenance?: Provenance;
    required_fields?: string[];
    completeness?: Record<string, number | {
        max: number;
        warn?: number;
    }>;
    population?: {
        field: string;
        contains?: string[];
        values?: string[];
    };
    followup?: {
        start: string;
        last_seen: string;
        event_date: string;
        status_field: string;
        event_values: string[];
        min_days: number;
        min_known_frac?: number;
        min_events?: number;
        warn_events?: number;
    };
    completeness_when?: {
        field: string;
        when: {
            field: string;
            values: string[];
        };
        max?: number;
        warn?: number;
    }[];
    date_order?: [
        string,
        string
    ][];
    min_n?: number;
    duplicate_ids?: boolean;
    subgroup?: {
        field: string;
        values: string[];
        min_n: number;
    };
    value_sets?: Record<string, string[]>;
    distribution?: {
        field: string;
        values: string[];
        min_frac: number;
        max_frac: number;
    };
}
export interface Cohort {
    name: string;
    rows: number;
    columns: string[];
    source: string;
}
export interface Question {
    name: string;
    id: string;
    text: string;
    definition: Definition;
}
export interface Finding {
    check: string;
    status: 'PASS' | 'WARN' | 'FAIL' | 'UNKNOWN';
    message: string;
    evidence: Record<string, unknown>;
}
export interface Assessment {
    cohort: string;
    question: {
        id: string;
        text: string;
    };
    verdict: Verdict;
    because: string[];
    findings: Finding[];
    bar: Definition;
    report: string;
    sha256: string;
}
export interface Rows {
    cohort: string;
    total: number;
    offset: number;
    rows: Record<string, string>[];
}
export const demo = new URLSearchParams(location.search).get('demo') === '1';
// The built page talks to whichever server delivered it, so any port or host works. `npm run dev` uses the API on :8010.
const base = (import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8010' : '')).replace(/\/$/, '');
async function request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
        response = await fetch(`${base}/api${path}`, init);
    }
    catch {
        throw new Error(`Cannot reach ReadySet${base ? ` at ${base}` : ''}. Check that it is still running in the terminal.${demo ? '' : ' Offline preview: add ?demo=1 to the URL.'}`);
    }
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status}).`);
    }
    return response.json();
}
const post = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
async function snapshot() { return (await import('./fixtures')).fixtures; }
export const api = {
    cohorts: async (): Promise<Cohort[]> => demo ? (await snapshot()).cohorts : request('/cohorts'),
    questions: async (): Promise<Question[]> => demo ? (await snapshot()).questions : request('/questions'),
    assess: async (cohort: string, question: string, definition?: Definition): Promise<Assessment> => {
        if (demo) {
            if (definition && definition.provenance?.status !== 'proposed')
                throw new Error('Live tuning needs the API. This offline preview contains original, captured assessments only.');
            const results = (await snapshot()).results as unknown as Record<string, Assessment>;
            const result = results[`${cohort}|${question}`];
            if (!result)
                throw new Error('No captured assessment for this pair.');
            return structuredClone(result);
        }
        return request('/assess', post(definition ? { cohort, definition } : { cohort, question }));
    },
    rows: async (cohort: string, ids: string[], offset = 0, idField = 'patient_id'): Promise<Rows> => {
        if (demo) {
            const data = (await snapshot()).rows as unknown as Record<string, Record<string, string>[]>;
            if (!data[cohort])
                throw new Error('No captured rows for this cohort. Connect the API to inspect its evidence.');
            const selected = data[cohort].filter(row => ids.includes(row[idField])).sort((a, b) => ids.indexOf(a.patient_id) - ids.indexOf(b.patient_id));
            return { cohort, total: selected.length, offset, rows: selected.slice(offset, offset + 50) };
        }
        return request(`/cohorts/${encodeURIComponent(cohort)}/rows?${new URLSearchParams({ ids: ids.join(','), limit: '50', offset: String(offset), id_field: idField })}`);
    },
    upload: async (file: File): Promise<Cohort> => { if (demo)
        throw new Error('Uploading needs the API.'); const body = new FormData(); body.append('file', file); return request('/cohorts', { method: 'POST', body }); },
    proposals: async (): Promise<Question[]> => demo ? [(await import('../reference/proposal.json')).default as unknown as Question] : request('/proposals'),
    draftStatus: async (): Promise<{
        available: boolean;
        reason: string;
    }> => demo ? { available: false, reason: 'Drafting needs the local API and model. Captured proposals remain available below.' } : request('/draft/status'),
    draft: async (text: string, cohort: string): Promise<Question> => request('/draft', post({ text, cohort })),
    approve: async (name: string, by: string): Promise<Question> => { if (demo)
        throw new Error('Approval needs the live API.'); return request(`/proposals/${encodeURIComponent(name)}/approve`, post({ by })); },
    discard: async (name: string) => { if (demo)
        throw new Error('Discarding needs the live API.'); return request(`/proposals/${encodeURIComponent(name)}`, { method: 'DELETE' }); },
    verify: async (report: string, cohort: string): Promise<{
        ok: boolean;
        message: string;
        data_ok?: boolean;
        data_message?: string;
    }> => { if (demo)
        throw new Error('Report verification needs the API.'); return request('/verify', post({ report, cohort })); },
};
export function citedIds(finding: Finding): string[] {
    return [...new Set(['missing_rows', 'violating_rows', 'unparseable_rows', 'duplicate_ids', 'invalid_rows', 'matching_rows', 'blank_id_rows'].flatMap(key => {
            const value = finding.evidence[key];
            return Array.isArray(value) ? value.map(String) : [];
        }))];
}
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Try again.';
