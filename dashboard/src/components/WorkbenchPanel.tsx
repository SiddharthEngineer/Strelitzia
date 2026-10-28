import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../api';
import { day } from '../labels';
import type { CoverPacketResult, DraftKind, JobDetail, PacketResult } from '../types';
import CoveragePanel from './CoveragePanel';

const CLAUDE_URL = 'https://claude.ai/projects';

interface Props {
  job: JobDetail;
  onSaved: (job: JobDetail) => void;
  /** Shown above the cover letter step (the job's cover notes box). */
  coverNotes?: ReactNode;
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

interface StepProps {
  job: JobDetail;
  kind: DraftKind;
  onSaved: (job: JobDetail) => void;
  /** Why the step can't start yet, or null when it can. */
  blocked: string | null;
}

/** One Claude step: Open in Claude (its packet, draft Doc and prompt), then Check & format that draft Doc. */
function Step({ job, kind, onSaved, blocked }: StepProps) {
  const [packet, setPacket] = useState<PacketResult | CoverPacketResult | null>(null);
  const [copied, setCopied] = useState<'ok' | 'failed' | null>(null);
  const [opening, setOpening] = useState(false);
  const [problem, setProblem] = useState<Failure | null>(null);
  const [check, setCheck] = useState<Check>({ state: 'idle' });
  const resume = kind === 'resume';
  const title = resume ? 'Resume' : 'Cover letter';

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
      const p = resume ? await api.openPacket(job.key) : await api.openCoverPacket(job.key);
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
      const out = await api.checkDrafts(job.key, kind);
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

  const draftUrl = resume
    ? (packet as PacketResult | null)?.resume_draft_url ?? job.resume_draft_url
    : (packet as CoverPacketResult | null)?.cover_draft_url ?? job.cover_draft_url;
  // The resume packet's URL is stored on the job; the cover letter packet is only known once it's opened here.
  const docs: [string, string | null | undefined][] = [
    [resume ? 'Packet' : 'Cover letter packet', packet?.doc_url ?? (resume ? job.packet_doc_url : null)],
    [resume ? 'Resume draft' : 'Cover letter draft', draftUrl],
  ];
  const hasDraft = Boolean(draftUrl);

  return (
    <section className="workbench-step" aria-label={title}>
      <h3>{title}</h3>
      {blocked && <p className="muted small">{blocked}</p>}
      <div className="action-group">
        <button type="button" className="primary" disabled={opening || Boolean(blocked)} onClick={openInClaude}>
          {opening ? 'Preparing…' : 'Open in Claude'}
        </button>
        <button type="button" disabled={Boolean(blocked) || !hasDraft || check.state === 'checking'}
          onClick={checkAndFormat}
          title={hasDraft ? undefined : 'Open in Claude first: it creates the draft Doc'}>
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
            Paste it into a new chat in your project; Claude writes the {resume ? 'resume' : 'cover letter'} draft
            Doc, then press Check &amp; format.
            {' · '}rules {packet.rules_version}
          </span>
        </div>
      )}
      {docs.some(([, href]) => href) && (
        <nav className="link-row" aria-label={`${title} Docs`}>
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
          <p><strong>Not saved.</strong> Copy the fix prompt into the same chat; Claude fixes the Doc.</p>
          <ol aria-label="Problems">{check.errors.map((e, i) => <li key={i}>{e}</li>)}</ol>
          <button type="button" onClick={copyFix}>{check.copied ? 'Copied fix prompt' : 'Copy fix prompt'}</button>
        </div>
      )}
      {check.state === 'saved' && (
        <p className="progress ok" role="status">
          {resume
            ? <>Saved draft v{check.version}.{check.fill != null && ` The resume fills ${check.fill}% of the page.`}</>
            : <>Saved the cover letter with draft v{check.version}.</>}
        </p>
      )}
      {(check.state === 'saved' || check.state === 'failed') && check.warnings.length > 0 && (
        <ul className="muted small" aria-label="Warnings">{check.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
      )}
    </section>
  );
}

/** Resume & cover letter: two Claude steps (the resume, then the cover letter from the accepted resume), the saved
 * files and coverage. */
export default function WorkbenchPanel({ job, onSaved, coverNotes }: Props) {
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

      <Step job={job} kind="resume" onSaved={onSaved} blocked={null} />
      {coverNotes}
      <Step job={job} kind="cover" onSaved={onSaved}
        blocked={job.draft_version ? null : 'Check & format a resume draft first: the letter is written from it.'} />

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
