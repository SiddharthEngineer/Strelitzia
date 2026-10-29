// Typed fetch helpers for the dashboard API (<base>/api, e.g. /strelitzia/dashboard/api). Mutating calls send `X-Strelitzia: 1` (the server's CSRF check).
import type {
  AddJobInput, AddJobResult, AuthMe, ClaudeSetup, Contact, CoverPacketResult, DeleteJobResult, DraftCheckOutcome, DraftKind, ContactFields, ContactListItem, ContactWithJobs,
  Facets, Interview, ImportResult, InterviewFields, JobDetail, JobList, JobPatch, JobQuery, PacketResult, PanelGradeOutcome,
  PanelMode, PanelOverview, PanelRun, PanelWinner, Preferences, PreferencesResponse, ProfileDocsSetupOutcome,
  ProfileResponse, ProfileSave, ProfileSyncResult, ReassessPreview, ReassessScope, Relation, RescoreAllResult,
  RescorePreview, ReviewDetail, ReviewGrader, ReviewImportOutcome, ReviewSummary, SavePreferencesResult, Task,
  UserStatus,
} from './types';

export const API_BASE = `${import.meta.env.BASE_URL}api`;

export class ApiError extends Error {
  constructor(public status: number, message: string, public body: unknown = null) {
    super(message);
    this.name = 'ApiError';
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === 'string') return detail;
    if (typeof detail?.message === 'string') return detail.message; // e.g. the 402 budget stop
    if (Array.isArray(detail)) { // pydantic validation errors; drop its "Value error, " prefix
      return detail.map((d) => (d?.msg ? String(d.msg).replace(/^Value error, /, '') : String(d))).join('; ');
    }
  } catch {
    // not JSON
  }
  return `${res.status} ${res.statusText}`.trim();
}

type UnauthorizedListener = () => void;
let unauthorized: UnauthorizedListener | null = null;

/** Call `listener` whenever a request comes back 401 (the session ended): the app shows the sign-in screen. */
export function onUnauthorized(listener: UnauthorizedListener | null): void {
  unauthorized = listener;
}

async function failure(res: Response): Promise<ApiError> {
  if (res.status === 401) unauthorized?.();
  const body = await res.clone().json().catch(() => null);
  return new ApiError(res.status, await errorMessage(res), body);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? 'GET';
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (method !== 'GET') {
    headers['X-Strelitzia'] = '1';
    if (init?.body !== undefined) headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(API_BASE + path, { ...init, headers });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

/** The query string for a jobs request (list params repeat: status=a&status=b). Empty values are left out. */
export function jobsQueryString(query: JobQuery): string {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(name, String(v)));
    else params.set(name, String(value));
  }
  return params.toString();
}

export function listJobs(query: JobQuery = {}, signal?: AbortSignal): Promise<JobList> {
  const qs = jobsQueryString(query);
  return request<JobList>(`/jobs${qs ? `?${qs}` : ''}`, { signal });
}

export function getFacets(signal?: AbortSignal): Promise<Facets> {
  return request<Facets>('/facets', { signal });
}

export function getJob(key: string, signal?: AbortSignal): Promise<JobDetail> {
  return request<JobDetail>(`/jobs/${encodeURIComponent(key)}`, { signal });
}

