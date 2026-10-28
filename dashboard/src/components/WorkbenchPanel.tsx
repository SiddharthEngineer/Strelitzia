import { useState } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../api';
import { day } from '../labels';
import type { JobDetail, PacketResult } from '../types';
import CoveragePanel from './CoveragePanel';

const CLAUDE_URL = 'https://claude.ai/projects';

interface Props {
  job: JobDetail;
  onSaved: (job: JobDetail) => void;
}

type Check =
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'failed'; errors: string[]; warnings: string[]; fixPrompt: string; copied: boolean }
  | { state: 'saved'; version: number; warnings: string[]; fill: number | null };

/** An API failure as the panel shows it: Drive not connected (a pointer to Claude setup, not an error), else the
 * message with any Profile Docs problems. */
type Failure = { kind: 'drive' } | { kind: 'error'; message: string; problems: string[] };

function failure(err: unknown): Failure {
  if (err instanceof api.ApiError && err.status === 409) {
    const problems = (err.body as { problems?: unknown } | null)?.problems;
    if (Array.isArray(problems)) return { kind: 'error', message: err.message, problems: problems.map(String) };
    if (/Google Drive/.test(err.message)) return { kind: 'drive' };
  }
  return { kind: 'error', message: err instanceof Error ? err.message : String(err), problems: [] };
}

/** Resume & cover letter: open the job in Claude (the packet and two draft Docs), Check & format the drafts, and
 * see the saved files and coverage. */
