// The shape of findings.json (shared format v0.2 plus our x_readyset additions).
// The rules for every field are in docs/OUTPUT-CONTRACT.md. The screen reads this file and computes nothing itself.
export type Verdict = 'Ready' | 'Conditional' | 'Blocked' | 'Insufficient Evidence';
export type FindingKind = 'sample_swap' | 'duplicate' | 'membership_change' | 'label_conflict' | 'missing_data' | 'other';
export interface Pointer { kind: 'sample' | 'patient' | 'gene' | 'protein' | 'slide' | 'file' | 'release' | 'analysis' | 'claim' | 'row'; id: string; release?: string; file?: string; url?: string; note?: string }
export interface Finding {
  id: string; kind: FindingKind; summary: string
  severity: 'high' | 'medium' | 'low' | 'none'; confidence: 'high' | 'medium' | 'low'
  evidence: Pointer[]; affects_analyses: string[]; not_affected_analyses: string[]
  limitation: string; needs_human_review: boolean
}
export interface Analysis { id: string; status: 'changed' | 'unchanged' | 'not_rerun'; before?: Record<string, unknown>; after?: Record<string, unknown>; note?: string }
export interface Repair { id: string; action: 'exclude' | 'relabel' | 'restore_from_previous_release' | 'flag_for_review' | 'other'; targets: Pointer[]; justification: string; addresses: string[] }
export interface ReleaseFile { file: string; sha256: string; hash_of?: 'file' | 'content' }
export interface FileInfo { file: string; status: 'changed' | 'unchanged' | 'absent' | 'missing_in_one' | 'not_in_both' | 'unreadable'; opened: boolean; note?: string }
// One named row of a large file, with each sample's value in both releases, so a reader can check a finding by hand.
export interface Witness { file: string; row: string; releases: string[]; values: { sample: string; before: string | null; after: string | null }[] }
// A person's review of one finding, recorded by the server beside the findings.
export interface Review { finding: string; key: string; status: 'confirmed' | 'dismissed'; fix?: 'approved' | ''; reviewer?: string; role?: string; note?: string; at?: string }
export interface Findings {
  format_version: '0.2'
  producer: { team: string; product: string; track: string }
  data: { dataset?: string; releases: { name: string; files: ReleaseFile[] }[] }
  question: string
  verdict?: Verdict
  findings: Finding[]
  analyses?: Analysis[]
  repairs?: Repair[]
  x_readyset?: {
    example_notice?: string; engine_version?: string; generated_at?: string; run_seconds?: number
    analyses_registered?: string[]; scope?: string
    files?: FileInfo[]
    witness?: Record<string, Witness>
    analysis_titles?: Record<string, string>
    analyses_in_question?: string[]; analysis_reads?: Record<string, string>; unrelated_findings?: number
    notes?: string[]
    effects?: Record<string, Record<string, { before?: Record<string, unknown>; after?: Record<string, unknown>; size?: 'none' | 'small' | 'large'; measure?: string | null; moved_by?: number }>>
    repair_priority?: Record<string, { level?: string; why?: string }>
    rules?: Record<string, { detected_by?: string; impact?: string[]; severity?: string }>
    live?: { available: { id: string; title: string }[] }
    review_keys?: Record<string, string>
    reviews?: Review[]
  }
}