/** Set (or with null, reset) the user's status. submittedAt is YYYY-MM-DD; the server defaults it to today. */
export function setStatus(key: string, status: UserStatus | null, submittedAt?: string): Promise<JobDetail> {
  const body: Record<string, string | null> = { status };
  if (submittedAt) body.submitted_at = submittedAt;
  return request<JobDetail>(`/jobs/${encodeURIComponent(key)}/status`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** Save the user's notes for the job's cover letter (null or blank clears them). */
export function putCoverNotes(key: string, notes: string | null): Promise<JobDetail> {
  return request<JobDetail>(`${job(key)}/cover-notes`, { method: 'PUT', body: JSON.stringify({ notes }) });
}

export function patchJob(key: string, patch: JobPatch): Promise<JobDetail> {
  return request<JobDetail>(`/jobs/${encodeURIComponent(key)}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

/** Delete the job with its drafts, interviews, notes and history (no undo). Drive files stay. */
export function deleteJob(key: string): Promise<DeleteJobResult> {
  return request<DeleteJobResult>(job(key), { method: 'DELETE' });
}

/** Write the job's Claude packet and resume draft Doc to Drive and get the prompt to paste in Claude (409 without
 * Drive). */
export function openPacket(key: string): Promise<PacketResult> {
  return request<PacketResult>(`/jobs/${encodeURIComponent(key)}/packet`, { method: 'POST' });
}

/** Write the job's cover letter packet and draft Doc to Drive and get the prompt for a new chat (409 until a resume
 * draft is accepted, or without Drive). */
export function openCoverPacket(key: string): Promise<CoverPacketResult> {
  return request<CoverPacketResult>(`/jobs/${encodeURIComponent(key)}/cover-packet`, { method: 'POST' });
}

/** Check & format one of the job's draft Docs: ok with the saved draft, or not ok with the errors and a fix prompt. */
export async function checkDrafts(key: string, kind: DraftKind = 'resume'): Promise<DraftCheckOutcome> {
  const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(key)}/drafts/check?kind=${kind}`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'X-Strelitzia': '1' },
  });
  if (res.status === 422) {
    const body = await res.clone().json().catch(() => null);
    if (body && Array.isArray(body.errors)) {
      return { ok: false, errors: body.errors, warnings: body.warnings ?? [], fix_prompt: body.fix_prompt ?? '' };
    }
  }
  if (!res.ok) throw await failure(res);
  return { ok: true, ...((await res.json()) as ImportResult) };
}

export function getClaudeSetup(signal?: AbortSignal): Promise<ClaudeSetup> {
  return request<ClaudeSetup>('/claude/setup', { signal });
}

/** Create the Profile Docs in Drive. Without `overwrite`, existing Docs come back as `existing` (nothing changed). */
export async function setupProfileDocs(overwrite: boolean): Promise<ProfileDocsSetupOutcome> {
  try {
    const profile = await request<ProfileResponse>('/profile/docs/setup', {
      method: 'POST', body: JSON.stringify({ overwrite }),
    });
    return { ok: true, profile };
  } catch (err) {
    const existing = err instanceof ApiError && err.status === 409
      ? (err.body as { existing?: unknown } | null)?.existing : undefined;
    if (Array.isArray(existing)) return { ok: false, existing: existing.map(String) };
    throw err;
  }
}

/** Pull the Profile Docs now. */
export function syncProfileDocs(): Promise<ProfileSyncResult> {
  return request<ProfileSyncResult>('/profile/docs/sync', { method: 'POST' });
}

/** Forget the user's Google Drive token (their files stay in their Drive). */
export function disconnectDrive(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('/drive/disconnect', { method: 'POST' });
}

/** Copy text to the clipboard (with a fallback for browsers without the async clipboard API). */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement('textarea');
  area.value = text;
  document.body.appendChild(area);
  area.select();
  try {
    if (!document.execCommand('copy')) throw new Error('Copy failed; select the text and copy it by hand.');
  } finally {
    area.remove();
  }
}

export function getTask(id: string, signal?: AbortSignal): Promise<Task> {
  return request<Task>(`/tasks/${encodeURIComponent(id)}`, { signal });
}

export function listJobTasks(key: string, signal?: AbortSignal): Promise<Task[]> {
  return request<Task[]>(`/jobs/${encodeURIComponent(key)}/tasks`, { signal });
}

/** Queue a fresh Claude assessment of one job. Poll getTask; a 402 means the monthly budget is used up. */
export function rescore(key: string): Promise<Task> {
  return request<Task>(`/jobs/${encodeURIComponent(key)}/rescore`, { method: 'POST' });
}

export function getPreferences(signal?: AbortSignal): Promise<PreferencesResponse> {
  return request<PreferencesResponse>('/preferences', { signal });
}

/** What saving `prefs` would re-assess (the jobs in `scope`) and roughly cost. Saves nothing. */
export function previewPreferences(prefs: Preferences, scope: ReassessScope = 'stale'): Promise<ReassessPreview> {
  return request<ReassessPreview>('/preferences/preview', {
    method: 'POST',
    body: JSON.stringify({ prefs, reassess_scope: scope }),
  });
}

/** Save and re-rank now; with confirmReassess, also queue re-assessment of the jobs in `scope` (by default the
 * ones it makes stale). */