export default function WorkbenchPanel({ job, onSaved }: Props) {
  const [packet, setPacket] = useState<PacketResult | null>(null);
  const [copied, setCopied] = useState<'ok' | 'failed' | null>(null);
  const [opening, setOpening] = useState(false);
  const [problem, setProblem] = useState<Failure | null>(null);
  const [check, setCheck] = useState<Check>({ state: 'idle' });

  async function copyPrompt(prompt: string) {
    try {
      await api.copyText(prompt);
      setCopied('ok');
    } catch {
      setCopied('failed');
    }
  }

  async function openInClaude() {
    setOpening(true);
    setProblem(null);
    setCopied(null);
    try {
      const p = await api.openPacket(job.key);
      setPacket(p);
      await copyPrompt(p.prompt);
    } catch (err) {
      setProblem(failure(err));
    } finally {
      setOpening(false);
    }
  }

  async function checkAndFormat() {
    setCheck({ state: 'checking' });
    setProblem(null);
    try {
      const out = await api.checkDrafts(job.key);
      if (out.ok) {
        setCheck({ state: 'saved', version: out.outcome.draft_version, warnings: out.outcome.warnings,
                   fill: out.outcome.fill_pct ?? null });
        onSaved(out.job);
      } else {
        setCheck({ state: 'failed', errors: out.errors, warnings: out.warnings, fixPrompt: out.fix_prompt, copied: false });
      }
    } catch (err) {
      setCheck({ state: 'idle' });
      setProblem(failure(err));
    }
  }

  async function copyFix() {
    if (check.state !== 'failed') return;
    try {
      await api.copyText(check.fixPrompt);
      setCheck({ ...check, copied: true });
    } catch (err) {
      setProblem(failure(err));
    }
  }

  const docs: [string, string | null | undefined][] = [
    ['Packet', packet?.doc_url ?? job.packet_doc_url],
    ['Resume draft', packet?.resume_draft_url ?? job.resume_draft_url],
    ['Cover letter draft', packet?.cover_draft_url ?? job.cover_draft_url],
  ];
  const hasDrafts = Boolean(packet?.resume_draft_url ?? job.resume_draft_url);
  // A PDF still on the server is the newest draft (a successful Drive upload removes it), so it wins over Drive.
  const files: [string, string | null | undefined][] = [
    ['Resume PDF', job.links.resume_pdf || job.links.resume],
    ['Resume DOCX', job.links.resume_docx],
    ['Cover letter PDF', job.links.cover_letter_pdf || job.links.cover_letter],
  ];
  const shownFiles = files.filter(([, href]) => href);
  const history = job.draft_history ?? [];

  return (
    <section className="card workbench" aria-label="Resume & cover letter">
      <div className="card-head">
        <h2>Resume &amp; cover letter</h2>
        {job.draft_version ? <span className="muted">Draft v{job.draft_version}</span> : null}
      </div>
      <p className="muted small">
        Resumes are written in your Claude project. Not set up yet? See <Link to="/claude-setup">Claude setup</Link>.
      </p>

      <div className="action-group">
        <button type="button" className="primary" disabled={opening} onClick={openInClaude}>
          {opening ? 'Preparing…' : 'Open in Claude'}
        </button>
        <button type="button" disabled={!hasDrafts || check.state === 'checking'} onClick={checkAndFormat}
          title={hasDrafts ? undefined : 'Open in Claude first: it creates the draft Docs'}>
          {check.state === 'checking' ? 'Checking…' : 'Check & format'}
        </button>
      </div>
      {problem?.kind === 'drive' && (
        <p className="notice" role="status">
          Resumes are written through Google Drive. Connect Google Drive on
          the <Link to="/claude-setup">Claude setup page</Link>, then Open in Claude again.
        </p>
      )}
      {packet && (
        <div className="progress ok" role="status">
          <span>
            {copied === 'failed' ? 'Couldn\'t copy: select the prompt below and copy it. ' : 'Copied the prompt. '}
            Paste it into a new chat in your project; Claude writes the two draft Docs, then press Check &amp; format.
            {' · '}rules {packet.rules_version}
          </span>
        </div>
      )}
      {docs.some(([, href]) => href) && (
        <nav className="link-row" aria-label="Claude Docs">
          {docs.filter(([, href]) => href).map(([label, href]) => (
            <a key={label} href={href!} target="_blank" rel="noreferrer noopener">{label} ↗</a>
          ))}
          <a href={CLAUDE_URL} target="_blank" rel="noreferrer noopener">claude.ai ↗</a>
          {packet && (
            <button type="button" onClick={() => copyPrompt(packet.prompt)}>
              {copied === 'ok' ? 'Copied prompt' : 'Copy prompt'}
            </button>
          )}
        </nav>
      )}
      {packet && copied === 'failed' && <textarea readOnly rows={4} aria-label="Prompt" value={packet.prompt} />}
      {problem?.kind === 'error' && (
        <div className="error" role="alert">
          <p>{problem.message}</p>
          {problem.problems.length > 0 && <ul>{problem.problems.map((p) => <li key={p}>{p}</li>)}</ul>}
        </div>
      )}
      {check.state === 'failed' && (
        <div className="check-errors" role="alert">
          <p><strong>Not saved.</strong> Copy the fix prompt into the same chat; Claude fixes the Docs.</p>
          <ol aria-label="Problems">{check.errors.map((e, i) => <li key={i}>{e}</li>)}</ol>
          <button type="button" onClick={copyFix}>{check.copied ? 'Copied fix prompt' : 'Copy fix prompt'}</button>
        </div>
      )}
      {check.state === 'saved' && (
        <p className="progress ok" role="status">
          Saved draft v{check.version}.{check.fill != null && ` The resume fills ${check.fill}% of the page.`}
        </p>
      )}
      {(check.state === 'saved' || check.state === 'failed') && check.warnings.length > 0 && (
        <ul className="muted small" aria-label="Warnings">{check.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
      )}

      {shownFiles.length > 0 && (
        <nav className="link-row" aria-label="Files">
          {shownFiles.map(([label, href]) => (
            <a key={label} href={href!} target="_blank" rel="noreferrer noopener">{label} ↗</a>
          ))}
        </nav>
      )}
      {job.notes_for_user && <p className="muted small">Claude's note: {job.notes_for_user}</p>}
      {job.coverage && <CoveragePanel coverage={job.coverage} unmet={job.unmet ?? []} />}
      {history.length > 0 && (
        <details>
          <summary>Draft history</summary>
          <ol className="history" aria-label="Draft history">
            {history.slice().reverse().map((h) => (
              <li key={h.version}>
                v{h.version} · {day(h.at)} · rules {h.rules_version}
                {job.submitted_draft_version === h.version && <strong> · submitted</strong>}
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
