// Shapes returned by the Silsila API (backend/src/silsila/api).

export type Lang = "en" | "ar";
export type Role = "family" | "counsellor";

/** A unit of person-facing text. Always rendered exactly as given. */
export interface Part {
  type: "template" | "source";
  id: string;
  text: string;
  params?: Record<string, unknown>;
  url?: string;
  attribution?: string;
  source_title?: string;
  sha256?: string;
  /** Present when a quoted English paragraph is shown in Arabic translation. */
  original_text?: string;
  translation?: { language: string; method?: string; reviewed_by_native_clinician?: boolean; sha256?: string };
}

export interface User {
  id: string;
  role: Role;
  display_name: string;
  lang: Lang;
}

export interface Health {
  ok: boolean;
  demo_mode: boolean;
  paragraphs: number;
  templates: number;
  loci: string[];
  audit: ChainStatus;
}

export interface ChainStatus {
  intact: boolean;
  events: number;
  first_broken_seq: number | null;
  head?: string;
}

export type Sex = "male" | "female";
export type PersonStatus = "unknown" | "unaffected" | "affected";

export interface TestRecord {
  detected: string[];
  recorded_at?: string;
  recorded_by?: string;
}

export interface PedPerson {
  id: string;
  sex: Sex;
  name?: string | null;
  /** Present on a case read in Arabic: the stored (English) name and the Arabic name. */
  name_en?: string | null;
  name_ar?: string | null;
  mother?: string | null;
  father?: string | null;
  status?: PersonStatus;
  affected_with?: string | null;
  test?: TestRecord | null;
  pregnant?: boolean;
  deceased?: boolean;
}

export interface Union {
  a: string;
  b: string;
}

export interface Pedigree {
  people: PedPerson[];
  unions: Union[];
}

export interface Consent {
  granted: boolean;
  granted_at?: string;
  withdrawn_at?: string | null;
  by?: string;
  wording_template?: string;
}

export interface Case {
  id: string;
  title?: string;
  locus_id: string;
  index_person_id: string;
  index_source: string;
  family_user_id: string;
  pedigree: Pedigree;
  consents?: Partial<Record<"compute" | "invite", Consent>>;
  created?: string;
  updated?: string;
}

export interface CaseSummary {
  id: string;
  title?: string;
  locus_id: string;
  index_source: string;
  people: number;
  invitations: number;
  open_invitations: number;
  updated: string;
}

export interface Allele {
  id: string;
  label: string;
  frequency: number;
  detection_rate: number;
  pathogenic?: boolean;
}

export interface Derivation {
  allele: string;
  measure: string;
  published_value: number;
  formula: string;
  inputs: Record<string, number>;
  allele_frequency: number;
}

export interface SourceCitation {
  allele?: string;
  citation?: string;
  pmid?: string;
  url?: string;
  population?: string;
  sample_size?: number;
  note?: string;
}

export interface LocusInfo {
  display: string;
  gene: string;
  background_f: number;
  alleles: Allele[];
  derivations: Derivation[];
  sources: SourceCitation[];
  detection_sources: SourceCitation[];
  content_ids: string[];
  limitations: string[];
}

export interface PersonReport {
  recorded: {
    status: PersonStatus;
    affected_with: string | null;
    test: TestRecord | null;
    pregnant: boolean;
    deceased: boolean;
  };
  computed: {
    p_carrier: number;
    p_affected: number;
    p_any_variant: number;
    chance_text: string;
    genotypes: Record<string, number>;
  };
  informative: boolean;
  sentence: Part[] | null;
  residual_note: Part[] | null;
}

export interface CoupleReport {
  female: string;
  male: string;
  kinship: number;
  computed: {
    p_both_carry: number;
    p_child_affected: number;
    child_affected_by_condition: Record<string, number>;
    baseline_child_affected: number;
  };
  sentence: Part[];
}

export type ReasonCode = "current_pregnancy" | "couple_child_risk" | "single_carrier_probability";

export interface InviteSuggestion {
  person_id: string;
  rank: number;
  p_carrier: number;
  partner_id: string | null;
  p_couple_both_carry: number | null;
  p_child_affected: number | null;
  pregnant_couple: boolean;
  reason_code: ReasonCode;
}