export function savePreferences(
  prefs: Preferences, confirmReassess = false, scope: ReassessScope = 'stale',
): Promise<SavePreferencesResult> {
  return request<SavePreferencesResult>('/preferences', {
    method: 'PUT',
    body: JSON.stringify({ prefs, confirm_reassess: confirmReassess, reassess_scope: scope }),
  });
}

/** How many active (not rejected) jobs Rescore all would re-assess, and roughly what it costs. */
export function rescorePreview(signal?: AbortSignal): Promise<RescorePreview> {
  return request<RescorePreview>('/rescore/preview', { signal });
}

/** The user's Rescore all that is still queued or running, or null. */
export function activeRescoreAll(signal?: AbortSignal): Promise<{ task: Task | null }> {
  return request<{ task: Task | null }>('/rescore/active', { signal });
}

/** Queue re-assessment of every active job after the user confirmed the cost. A 402 means the budget is used up. */
export function rescoreAll(): Promise<RescoreAllResult> {
  return request<RescoreAllResult>('/rescore', { method: 'POST', body: JSON.stringify({ confirm: true }) });
}

const job = (key: string) => `/jobs/${encodeURIComponent(key)}`;

/** Add a job by link (or by pasted description). An existing link returns created: false and the same key. */
export function addJob(input: AddJobInput): Promise<AddJobResult> {
  return request<AddJobResult>('/jobs', { method: 'POST', body: JSON.stringify(input) });
}

/** Save a pasted description for a posting that couldn't be read; queues extraction and scoring. */
export function putDescription(
  key: string, fields: { title?: string; company?: string; location?: string; description: string },
): Promise<{ task: Task; key: string }> {
  return request(`${job(key)}/description`, { method: 'PUT', body: JSON.stringify(fields) });
}

export function listContacts(q?: string, signal?: AbortSignal): Promise<ContactListItem[]> {
  return request<ContactListItem[]>(`/contacts${q ? `?q=${encodeURIComponent(q)}` : ''}`, { signal });
}

export function getContact(id: string, signal?: AbortSignal): Promise<ContactWithJobs> {
  return request<ContactWithJobs>(`/contacts/${encodeURIComponent(id)}`, { signal });
}

export function createContact(fields: ContactFields & { name: string }): Promise<Contact> {
  return request<Contact>('/contacts', { method: 'POST', body: JSON.stringify(fields) });
}

