import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../api';
import Flower from '../components/Flower';
import ProfileDocLinks from '../components/ProfileDocLinks';
import { Group, TagInput } from '../components/FormParts';
import { humanize, relativeTime } from '../labels';
import type { ProfileFields, ProfileResponse } from '../types';

type FieldKey = keyof ProfileFields;
type TextKey = { [K in FieldKey]: ProfileFields[K] extends string ? K : never }[FieldKey];

const isEmpty = (v: unknown) => v === null || v === '' || (Array.isArray(v) && v.length === 0);

/** The profile with `draft` filled into the fields that are still empty. */
function withDraft(form: ProfileFields, draft: Partial<ProfileFields>): ProfileFields {
  const next = { ...form };
  for (const [key, value] of Object.entries(draft) as [FieldKey, ProfileFields[FieldKey]][]) {
    if (value !== undefined && !isEmpty(value) && isEmpty(form[key])) (next as Record<FieldKey, unknown>)[key] = value;
  }
  return next;
}

export default function ProfilePage() {
  const [data, setData] = useState<ProfileResponse | null>(null);
  const [form, setForm] = useState<ProfileFields | null>(null);
  const [saved, setSaved] = useState('');
  // The resume's draft from Sync now (until Save or Discard); a field is highlighted while it holds the drafted value.
  const [draft, setDraft] = useState<Partial<ProfileFields>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncNote, setSyncNote] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);

  function load(res: ProfileResponse) {
    setData(res);
    setForm(res.profile);
    setSaved(JSON.stringify(res.profile));
  }

  useEffect(() => {
    const ctrl = new AbortController();
    api.getProfile(ctrl.signal).then(load).catch((err) => {
      if (!ctrl.signal.aborted) setError(err.message || String(err));
    });
    return () => ctrl.abort();
  }, []);

  if (error && !form) return <p className="notice error" role="alert">Couldn't load your profile: {error}</p>;
  if (!form || !data) {
    return (
      <div className="loader-state" aria-live="polite" aria-busy="true">
        <Flower variant="loader" size={64} />
        Loading profile…
      </div>
    );
  }

  const dirty = JSON.stringify(form) !== saved;
  const drafted = (Object.keys(draft) as FieldKey[]).filter(
    (k) => JSON.stringify(form[k]) === JSON.stringify(draft[k]));
  const set = <K extends FieldKey>(key: K, value: ProfileFields[K]) => setForm((f) => (f ? { ...f, [key]: value } : f));

  const row = (key: FieldKey, name: string, control: ReactNode) => (
    <div key={key} className={`pref-row${drafted.includes(key) ? ' drafted' : ''}`}>
      <div className="pref-label">{name}</div>
      <div className="pref-value">{control}</div>
      {drafted.includes(key) && <span className="tag tag-soon" title="From your resume; Save to keep it">From resume</span>}
    </div>
  );
  const textRow = (key: TextKey, name: string, type = 'text', placeholder?: string) => row(key, name, (
    <input type={type} aria-label={name} value={form[key]} placeholder={placeholder}
      onChange={(e) => set(key, e.target.value)} />
  ));

  async function onSave() {
    if (!form) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      load(await api.saveProfile(form));
      setDraft({});
      setMessage('Saved.');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function onDiscard() {
    setForm(JSON.parse(saved));
    setDraft({});
  }

  async function onSync() {
    setSyncing(true);
    setSyncError(null);
    setSyncNote(null);
    try {
      const res = await api.syncProfileDocs();
      setData(res);  // the fields being edited stay as typed
      setProblems(res.problems);
      const found = Object.keys(res.draft ?? {}).length > 0;
      if (found) {
        setForm((f) => (f ? withDraft(f, res.draft) : f));
        setDraft((d) => ({ ...d, ...res.draft }));
      }
      if (res.parse_error) setSyncError(res.parse_error);
      if (!res.ok) return;
      if (found) setSyncNote('Synced. The highlighted fields are from your resume: check them, then Save.');
      else setSyncNote(res.changed ? 'Synced: your changes are in.' : 'Synced: nothing changed.');
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : String(err));
    } finally {
      setSyncing(false);
    }
  }

  return (
    <article className="prefs-page profile-page">
      <h1>Profile</h1>
      <p className="muted">
        Profile is about you; <Link to="/preferences">Preferences</Link> is about the job you want. Scoring reads your
        resume, and the resume workbench reads your content library and these details.
      </p>

      <Group title="About you">
        {textRow('first_name', 'First name')}
        {textRow('last_name', 'Last name')}
        {textRow('email', 'Email', 'email')}
        {textRow('phone', 'Phone', 'tel')}
        {textRow('linkedin_url', 'LinkedIn', 'url', 'https://www.linkedin.com/in/…')}
        {textRow('github_url', 'GitHub', 'url', 'https://github.com/…')}
        {textRow('location', 'Location', 'text', 'City, state')}
      </Group>

      <Group title="Experience">
        {textRow('current_job_title', 'Current title')}
        {row('years_experience', 'Years of experience', (
          <input type="number" min={0} max={70} step={0.5} aria-label="Years of experience"
            value={form.years_experience ?? ''} onChange={(e) => {
              const n = e.target.value.trim() === '' ? null : Number(e.target.value);
              set('years_experience', n !== null && Number.isFinite(n) && n >= 0 ? n : null);
            }} />
        ))}
        {row('education_level', 'Education', (
          <select aria-label="Education" value={form.education_level ?? ''}
            onChange={(e) => set('education_level', e.target.value || null)}>
            <option value="">Not set</option>
            {data.options.education_level.map((o) => <option key={o} value={o}>{humanize(o)}</option>)}
          </select>
        ))}
        {row('skills', 'Skills', (
          <TagInput label="Skills" values={form.skills} placeholder="e.g. Python; Enter to add"
            onChange={(v) => set('skills', v)} />
        ))}
      </Group>

      <Group title="Content library and resume" hint="Both live in Google Docs in the Drive folder Strelitzia/Profile.
        Edit them there; the app reads them again before every Claude packet and check, or when you press Sync now.">
        {data.profile_docs ? (
          <>
            <ProfileDocLinks docs={data.profile_docs} label="Profile Docs" />
            <p className="muted small">
              Last synced {relativeTime(data.profile_docs.library?.synced_at)}.{' '}
              <button type="button" disabled={syncing} onClick={onSync}>{syncing ? 'Syncing…' : 'Sync now'}</button>
            </p>
            {syncNote && <p className="ok-text" role="status">{syncNote}</p>}
            {syncError && <p className="error" role="alert">{syncError}</p>}
            {problems.length > 0 && (
              <div className="notice error" role="alert">
                <p>Nothing was synced. Fix these in the Docs, then Sync now:</p>
                <ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul>
              </div>
            )}
          </>
        ) : (
          <p className="muted">
            Your content library and resume aren't in Google Docs yet. Set them up on
            the <Link to="/claude-setup">Claude setup page</Link>.
          </p>
        )}
      </Group>

      <div className="save-bar">
        <button type="button" className="primary" disabled={!dirty || busy} onClick={onSave}>Save</button>
        {dirty && <button type="button" disabled={busy} onClick={onDiscard}>Discard</button>}
        {message && !dirty && <span className="ok-text" role="status">{message}</span>}
        {error && <span className="error" role="alert">{error}</span>}
      </div>
    </article>
  );
}
