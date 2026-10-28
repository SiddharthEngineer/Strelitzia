import { useEffect, useRef, useState, type FormEvent } from 'react';
import { patchJob } from '../api';
import { day, WORK_MODE_LABELS } from '../labels';
import type { JobDetail, JobPatch, WorkMode } from '../types';

interface Props {
  job: JobDetail;
  onSaved: (job: JobDetail) => void;
  onClose: () => void;
}

/** Fix a job's title, company, location, work mode, salary and deadline. The posting link can't change. */
export default function EditJobDialog({ job, onSaved, onClose }: Props) {
  const titleRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState(job.title ?? '');
  const [company, setCompany] = useState(job.company ?? '');
  const [location, setLocation] = useState(job.location ?? '');
  const [workMode, setWorkMode] = useState<string>(job.work_mode ?? '');
  const [salary, setSalary] = useState(job.salary ?? '');
  const [deadline, setDeadline] = useState(job.deadline ? day(job.deadline) : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || !company.trim()) {
      setError('The title and company can’t be empty.');
      return;
    }
    // Send only what changed, so an untouched field keeps its value.
    const patch: JobPatch = {};
    if (title.trim() !== (job.title ?? '')) patch.title = title.trim();
    if (company.trim() !== (job.company ?? '')) patch.company = company.trim();
    if (location.trim() !== (job.location ?? '')) patch.location = location.trim() || null;
    if (workMode !== (job.work_mode ?? '')) patch.work_mode = (workMode || null) as WorkMode | null;
    if (salary.trim() !== (job.salary ?? '')) patch.salary = salary.trim() || null;
    if (deadline !== (job.deadline ? day(job.deadline) : '')) patch.deadline = deadline || null;
    if (!Object.keys(patch).length) {
      onClose();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(await patchJob(job.key, patch));
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="dialog add-job" role="dialog" aria-modal="true" aria-labelledby="edit-job-title" onSubmit={submit}>
        <h2 id="edit-job-title">Edit job</h2>
        <div className="form-grid">
          <label className="field"><span>Title</span>
            <input ref={titleRef} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
          <label className="field"><span>Company</span>
            <input value={company} onChange={(e) => setCompany(e.target.value)} /></label>
          <label className="field"><span>Location</span>
            <input value={location} onChange={(e) => setLocation(e.target.value)} /></label>
          <label className="field"><span>Work mode</span>
            <select value={workMode} onChange={(e) => setWorkMode(e.target.value)}>
              <option value="">Not set</option>
              {Object.entries(WORK_MODE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label className="field"><span>Salary</span>
            <input value={salary} placeholder="e.g. $120k – $150k" onChange={(e) => setSalary(e.target.value)} /></label>
          <label className="field"><span>Deadline</span>
            <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
        </div>
        <p className="muted small">The posting link can’t change: to fix it, delete this job and add it again.</p>
        <div className="dialog-actions">
          <button type="submit" className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
          <button type="button" disabled={busy} onClick={onClose}>Cancel</button>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
    </div>
  );
}
