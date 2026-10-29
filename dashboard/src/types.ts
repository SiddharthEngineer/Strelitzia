// Mirrors the dashboard API responses (src/strelitzia/web/app.py, queries.py, tasks.py).

export type Status = 'active' | 'inactive' | 'in_progress' | 'submitted' | 'rejected' | 'heard_back';
export type StatusFilter = Status | 'no_response' | 'all';
export type UserStatus = 'in_progress' | 'submitted' | 'rejected' | 'heard_back';
export type StatusColor = 'grey' | 'orange' | 'yellow' | 'blue' | 'red' | 'green';
// status = live work first, closed last, then by fit score (the API's default).
export type SortKey = 'status' | 'discovered_at' | 'deadline' | 'fit_score' | 'next_interview';
export type Sort = SortKey | `-${SortKey}`;
export type WorkMode = 'remote' | 'hybrid' | 'onsite' | 'unknown';
export type Source = 'manual' | 'discovered';
export type IntakeStatus = 'queued' | 'scraping' | 'ok' | 'needs_paste' | 'error';

export interface JobListItem {
  key: string;
  title: string | null;
  company: string | null;
  role_category: string | null;
  location: string | null;
  work_mode: WorkMode | null;
  fit_score: number | null;
  discovered_at: string | null;
  deadline: string | null;
  status: Status;
  status_color: StatusColor;
  days_since_submitted: number | null;
  source: Source;
  added_at: string | null;
  intake_status: IntakeStatus | null;
  next_interview: string | null;
  fit_breakdown: FitComponent[];
  fit_flags: string[];
  flag_reasons: string[];
  assessment_stale: boolean;
}

export type Importance = 'dont_care' | 'nice' | 'important' | 'very_important' | 'dealbreaker';

// One scored criterion of the fit score (scoring/preferences.py Component). score is 0-1, null when not set.
export interface FitComponent {
  key: string;
  label: string;
  score: number | null;
  importance: Importance;
  dealbreaker_hit: boolean;
  note: string;
}

export interface Rating {
  score: number; // 1-5
  evidence: string;
}

// The Claude assessment (scoring/assessment.py), or {prefiltered: true} for a job the title prefilter skipped.
export interface FitAssessment {
  skills_match?: Rating;
  experience_match?: Rating;
  domain_interest?: Rating;
  red_flags?: { code: string; note: string }[];
  matched_keywords?: string[];
  summary?: string;
  prefiltered?: boolean;
}

export interface JobList {
  total: number;
  page: number;
  page_size: number;
  items: JobListItem[];
}

export interface JobQuery {
  status?: StatusFilter[];
  role?: string[];
  work_mode?: string[];
  location?: string;
  found_from?: string;
  found_to?: string;
  due_from?: string;
  due_to?: string;
  score_min?: number;
  score_max?: number;
  q?: string;
  hide_flagged?: boolean;
  sort?: Sort;
  page?: number;
  page_size?: number;
}

export interface FacetCount {
  value: string;
  count: number;
}

export interface Facets {
  total: number;
  status: (FacetCount & { value: Status | 'no_response'; color: StatusColor | null })[];
  role_category: FacetCount[];
  work_mode: FacetCount[];
  location: FacetCount[];
  flagged?: number;
}

export interface PostingLocation {
  city: string | null;
  state: string | null;
  country: string | null;
}

// The extract stage's JobPosting (enrichment/posting_model.py).
export interface JobDetails {
  company: string | null;
  title_normalized: string | null;
  role_category?: string;
  seniority: string;
  employment_type: string;
  work_mode: string;
  locations: PostingLocation[];
  remote_region: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  posted_date: string | null;
  application_deadline: string | null;
  start_date: string | null;
  summary: string;
  team: string | null;
  responsibilities: string[];
  required_qualifications: string[];
  preferred_qualifications: string[];
  skills_required: string[];
  skills_preferred: string[];
  education_level: string;
  education_fields: string[];
  years_experience_min: number | null;
  years_experience_max: number | null;
  visa_sponsorship: string;
  security_clearance: string;
  travel: string | null;
  benefits: string[];
  company_blurb: string | null;
}

export interface StatusEvent {
  from_status: string | null;
  to_status: string | null;
  at: string;
  source: string | null;
}

export interface JobLinks {
  posting: string;
  apply: string | null;
  drive_folder: string | null;
  resume: string | null;
  cover_letter: string | null;
  packet?: string | null;
  resume_draft?: string | null;
  cover_draft?: string | null;
  // Local draft files served by the API (left out once the PDF has moved to Drive).
  resume_pdf?: string;
  resume_docx?: string;
  cover_letter_pdf?: string;
}

export interface Coverage {
  covered: string[];
  missing: string[];
  pct_required: number | null; // null when the posting lists no required qualifications
  pct_preferred: number | null;
}

