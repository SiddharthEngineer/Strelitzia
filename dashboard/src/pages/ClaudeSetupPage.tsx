import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import * as api from '../api';
import Flower from '../components/Flower';
import ProfileDocLinks from '../components/ProfileDocLinks';
import { relativeTime } from '../labels';
import type { ClaudeSetup, ProfileDocs } from '../types';

// The ?drive= outcome the Drive connect callback (web/auth.py) redirects back with.
const DRIVE_OUTCOMES: Record<string, { text: string; error: boolean }> = {
  connected: { text: 'Google Drive is connected.', error: false },
  denied: { text: "Google Drive wasn't connected: allow access to the files Strelitzia creates and try again.", error: true },
  error: { text: "Couldn't connect Google Drive. Try again.", error: true },
  unavailable: { text: "This server can't connect Google Drive yet.", error: true },
};

/** "A", "A and B", "A, B and C". */
function joinNames(names: string[]): string {
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/** When the app last pulled the Docs (the older of the two): edits made in a Doc since then aren't in its copy. */
function lastSynced(docs: ProfileDocs | null): string | null {
  const times = [docs?.library?.synced_at, docs?.resume?.synced_at].filter((t): t is string => Boolean(t));
  return times.length ? times.reduce((a, b) => (new Date(a) <= new Date(b) ? a : b)) : null;
}

/** One-time setup: Drive, the Profile Docs, and a Claude Project with the instructions (the rules come in each packet). */
export default function ClaudeSetupPage() {
  const [params, setParams] = useSearchParams();
  const outcome = DRIVE_OUTCOMES[params.get('drive') ?? ''];
  const [setup, setSetup] = useState<ClaudeSetup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  // The Docs that setup would overwrite (asked before it does).
  const [existing, setExisting] = useState<string[] | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    api.getClaudeSetup(ctrl.signal).then(setSetup).catch((err) => {
      if (!ctrl.signal.aborted) setError(err.message || String(err));
    });
    return () => ctrl.abort();
  }, []);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const setUpDocs = (overwrite: boolean) => run(async () => {
    const res = await api.setupProfileDocs(overwrite);
    if (!res.ok) {
      setExisting(res.existing);
      return;
    }
    setExisting(null);
    setSetup((s) => (s ? { ...s, profile_docs: res.profile.profile_docs } : s));
  });

  const disconnect = () => run(async () => {
    await api.disconnectDrive();
    setParams({}, { replace: true });  // the ?drive= outcome no longer applies
    setSetup(await api.getClaudeSetup());
  });

  async function copyInstructions() {
    if (!setup) return;
    try {
      await api.copyText(setup.project_instructions);
      setCopied(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (!setup) {
    return error ? <p className="notice error" role="alert">Couldn't load the Claude setup: {error}</p> : (
      <div className="loader-state" aria-live="polite" aria-busy="true"><Flower variant="loader" size={64} />Loading…</div>
    );
  }

  return (
    <article className="job-page claude-setup">
      <h1>Claude setup</h1>
      <p className="muted">
        Resumes and cover letters are written in your Claude Pro plan. Do this once; after that every job's
        <strong> Open in Claude</strong> button gives you a prompt for a new chat in the project.
      </p>
      {outcome && <p className={outcome.error ? 'notice error' : 'notice'} role="status">{outcome.text}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <ol className="setup-steps">
        <li>
          Connect Google Drive. The app keeps your Profile Docs, packets and PDFs in a Strelitzia folder there.
          {!setup.drive && (
            <p className="muted">Google Drive isn't set up ({setup.drive_detail}).</p>
          )}
          {!setup.drive && setup.connect_url && (
            <a className="button" href={setup.connect_url}>Connect Google Drive</a>
          )}
          {setup.drive_source === 'user' && (
            <p className="muted small">
              <strong>Connected</strong> · files go to a Strelitzia folder in your Drive ({setup.drive_detail}).{' '}
              <button type="button" disabled={busy} onClick={disconnect}>Disconnect</button>{' '}
              {setup.connect_url && <a href={setup.connect_url}>Reconnect</a>}
            </p>
          )}
          {setup.drive_source === 'legacy' && <p className="muted small"><strong>Connected</strong> ({setup.drive_detail}).</p>}
        </li>
        <li>
          Set up your Profile Docs: the app creates <strong>Content Library</strong> and
          <strong> Base Resume</strong> in the Drive folder Strelitzia/Profile, filled with what it has now.
          From then on you edit your library and resume there, and every packet reads them fresh.
          <p className="muted small">
            The app can only see files it created. Edit these two Docs; don't add new ones to the folder (by hand or
            from Claude), because the app won't see them. The old Docs in Strelitzia/_Claude are no longer used and
            can be deleted.
          </p>
          {setup.profile_docs && <ProfileDocLinks docs={setup.profile_docs} label="Profile Docs" />}
          {existing ? (
            // setup_profile_docs rewrites the Docs from the app's last-synced copy, so newer edits in the Docs are lost.
            <div className="notice warning" role="alertdialog" aria-label="Replace the Profile Docs?">
              <p>
                <strong>This replaces the text of {joinNames(existing)}.</strong> They'll be rewritten from the app's
                last-synced copy (the example templates where that copy is empty). Edits you made in the Docs since the
                last sync ({relativeTime(lastSynced(setup.profile_docs))}) will be lost. Use Sync now on the Profile
                page first to keep them.
              </p>
              <button type="button" className="primary" disabled={busy} onClick={() => setUpDocs(true)}>Replace the Docs</button>{' '}
              <button type="button" disabled={busy} onClick={() => setExisting(null)}>Cancel</button>
            </div>
          ) : (
            <>
              <button type="button" disabled={busy || !setup.drive} onClick={() => setUpDocs(false)}>
                {busy ? 'Setting up…' : 'Set up Profile Docs'}
              </button>
              {setup.profile_docs && (
                <p className="muted small">Your Profile Docs already exist: setting them up again replaces their text.</p>
              )}
            </>
          )}
        </li>
        <li>
          On <a href="https://claude.ai/projects" target="_blank" rel="noreferrer noopener">claude.ai ↗</a>, create a
          project named <strong>{setup.project_name}</strong> and paste these project instructions (Project →
          Instructions):
          <p className="pre card">{setup.project_instructions}</p>
          <button type="button" onClick={copyInstructions}>{copied ? 'Copied' : 'Copy instructions'}</button>
          <p>
            Turn on the Google Docs connector so Claude can open the packet, your Profile Docs and the drafts. There's
            nothing to upload: the rules come inside each job's packet. If the project's knowledge still has an old
            rules file, delete it.
          </p>
          <p className="muted small">
            Instructions version {setup.instructions_version} · rules version {setup.rules_version}. When the
            instructions change, Check &amp; format warns you to paste them again.
          </p>
        </li>
      </ol>
    </article>
  );
}