export function updateContact(id: string, fields: ContactFields): Promise<ContactWithJobs> {
  return request<ContactWithJobs>(`/contacts/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(fields) });
}

export function deleteContact(id: string): Promise<{ ok: boolean }> {
  return request(`/contacts/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** Link an existing contact (`contact_id`) or a new one (`contact`) to a job. Returns the updated job. */
export function linkContact(
  key: string, link: { contact_id: string } | { contact: ContactFields & { name: string } }, relation: Relation,
): Promise<JobDetail> {
  return request<JobDetail>(`${job(key)}/contacts`, { method: 'POST', body: JSON.stringify({ ...link, relation }) });
}

export function unlinkContact(key: string, contactId: string): Promise<JobDetail> {
  return request<JobDetail>(`${job(key)}/contacts/${encodeURIComponent(contactId)}`, { method: 'DELETE' });
}

export function createInterview(key: string, fields: InterviewFields): Promise<Interview> {
  return request<Interview>(`${job(key)}/interviews`, { method: 'POST', body: JSON.stringify(fields) });
}

export function updateInterview(id: string, fields: InterviewFields): Promise<Interview> {
  return request<Interview>(`/interviews/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(fields) });
}

export function deleteInterview(id: string): Promise<{ ok: boolean }> {
  return request(`/interviews/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function getPanel(signal?: AbortSignal): Promise<PanelOverview> {
  return request<PanelOverview>('/panel', { signal });
}

/** Start a blind panel: n jobs with two comparable drafts each. 409 when there are none. */
export function createPanelRun(n: number, mode: PanelMode): Promise<PanelRun> {
  return request<PanelRun>('/panel/runs', { method: 'POST', body: JSON.stringify({ n, mode }) });
}

export function getPanelRun(id: string, signal?: AbortSignal): Promise<PanelRun> {
  return request<PanelRun>(`/panel/runs/${encodeURIComponent(id)}`, { signal });
}

async function postPanelGrade(id: string, body: object): Promise<PanelGradeOutcome> {
  const res = await fetch(`${API_BASE}/panel/runs/${encodeURIComponent(id)}/grades`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Strelitzia': '1' },
    body: JSON.stringify(body),
  });
  if (res.status === 422) {
    const err = await res.clone().json().catch(() => null);
    if (err && Array.isArray(err.errors)) return { ok: false, errors: err.errors };
  }
  if (!res.ok) throw await failure(res);
  const out = (await res.json()) as { graded: number | null; warnings?: string[]; run: PanelRun };
  return { ok: true, graded: out.graded, warnings: out.warnings ?? [], run: out.run };
}

/** Import a model's pasted reply: ok with the run, or not ok with the errors (e.g. the wrong item count). */
export function importPanelGrades(id: string, grader: 'sonnet' | 'opus', text: string): Promise<PanelGradeOutcome> {
  return postPanelGrade(id, { grader, text });
}

/** Your blind pick for one item, in packet 1's order. */
export async function pickPanelItem(id: string, item: number, winner: PanelWinner): Promise<PanelRun> {
  const out = await postPanelGrade(id, { grader: 'you', item, winner });
  if (!out.ok) throw new ApiError(422, out.errors[0]);
  return out.run;
}

/** Start a recruiter review of the job's latest draft (409 when it has none): its prompt to paste into a chat. */
export function createReview(key: string): Promise<ReviewDetail> {
  return request<ReviewDetail>(`/jobs/${encodeURIComponent(key)}/reviews`, { method: 'POST' });
}

/** The job's reviews, newest first. */
export function listJobReviews(key: string, signal?: AbortSignal): Promise<ReviewSummary[]> {
  return request<ReviewSummary[]>(`/jobs/${encodeURIComponent(key)}/reviews`, { signal });
}

/** All the user's reviews, newest first. */
export function listReviews(signal?: AbortSignal): Promise<ReviewSummary[]> {
  return request<ReviewSummary[]>('/reviews', { signal });
}

export function getReview(id: string, signal?: AbortSignal): Promise<ReviewDetail> {
  return request<ReviewDetail>(`/reviews/${encodeURIComponent(id)}`, { signal });
}

/** Import a grader's pasted reply: ok with the review, or not ok with the errors (the reply doesn't fit the format). */
export async function importReviewReply(id: string, grader: ReviewGrader, modelLabel: string,
  text: string): Promise<ReviewImportOutcome> {
  const res = await fetch(`${API_BASE}/reviews/${encodeURIComponent(id)}/replies`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Strelitzia': '1' },
    body: JSON.stringify({ grader, model_label: modelLabel, text }),
  });
  if (res.status === 422) {
    const err = await res.clone().json().catch(() => null);
    if (err && Array.isArray(err.errors)) return { ok: false, errors: err.errors };
  }
  if (!res.ok) throw await failure(res);
  const out = (await res.json()) as { warnings?: string[]; review: ReviewDetail };
  return { ok: true, warnings: out.warnings ?? [], review: out.review };
}

/** Whether sign-in is on and who is signed in (never a 401: user is null without a session). */
export function getMe(signal?: AbortSignal): Promise<AuthMe> {
  return request<AuthMe>('/auth/me', { signal });
}

/** The Google sign-in page (a full-page redirect through the server; in proxy mode, on to the site's sign-in). */
export const LOGIN_URL = `${API_BASE}/auth/login`;

export function logout(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('/auth/logout', { method: 'POST' });
}

/** Proxy mode: end the site's session (its own endpoint, outside the dashboard's API). */
export async function siteLogout(url: string): Promise<void> {
  const res = await fetch(url, { method: 'POST', credentials: 'same-origin' });
  if (!res.ok) throw new ApiError(res.status, `Couldn't sign out of the site (${res.status})`);
}

export function getProfile(signal?: AbortSignal): Promise<ProfileResponse> {
  return request<ProfileResponse>('/profile', { signal });
}

export function saveProfile(profile: ProfileSave): Promise<ProfileResponse> {
  return request<ProfileResponse>('/profile', { method: 'PUT', body: JSON.stringify(profile) });
}