export interface DraftHistoryEntry {
  version: number;
  at: string;
  rules_version: string;
}

/** POST /jobs/{key}/packet: the packet and the resume draft Doc in the job's Drive folder, and the prompt. */
export interface PacketResult {
  prompt: string;
  doc_url: string;
  rules_version: string;
  resume_draft_url: string | null;
}

/** POST /jobs/{key}/cover-packet: the cover letter packet and draft Doc, and the prompt for a new chat. */
export interface CoverPacketResult {
  prompt: string;
  doc_url: string;
  rules_version: string;
  cover_draft_url: string | null;
}

/** The draft Doc a Check & format reads. */
export type DraftKind = 'resume' | 'cover';

/** POST /jobs/{key}/drafts/check on success */
export interface ImportResult {
  outcome: { draft_version: number; warnings: string[]; coverage: Coverage; unmet: string[]; fill_pct?: number | null };
  job: JobDetail;
}

export type DraftCheckOutcome =
  | ({ ok: true } & ImportResult)
  | { ok: false; errors: string[]; warnings: string[]; fix_prompt: string };

/** GET /claude/setup */
export interface ClaudeSetup {
  drive: boolean;
  drive_detail: string;
  /** "user": the user's own connected Drive; "legacy": the CLI's token file (owner, no TOKEN_KEY on the server). */
  drive_source: 'user' | 'legacy' | null;
  /** Where Connect Google Drive goes (a full-page redirect to Google), or null when the server can't offer it. */
  connect_url: string | null;
  /** The rules travel in each job's packet; this is only shown for reference. */
  rules_version: string;
  /** The user's Profile Docs, or null before setup. */
  profile_docs: ProfileDocs | null;
  project_name: string;
  /** What to paste into the project's instructions; its first line is "Instructions version: <v>". */
  project_instructions: string;
  instructions_version: string;
  /** Prompts for a new chat in the project (shown on the Profile page), versioned with the instructions. */
  interview_prompts: InterviewPrompts;
}

export interface InterviewPrompts {
  /** Claude interviews the user to fill the About me Doc. */
  about_me: string;
  /** Claude revises the Content Library one project at a time (Responsibility, Detail, outcomes). */
  library: string;
}

/** One Profile Doc in Drive (Strelitzia/Profile/) and when the app last pulled it. */
export interface ProfileDocLink {
  url: string | null;
  synced_at: string | null;
}

export interface ProfileDocs {
  library: ProfileDocLink | null;
  resume: ProfileDocLink | null;
  /** The About me Doc: the personal answers a cover letter needs (Sync creates it for users set up before it). */
  about: ProfileDocLink | null;
}

export interface JobDetail {
  key: string;
  url: string;
  title: string | null;
  company: string | null;
  site: string | null;
  location: string | null;
  work_mode: WorkMode | null;
  /** The posting's pay as written (the extracted range is in details). */
  salary: string | null;
  role_category: string | null;
  fit_score: number | null;
  score_reasoning: string | null;
  discovered_at: string | null;
  deadline: string | null;
  notes: string | null;
  /** The user's notes for the cover letter: why this company, referrals, what to stress (≤ 2000 characters). */
  cover_notes: string | null;
  description_text: string | null;
  details: JobDetails | null;
  status: Status;
  status_color: StatusColor;
  days_since_submitted: number | null;
  submitted_date: string | null;
  events: StatusEvent[];
  links: JobLinks;
  source: Source;
  added_at: string | null;
  intake_status: IntakeStatus | null;
  intake_error: string | null;
  contacts: JobContact[];
  interviews: Interview[];
  fit_breakdown: FitComponent[];
  fit_flags: string[];
  flag_reasons: string[];
  assessment_stale: boolean;
  /** The user edited the title or company after the last assessment. */
  score_stale: boolean;
  fit_assessment: FitAssessment | null;
  draft_version?: number | null;
  draft_rules_version?: string | null;
  submitted_draft_version?: number | null;
  submitted_rules_version?: string | null;
  coverage?: Coverage | null;
  unmet?: string[];
  warnings?: string[];
  fill_pct?: number | null;
  notes_for_user?: string;
  draft_history?: DraftHistoryEntry[];
  packet_doc_url?: string | null;
  resume_draft_url?: string | null;
  cover_draft_url?: string | null;
  /** When the cover letter last passed its own Check & format, and that check's warnings. */
  cover_letter_at?: string | null;
  cover_warnings?: string[];
}

export interface Criterion<V = unknown> {
  importance: Importance;
  value: V;
}