export interface Report {
  status: "ok" | "inconsistent" | "not_calculated" | "awaiting_consent";
  engine?: string;
  computed_at?: string;
  locus_id?: string;
  lang?: Lang;
  locus?: LocusInfo;
  people?: Record<string, PersonReport>;
  couples?: CoupleReport[];
  invites?: InviteSuggestion[];
  message?: Part[];
  reason?: string | null;
}

export type Channel = "self_share_letter" | "clinic_contact" | "anonymous_invite";

export type InvitationStatus =
  | "awaiting_counsellor"
  | "approved"
  | "sent"
  | "opened"
  | "understood"
  | "booked"
  | "tested"
  | "closed"
  | "withdrawn"
  | "declined_by_relative"
  | "no_response";

export interface HistoryEntry {
  status: InvitationStatus;
  at: string;
  by: string;
  [k: string]: unknown;
}

export interface Invitation {
  id: string;
  case_id: string;
  person_id: string;
  person_name: string;
  channel: Channel;
  disclose_condition: boolean;
  disclose_sender: boolean;
  sender_name: string | null;
  status: InvitationStatus;
  code?: string;
  history: HistoryEntry[];
  teachback: { at: string; score: number; total: number; passed: boolean } | null;
  closure_evidence: Record<string, unknown> | null;
  created?: string;
  updated?: string;
}

export interface CaseDetail {
  case: Case;
  report: Report;
  invitations: Invitation[];
  consent_text: Record<"compute" | "invite", Part[]>;
}

export interface TeachbackQuestion {
  id: string;
  en: string;
  ar: string;
  evidence: string;
  options: { id: string; en: string; ar: string }[];
}

export interface RelativeView {
  invitation_id: string;
  status: InvitationStatus;
  message: Part[];
  information: Part[];
  teachback: TeachbackQuestion[];
  consent_note: Part[];
  /** Common questions the relative can open; each answer is quoted source text. */
  topics: { id: string; title_en: string; title_ar: string }[];
}

export interface TopicAnswer {
  id: string;
  title_en: string;
  title_ar: string;
  parts: Part[];
}

export interface TeachbackResult {
  score: number;
  total: number;
  passed: boolean;
  items: Record<string, { answer: string | null; correct: boolean; evidence: string }>;
}

export interface MessageReply {
  reply: Part[];
  escalated: boolean;
  labels: string[];
}

export interface InboxMessage {
  id: string;
  case_id: string | null;
  sender: string;
  text: string;
  lang: Lang;
  labels: string[];
  rule_labels: string[];
  model_labels: string[];
  ngram_labels?: string[];
  model: string | null;
  topic: string | null;
  reply: Part[];
  escalate: boolean;
  resolved: boolean;
  resolved_by?: string;
  resolved_at?: string;
  created: string;
}

export interface QueueItem {
  type: "message" | "case" | "invitation";
  id: string;
  case_id: string | null;
  priority: number;
  reasons: string[];
  status?: InvitationStatus;
  since: string;
}

export interface AuditEvent {
  seq: number;
  ts: string;
  actor: string;
  role: string;
  action: string;
  case_id: string | null;
  entity: string | null;
  outcome: string;
  detail: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface AuditResponse {
  events: AuditEvent[];
  chain: ChainStatus;
}

export interface InjectResult {
  attempted: string;
  approved_original: string;
  blocked: boolean;
  reason: string | null;
}

export interface LociRegister {
  background_inbreeding: { value: number; meaning: string; source: SourceCitation };
  loci: {
    id: string;
    display: string;
    gene: string;
    alleles: Allele[];
    phenotypes: { genotype: string[]; label: string; affected: boolean; content_id?: string }[];
    derivations: Derivation[];
    sources: {
      id: string;
      label: string;
      published_measure?: string;
      published_value?: number;
      detection_rate?: number;
      detection_source?: SourceCitation | null;
      detection_note?: string;
      source?: SourceCitation;
    }[];
    limitations: string[];
  }[];
  excluded: { id: string; display: string; reason: string }[];
}
