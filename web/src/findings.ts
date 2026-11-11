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
    files?: { file: string; status: 'changed' | 'unchanged' | 'absent' | 'missing_in_one' | 'unreadable'; opened: boolean }[]
  }
}