// The Preferences page's document (scoring/preferences.py Preferences).
export interface Preferences {
  salary: Criterion<{ min: number | null; currency: string; period: string }>;
  locations: Criterion<{ places: string[]; remote_ok: boolean }>;
  work_mode: Criterion<string[]>;
  role_category: Criterion<string[]>;
  seniority: Criterion<string[]>;
  employment_type: Criterion<string[]>;
  visa: Criterion<boolean>;
  clearance: Criterion<boolean>;
  travel: Criterion<number | null>;
  red_flags_counted: string[];
  skills_want: string[];
  skills_avoid: string[];
  industries_favor: string[];
  industries_avoid: string[];
  target_roles: string[];
}

export interface RedFlagOption {
  value: string;
  label: string;
  help: string;
}

export interface PreferencesResponse {
  prefs: Preferences;
  // Value lists by key; red_flags lists the pickable flags with a label and a one-line explanation;
  // roles_by_field maps each job field (role_category) to common role titles for target_roles.
  options: Record<string, string[] | RedFlagOption[] | Record<string, string[]>>;
  labels: Record<string, string>;
}

export interface ReassessPreview {
  reassess_needed: boolean;
  jobs_to_reassess: number;
  estimated_usd: number;
  /** Only with reassess_scope "active": jobs left out because they aren't extracted yet. */
  skipped_unextracted?: number;
}

/** "stale": only the jobs whose assessment is out of date. "active": every job that isn't rejected. */
export type ReassessScope = 'stale' | 'active';

/** GET /rescore/preview: what Rescore all would re-assess (active jobs) and roughly cost. */
export interface RescorePreview {
  jobs: number;
  skipped_unextracted: number;
  estimated_usd: number;
}

/** POST /rescore */
export interface RescoreAllResult extends RescorePreview {
  task: Task | null;
}

export interface SavePreferencesResult {
  prefs: Preferences;
  rescored: number;
  task: Task | null;
}

export type TaskKind = 'rescore' | 'reassess_all' | 'rescore_all' | 'intake';
export type TaskState = 'queued' | 'running' | 'done' | 'error';

export interface Task {
  id: string;
  url: string | null;
  kind: TaskKind;
  state: TaskState;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  key: string | null;
}

export type Relation = 'recruiter' | 'hiring_manager' | 'referral' | 'interviewer' | 'other';

