import { useEffect, useState } from 'react';
import * as api from '../api';
import { day, GRADER_LABELS, graderLabel } from '../labels';
import Scorecard from './Scorecard';
import type { JobDetail, ReviewDetail, ReviewGrader } from '../types';

const CHATS: [string, string][] = [
  ['claude.ai', 'https://claude.ai/new'],
  ['chatgpt.com', 'https://chatgpt.com/'],
  ['gemini.google.com', 'https://gemini.google.com/app'],
];
const GRADERS = Object.keys(GRADER_LABELS) as ReviewGrader[];

type Import =
  | { state: 'idle' }
  | { state: 'importing' }
  | { state: 'failed'; errors: string[] }
  | { state: 'saved'; grader: string; warnings: string[] };

/** Recruiter review: start one of the job's latest draft, copy its prompt into any chat, paste each grader's reply
 * back. Shown once the job has a draft. */
export default function ReviewPanel({ job }: { job: JobDetail }) {
  const [review, setReview] = useState<ReviewDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState<'ok' | 'failed' | null>(null);
  const [grader, setGrader] = useState<ReviewGrader>('claude-sonnet');
  const [model, setModel] = useState('');
  const [text, setText] = useState('');
  const [result, setResult] = useState<Import>({ state: 'idle' });

  const hasDraft = Boolean(job.draft_version);
  useEffect(() => {
    if (!hasDraft) return;
    const ctrl = new AbortController();
    api.listJobReviews(job.key, ctrl.signal)
      .then((reviews) => (reviews?.length ? api.getReview(reviews[0].id, ctrl.signal) : null))
      .then((latest) => setReview(latest ?? null))
      .catch((err) => {
        if (!ctrl.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      });
    return () => ctrl.abort();
  }, [job.key, hasDraft]);

  async function copyPrompt(prompt: string) {
    try {
      await api.copyText(prompt);
      setCopied('ok');
    } catch {
      setCopied('failed');
    }
  }

  async function create() {
    setCreating(true);
    setError(null);
    setCopied(null);
    setResult({ state: 'idle' });
    try {
      const created = await api.createReview(job.key);
      setReview(created);
      await copyPrompt(created.prompt);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  }

  async function importReply() {
    if (!review) return;
    if (!text.trim()) {
      setResult({ state: 'failed', errors: ['Paste the grader\'s whole reply first.'] });
      return;
    }
    if (grader === 'other' && !model.trim()) {
      setResult({ state: 'failed', errors: ['Name the model you used.'] });
      return;
    }
    setResult({ state: 'importing' });
    setError(null);
    try {
      const out = await api.importReviewReply(review.id, grader, model.trim(), text);
      if (out.ok) {
        setReview(out.review);
        setText('');
        setResult({ state: 'saved', grader: graderLabel(grader, model.trim()), warnings: out.warnings });
      } else {
        setResult({ state: 'failed', errors: out.errors });
      }
    } catch (err) {
      setResult({ state: 'idle' });
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (!hasDraft) return null;
  const newer = review?.draft_version != null && review.draft_version < job.draft_version!;
  const oldCriteria = review != null && review.prompt_version !== review.current_prompt_version;

  return (
    <section className="card review-panel" aria-label="Recruiter review">
      <div className="card-head">
        <h2>Recruiter review</h2>
        {review && <span className="muted">Started {day(review.created_at)}</span>}
      </div>
      <p className="muted small">
        A recruiter's grades for the latest draft, from any chat model. Paste the same prompt into several models to
        compare them.
      </p>
      {(newer || oldCriteria) && (
        <p className="notice" role="status">
          {newer && <>This review is of draft v{review!.draft_version}; v{job.draft_version} is newer. </>}
          {oldCriteria && <>The review criteria changed since this review started. </>}
          Get a new review to grade the current one.
        </p>
      )}
      <div className="action-group">
        <button type="button" className={review ? undefined : 'primary'} disabled={creating} onClick={create}>
          {creating ? 'Preparing…' : review ? 'Get a new review' : 'Get a recruiter review'}
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {review && (
        <>
          <nav className="link-row" aria-label="Chats">
            <button type="button" onClick={() => copyPrompt(review.prompt)}>
              {copied === 'ok' ? 'Copied prompt' : 'Copy prompt'}
            </button>
            {CHATS.map(([label, href]) => (
              <a key={label} href={href} target="_blank" rel="noreferrer noopener">{label} ↗</a>
            ))}
          </nav>
          <p className="muted small">
            {copied === 'failed' ? 'Couldn\'t copy: select the prompt below and copy it. ' : ''}
            Paste the prompt into a new chat, then paste the whole reply here and say which model wrote it.
          </p>
          {copied === 'failed' && <textarea readOnly rows={4} aria-label="Prompt" value={review.prompt} />}
          <div className="form-grid">
            <label className="field"><span>Grader</span>
              <select value={grader} onChange={(e) => setGrader(e.target.value as ReviewGrader)}>
                {GRADERS.map((g) => <option key={g} value={g}>{GRADER_LABELS[g]}</option>)}
              </select>
            </label>
            <label className="field"><span>{grader === 'other' ? 'Model name' : 'Model name (optional)'}</span>
              <input value={model} maxLength={100} placeholder={grader === 'other' ? 'e.g. Llama 4' : 'e.g. GPT-5 Thinking'}
                onChange={(e) => setModel(e.target.value)} />
            </label>
          </div>
          <label className="field"><span>Reply</span>
            <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <div className="action-group">
            <button type="button" disabled={result.state === 'importing'} onClick={importReply}>
              {result.state === 'importing' ? 'Importing…' : 'Import'}
            </button>
          </div>
          {result.state === 'failed' && (
            <div className="check-errors" role="alert">
              <p><strong>Not imported.</strong> Ask the model to fix its reply in the same chat, then paste it again.</p>
              <ol aria-label="Problems">{result.errors.map((e, i) => <li key={i}>{e}</li>)}</ol>
            </div>
          )}
          {result.state === 'saved' && (
            <p className="progress ok" role="status">Imported {result.grader}'s review.</p>
          )}
          {result.state === 'saved' && result.warnings.length > 0 && (
            <ul className="muted small" aria-label="Warnings">{result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
          )}
          <Scorecard review={review} />
        </>
      )}
    </section>
  );
}