// A contact (workspace.py), shared across jobs.
export interface Contact {
  id: string;
  name: string;
  company: string | null;
  role: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export type ContactFields = Partial<Omit<Contact, 'id' | 'created_at' | 'updated_at'>>;

export interface JobContact extends Contact {
  relation: Relation;
}

export interface ContactListItem extends Contact {
  job_count: number;
}

export interface ContactJob {
  key: string;
  title: string | null;
  company: string | null;
  relation: Relation;
}

export interface ContactWithJobs extends Contact {
  jobs: ContactJob[];
}

export type Outcome = 'pending' | 'passed' | 'rejected' | 'withdrew';

export interface Interview {
  id: string;
  job_url: string;
  scheduled_at: string | null; // ISO UTC
  stage: string | null;
  format: string | null;
  interviewers: string | null;
  prep_notes: string | null;
  debrief_notes: string | null;
  outcome: Outcome | null;
  created_at: string;
  updated_at: string;
}

export type InterviewFields = Partial<Pick<Interview,
  'scheduled_at' | 'stage' | 'format' | 'interviewers' | 'prep_notes' | 'debrief_notes' | 'outcome'>>;

export interface AddJobInput {
  url?: string;
  title?: string;
  company?: string;
  location?: string;
  description?: string;
}

export interface AddJobResult {
  key: string;
  created: boolean;
  task: Task | null;
}

/** The signed-in account (GET /auth/me). While login is off every request acts as the owner. */
export interface AuthUser {
  email: string;
  name: string | null;
  role: 'owner' | 'user';
}

export interface AuthMe {
  /** Sign-in is on: built-in Google sign-in, or the site's sign-in through the reverse proxy. */
  enabled: boolean;
  user: AuthUser | null;
  /** How sign-in works (missing from an older server). */
  mode?: 'off' | 'google' | 'proxy';
  /** Proxy mode: who the site signed in, even when that account can't use the dashboard. */
  identity?: { email: string; name: string | null } | null;
  /** Why `identity` has no account here. */
  reason?: 'not_invited' | 'disabled' | null;
  /** Proxy mode: the site's sign-out endpoint (POST), used instead of the dashboard's own. */
  logout_url?: string | null;
  /** engineerfamily's shared header script (`<ef-home>`, `<ef-profile>`), when the dashboard should use it. */
  site_header_url?: string | null;
  /** Proxy mode with engineerfamily's grant: the visitor is a site admin. */
  site_admin?: boolean;
  /** engineerfamily's Users page (where access and caps are set), when the site grants access. */
  users_url?: string | null;
}

/** The fields the Profile page edits (GET/PUT /profile). */
export interface ProfileFields {
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  linkedin_url: string;
  github_url: string;
  location: string;
  current_job_title: string;
  years_experience: number | null;
  education_level: string | null;
  skills: string[];
}

export interface ProfileResponse {
  profile: ProfileFields;
  /** Scoring has a resume text to read (uploaded, or imported from resume.txt). */
  has_resume: boolean;
  resume_file_name: string | null;
  content_library_md: string;
  /** Why the workbench can't use the content library, or null. */
  content_library_error: string | null;
  /** The Profile Docs (the content library and base resume live there), or null before setup. */
  profile_docs: ProfileDocs | null;
  options: { education_level: string[] };
}

/** PUT /profile: the fields (the content library and resume are edited in the Profile Docs). */
export type ProfileSave = ProfileFields;

/** POST /profile/docs/sync: the pull's outcome (problems mean nothing was saved) and the profile. */
export interface ProfileSyncResult extends ProfileResponse {
  ok: boolean;
  problems: string[];
  /** About me trouble (e.g. no answers yet): shown, but the rest was saved. */
  warnings: string[];
  changed: boolean;
  /** Values from the Base Resume for fields that are still empty (not saved: the user reviews, then saves). */
  draft: Partial<ProfileFields>;
  /** Why the resume couldn't be read for the draft (the sync itself still worked), or null. */
  parse_error: string | null;
}

/** POST /profile/docs/setup: done, or the names of the Docs it would overwrite. */
export type ProfileDocsSetupOutcome = { ok: true; profile: ProfileResponse } | { ok: false; existing: string[] };

/** PATCH /jobs/{key}: only the fields present change; null clears an optional one. */
export interface JobPatch {
  submitted_at?: string;
  notes?: string | null;
  title?: string;
  company?: string;
  location?: string | null;
  work_mode?: WorkMode | null;
  salary?: string | null;
  deadline?: string | null;
}

/** DELETE /jobs/{key}: the job's Drive folder is left alone. */
export interface DeleteJobResult {
  ok: boolean;
  drive_folder: string | null;
  message: string;
}

/** Recruiter review graders: a chat app and model the user pasted the prompt into. */
export type ReviewGrader = 'claude-haiku' | 'claude-sonnet' | 'claude-opus' | 'chatgpt' | 'gemini' | 'other';
export type ReviewVerdict = 'yes' | 'maybe' | 'no';

export interface ReviewGradeSummary {
  grader: ReviewGrader;
  /** The exact model the user named ("GPT-5 Thinking"), or "". */
  model_label: string;
  overall_resume: string;
  overall_cover: string | null;
  verdict: ReviewVerdict;
  created_at: string;
}

/** GET /reviews and /jobs/{key}/reviews: one review with every grader's overall grades. */
export interface ReviewSummary {
  id: string;
  job_url: string;
  draft_id: string;
  draft_version: number | null;
  prompt_version: string;
  created_at: string;
  job: { key: string | null; title: string | null; company: string } | null;
  grades: ReviewGradeSummary[];
}

export interface ReviewCriterionGrade {
  grade: string;
  evidence: string;
  fix: string;
}

export interface ReviewDocGrades {
  criteria: Record<string, ReviewCriterionGrade>;
  overall: string;
}

/** A grader's whole reply, as imported. */
export interface ReviewReplyData {
  review: number;
  prompt_version?: string;
  resume: ReviewDocGrades;
  cover_letter: ReviewDocGrades | null;
  verdict: ReviewVerdict;
  top_fixes: string[];
}

export interface ReviewCriterion {
  key: string;
  name: string;
}

/** GET /reviews/{id}: the review with its prompt and every grader's reply. */
export interface ReviewDetail extends ReviewSummary {
  current_prompt_version: string;
  criteria: ReviewCriterion[];
  prompt: string;
  replies: (ReviewGradeSummary & { reply: ReviewReplyData })[];
}

export type ReviewImportOutcome =
  | { ok: true; warnings: string[]; review: ReviewDetail }
  | { ok: false; errors: string[] };

export type GraderTendency = 'harsh' | 'lenient' | 'narrow' | 'balanced';

/** One grader in GET /reviews/graders. Means are grade points (A+ = 14 ... F- = 0). */
export interface GraderStats {
  grader: ReviewGrader;
  model_labels: string[];
  reviews: number;
  mean: Record<string, number | null>;
  mean_overall: { resume: number | null; cover_letter: number | null };
  /** How often its verdict matched another grader's on the same review (0-1). */
  verdict_agreement: number | null;
  /** Mean points above (+) or below (-) the other graders on the same criterion. */
  bias: number | null;
  /** Standard deviation of its criterion grades, in points. */
  spread: number | null;
  tendency: GraderTendency | null;
}

/** GET /reviews/graders: from the reviews that 2+ graders replied to. */
export interface GraderComparison {
  reviews: number;
  criteria: ReviewCriterion[];
  graders: GraderStats[];
}
