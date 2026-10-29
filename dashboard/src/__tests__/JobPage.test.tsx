import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';
import { todayIso } from '../labels';
import JobPage, { compensation } from '../pages/JobPage';
import type { Task } from '../types';
import { jobDetail } from './fixtures';

vi.mock('../api');

function task(state: Task['state'], extra: Partial<Task> = {}): Task {
  return {
    id: 't1', url: 'https://example.com/job/1', kind: 'rescore', state, created_at: '2026-10-05T20:00:00+00:00',
    started_at: state === 'queued' ? null : '2026-10-05T20:00:01+00:00',
    finished_at: state === 'done' || state === 'error' ? '2026-10-05T20:00:30+00:00' : null,
    error: state === 'error' ? 'The Claude API is overloaded right now; try again in a few minutes.' : null,
    key: 'abc123', ...extra,
  };
}

function renderJob() {
  return render(
    <MemoryRouter initialEntries={['/jobs/abc123']}>
      <Routes>
        <Route path="/jobs/:key" element={<JobPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(api.getJob).mockResolvedValue(jobDetail());
  vi.mocked(api.listJobTasks).mockResolvedValue([]);
  vi.mocked(api.listJobReviews).mockResolvedValue([]);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('JobPage sections', () => {
  it('renders the extracted details', async () => {
    renderJob();
    expect(await screen.findByRole('heading', { name: 'Data Scientist' })).toBeInTheDocument();
    for (const title of ['Summary', 'Responsibilities', 'Required qualifications', 'Preferred qualifications', 'Skills',
      'Compensation', 'Location and work mode', 'Seniority and type', 'Education and experience',
      'Sponsorship and clearance', 'Benefits', 'Team', 'Status history']) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
    }
    expect(screen.getByText('$120,000 – $150,000 per year')).toBeInTheDocument();
    expect(screen.getByText('Spark')).toHaveClass('chip-preferred');
    expect(screen.getByText('3+ years')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Posting/ })).toHaveAttribute('href', 'https://example.com/job/1');
    expect(screen.queryByRole('link', { name: /Drive folder/ })).toBeNull(); // missing links are hidden
    expect(screen.queryByText(/Not extracted yet/)).toBeNull();
  });

  it('falls back to the raw description without details', async () => {
    vi.mocked(api.getJob).mockResolvedValue(jobDetail({ details: null }));
    renderJob();
    expect(await screen.findByText(/Not extracted yet/)).toBeInTheDocument();
    expect(screen.getByText('We are hiring a data scientist to build models.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Responsibilities' })).toBeNull();
  });

  it('formats compensation ranges', () => {
    const d = jobDetail().details!;
    expect(compensation({ ...d, salary_min: 45, salary_max: null, salary_period: 'hour' })).toBe('from $45 per hour');
    expect(compensation({ ...d, salary_min: null, salary_max: null })).toBeNull();
  });
});

describe('JobPage status actions', () => {
  it('marks submitted with today by default', async () => {
    const user = userEvent.setup();
    vi.mocked(api.setStatus).mockResolvedValue(jobDetail({ status: 'submitted', status_color: 'blue', submitted_date: todayIso() }));
    renderJob();
    await user.click(await screen.findByRole('button', { name: 'Mark submitted' }));
    expect(screen.getByLabelText('Submitted on')).toHaveValue(todayIso());
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(api.setStatus).toHaveBeenCalledWith('abc123', 'submitted', todayIso());
    expect(await screen.findByLabelText('Submitted date')).toHaveValue(todayIso());
  });

  it('marks submitted with an edited date, then edits it inline', async () => {
    const user = userEvent.setup();
    vi.mocked(api.setStatus).mockResolvedValue(jobDetail({ status: 'submitted', status_color: 'blue', submitted_date: '2026-09-28' }));
    vi.mocked(api.patchJob).mockResolvedValue(jobDetail({ status: 'submitted', status_color: 'blue', submitted_date: '2026-09-27' }));
    renderJob();
    await user.click(await screen.findByRole('button', { name: 'Mark submitted' }));
    const input = screen.getByLabelText('Submitted on');
    await user.clear(input);
    await user.type(input, '2026-09-28');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(api.setStatus).toHaveBeenCalledWith('abc123', 'submitted', '2026-09-28');

    // A date picker reports one complete value.
    fireEvent.change(await screen.findByLabelText('Submitted date'), { target: { value: '2026-09-27' } });
    await waitFor(() => expect(api.patchJob).toHaveBeenLastCalledWith('abc123', { submitted_at: '2026-09-27' }));
  });

  it('rejected, heard back and reset call the status endpoint', async () => {
    const user = userEvent.setup();
    vi.mocked(api.setStatus).mockResolvedValue(jobDetail({ status: 'in_progress', status_color: 'yellow' }));
    renderJob();
    await user.click(await screen.findByRole('button', { name: 'Rejected' }));
    expect(api.setStatus).toHaveBeenLastCalledWith('abc123', 'rejected', undefined);
    await user.click(screen.getByRole('button', { name: 'Heard back' }));
    expect(api.setStatus).toHaveBeenLastCalledWith('abc123', 'heard_back', undefined);
    await user.click(screen.getByRole('button', { name: 'Reset' }));
    expect(api.setStatus).toHaveBeenLastCalledWith('abc123', null, undefined);
  });

  it('saves notes on blur only when changed', async () => {
    const user = userEvent.setup();
    vi.mocked(api.patchJob).mockResolvedValue(jobDetail({ notes: 'Referral from Sam' }));
    renderJob();
    const notes = await screen.findByRole('textbox', { name: 'Notes' });
    await user.click(notes);
    await user.tab();
    expect(api.patchJob).not.toHaveBeenCalled();
    await user.type(notes, 'Referral from Sam');
    await user.tab();
    expect(api.patchJob).toHaveBeenCalledWith('abc123', { notes: 'Referral from Sam' });
  });

  it('saves the cover letter notes on blur, with the per-application questions as the placeholder', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getJob).mockResolvedValue(jobDetail({ cover_notes: 'Used their API' }));
    vi.mocked(api.putCoverNotes).mockResolvedValue(jobDetail({ cover_notes: 'Used their API. Referral: Sam' }));
    renderJob();
    const box = await screen.findByRole('textbox', { name: 'Why this company, referrals, anything to stress' });
    expect(box).toHaveValue('Used their API');
    expect(box).toHaveAttribute('maxlength', '2000');
    expect(box.getAttribute('placeholder')).toMatch(/drew you to this company[\s\S]*referral[\s\S]*emphasise or avoid/);
    await user.click(box);
    await user.tab();
    expect(api.putCoverNotes).not.toHaveBeenCalled();
    await user.type(box, '. Referral: Sam');
    await user.tab();
    expect(api.putCoverNotes).toHaveBeenCalledWith('abc123', 'Used their API. Referral: Sam');
    expect(await screen.findByDisplayValue('Used their API. Referral: Sam')).toBeInTheDocument();
  });
});

const saved = {
  draft_version: 1, draft_rules_version: 'r1234567',
  coverage: { covered: ['Python', 'SQL'], missing: ['PhD in statistics'], pct_required: 100, pct_preferred: 0 },
  unmet: ['PhD in statistics'],
  draft_history: [{ version: 1, at: '2026-10-15T10:00:00+00:00', rules_version: 'r1234567' }],
};

describe('JobPage Claude workbench', () => {
  const PACKET = {
    prompt: "Tailor my resume (the resume only) for the job in 'Acme'.", rules_version: 'r1234567',
    doc_url: 'https://docs.google.com/document/d/P/edit',
    resume_draft_url: 'https://docs.google.com/document/d/R/edit',
  };
  const COVER_PACKET = {
    prompt: "Write my cover letter for the job in 'Acme'.", rules_version: 'c7654321',
    doc_url: 'https://docs.google.com/document/d/CP/edit',
    cover_draft_url: 'https://docs.google.com/document/d/C/edit',
  };
  const step = async (name: 'Resume' | 'Cover letter') => within(await screen.findByRole('region', { name }));
  const apiError = (status: number, message: string, body: unknown = null) =>
    Object.assign(Object.create(api.ApiError.prototype), { status, message, body });

  it('Resume: Open in Claude copies the prompt and links the packet and the resume draft Doc; no paste box', async () => {
    const user = userEvent.setup();
    vi.mocked(api.openPacket).mockResolvedValue(PACKET);
    renderJob();
    const resume = await step('Resume');
    expect(resume.getByRole('button', { name: 'Check & format' })).toBeDisabled();
    await user.click(resume.getByRole('button', { name: 'Open in Claude' }));
    expect(api.openPacket).toHaveBeenCalledWith('abc123');
    expect(api.copyText).toHaveBeenCalledWith(PACKET.prompt);
    expect(await resume.findByRole('status')).toHaveTextContent('Copied the prompt');
    expect(resume.getByRole('status')).toHaveTextContent('rules r1234567');
    const docs = resume.getByRole('navigation', { name: 'Resume Docs' });
    expect(within(docs).getByRole('link', { name: /Packet/ })).toHaveAttribute('href', PACKET.doc_url);
    expect(within(docs).getByRole('link', { name: /Resume draft/ })).toHaveAttribute('href', PACKET.resume_draft_url);
    expect(within(docs).queryByRole('link', { name: /Cover letter/ })).toBeNull();
    expect(within(docs).getByRole('link', { name: /claude.ai/ })).toBeInTheDocument();
    await user.click(within(docs).getByRole('button', { name: 'Copied prompt' }));
    expect(api.copyText).toHaveBeenCalledTimes(2);
    expect(resume.getByRole('button', { name: 'Check & format' })).toBeEnabled();
    expect(resume.queryByRole('textbox')).toBeNull();
  });

  it('the cover letter step waits for an accepted resume, with the cover notes box above it', async () => {
    renderJob();
    const cover = await step('Cover letter');
    expect(cover.getByRole('button', { name: 'Open in Claude' })).toBeDisabled();
    expect(cover.getByRole('button', { name: 'Check & format' })).toBeDisabled();
    expect(cover.getByText(/Check & format a resume draft first/)).toBeInTheDocument();
    const notes = screen.getByRole('textbox', { name: 'Why this company, referrals, anything to stress' });
    const region = screen.getByRole('region', { name: 'Cover letter' });
    expect(notes.compareDocumentPosition(region) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole('region', { name: 'Resume' }).compareDocumentPosition(notes)
      & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('Cover letter: opens its own packet, then checks only the cover letter Doc', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getJob).mockResolvedValue(jobDetail({ ...saved, resume_draft_url: PACKET.resume_draft_url }));
    vi.mocked(api.openCoverPacket).mockResolvedValue(COVER_PACKET);
    vi.mocked(api.checkDrafts).mockResolvedValue({
      ok: true, outcome: { draft_version: 1, warnings: ["The cover letter's first sentence doesn't name Acme"],
        coverage: saved.coverage, unmet: saved.unmet },
      job: jobDetail({ ...saved, resume_draft_url: PACKET.resume_draft_url, cover_draft_url: COVER_PACKET.cover_draft_url }),
    });
    renderJob();
    const cover = await step('Cover letter');
    expect(cover.getByRole('button', { name: 'Check & format' })).toBeDisabled();
    await user.click(cover.getByRole('button', { name: 'Open in Claude' }));
    expect(api.openCoverPacket).toHaveBeenCalledWith('abc123');
    expect(api.openPacket).not.toHaveBeenCalled();
    expect(api.copyText).toHaveBeenCalledWith(COVER_PACKET.prompt);
    expect(await cover.findByRole('status')).toHaveTextContent('rules c7654321');
    const docs = cover.getByRole('navigation', { name: 'Cover letter Docs' });
    expect(within(docs).getByRole('link', { name: /Cover letter packet/ })).toHaveAttribute('href', COVER_PACKET.doc_url);
    expect(within(docs).getByRole('link', { name: /Cover letter draft/ })).toHaveAttribute('href', COVER_PACKET.cover_draft_url);
    await user.click(cover.getByRole('button', { name: 'Check & format' }));
    expect(api.checkDrafts).toHaveBeenCalledWith('abc123', 'cover');
    expect(await cover.findByText('Saved the cover letter with draft v1.')).toBeInTheDocument();
    expect(cover.getByRole('list', { name: 'Warnings' })).toHaveTextContent("doesn't name Acme");
  });

  it('a newly accepted resume clears the cover step and shows the saved letter\'s warnings', async () => {
    const user = userEvent.setup();
    const coverJob = { ...saved, resume_draft_url: PACKET.resume_draft_url, cover_draft_url: COVER_PACKET.cover_draft_url,
      cover_letter_at: '2026-10-15T11:00:00+00:00', cover_warnings: ["The cover letter's first sentence doesn't name Acme"] };
    vi.mocked(api.getJob).mockResolvedValue(jobDetail(coverJob));
    vi.mocked(api.checkDrafts)
      .mockResolvedValueOnce({ ok: true, outcome: { draft_version: 1, warnings: [], coverage: saved.coverage, unmet: saved.unmet },
        job: jobDetail({ ...coverJob, cover_warnings: [] }) })
      .mockResolvedValueOnce({ ok: true, outcome: { draft_version: 2, warnings: [], coverage: saved.coverage, unmet: saved.unmet },
        job: jobDetail({ ...coverJob, cover_warnings: [], draft_version: 2 }) });
    renderJob();
    const cover = await step('Cover letter');
    expect(cover.getByRole('list', { name: 'Warnings' })).toHaveTextContent("doesn't name Acme");
    await user.click(cover.getByRole('button', { name: 'Check & format' }));
    expect(await cover.findByText('Saved the cover letter with draft v1.')).toBeInTheDocument();
    await user.click((await step('Resume')).getByRole('button', { name: 'Check & format' }));
    expect(await screen.findByText('Saved draft v2.')).toBeInTheDocument();
    expect((await step('Cover letter')).queryByText(/Saved the cover letter/)).toBeNull();
  });

  it('a cover check that needs input lists the question and copies the fix prompt', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getJob).mockResolvedValue(jobDetail({ ...saved, cover_draft_url: COVER_PACKET.cover_draft_url }));
    vi.mocked(api.checkDrafts).mockResolvedValue({
      ok: false, errors: ['The cover letter still needs your input: why Acme?. Answer it in the chat'], warnings: [],
      fix_prompt: 'These problems were found:\n1. The cover letter still needs your input: why Acme?',
    });
    renderJob();
    const cover = await step('Cover letter');
    await user.click(cover.getByRole('button', { name: 'Check & format' }));
    const alert = await cover.findByRole('alert');
    expect(within(alert).getByRole('list', { name: 'Problems' })).toHaveTextContent('needs your input: why Acme?');
    await user.click(within(alert).getByRole('button', { name: 'Copy fix prompt' }));
    expect(api.copyText).toHaveBeenCalledWith(expect.stringContaining('why Acme?'));
  });

  it('a failed copy shows the prompt to copy by hand', async () => {
    const user = userEvent.setup();
    vi.mocked(api.openPacket).mockResolvedValue(PACKET);
    vi.mocked(api.copyText).mockRejectedValueOnce(new Error('denied'));
    renderJob();
    await user.click((await step('Resume')).getByRole('button', { name: 'Open in Claude' }));
    expect(await screen.findByRole('status')).toHaveTextContent("Couldn't copy: select the prompt below");
    expect(screen.getByRole('textbox', { name: 'Prompt' })).toHaveValue(PACKET.prompt);
  });

  it('without Drive it says to connect Drive on the Claude setup page, not an error', async () => {
    const user = userEvent.setup();
    vi.mocked(api.openPacket).mockRejectedValue(apiError(409, 'Connect Google Drive on the Claude setup page'));
    renderJob();
    await user.click((await step('Resume')).getByRole('button', { name: 'Open in Claude' }));
    const note = await screen.findByRole('status');
    expect(note).toHaveTextContent('Connect Google Drive on the Claude setup page');
    expect(within(note).getByRole('link', { name: 'Claude setup page' })).toHaveAttribute('href', '/claude-setup');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('lists Profile Docs problems from Open in Claude', async () => {
    const user = userEvent.setup();
    vi.mocked(api.openPacket).mockRejectedValue(apiError(409, 'Your Profile Docs have problems',
      { detail: 'Your Profile Docs have problems', problems: ['The Content Library Doc has no projects.'] }));
    renderJob();
    await user.click((await step('Resume')).getByRole('button', { name: 'Open in Claude' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Your Profile Docs have problems');
    expect(alert).toHaveTextContent('has no projects');
  });

  it('a failed check lists the problems and copies the fix prompt', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getJob).mockResolvedValue(jobDetail({ resume_draft_url: PACKET.resume_draft_url }));
    vi.mocked(api.checkDrafts).mockResolvedValue({
      ok: false, errors: ['Resume draft, line 5: bullet has no [slug] tags at the end'], warnings: [],
      fix_prompt: 'These problems were found:\n1. Resume draft, line 5: bullet has no [slug] tags at the end',
    });
    renderJob();
    await user.click((await step('Resume')).getByRole('button', { name: 'Check & format' }));
    expect(api.checkDrafts).toHaveBeenCalledWith('abc123', 'resume');
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByRole('list', { name: 'Problems' })).toHaveTextContent('line 5: bullet has no [slug] tags');
    await user.click(within(alert).getByRole('button', { name: 'Copy fix prompt' }));
    expect(api.copyText).toHaveBeenCalledWith(expect.stringContaining('These problems were found'));
    expect(within(alert).getByRole('button', { name: 'Copied fix prompt' })).toBeInTheDocument();
  });

  it('a passing check shows the version, files, coverage and draft history', async () => {
    const user = userEvent.setup();
    const links = {
      ...jobDetail().links, resume: 'https://drive.google.com/file/d/R/view',
      resume_docx: '/strelitzia/dashboard/api/jobs/abc123/files/resume_docx', cover_letter: 'https://drive.google.com/file/d/C/view',
    };
    vi.mocked(api.getJob).mockResolvedValue(jobDetail({ resume_draft_url: PACKET.resume_draft_url }));
    vi.mocked(api.checkDrafts).mockResolvedValue({
      ok: true, outcome: { draft_version: 1, warnings: ["Dropped to fit one page: 'x'"], coverage: saved.coverage, unmet: saved.unmet, fill_pct: 97 },
      job: jobDetail({ ...saved, links, resume_draft_url: PACKET.resume_draft_url }),
    });
    renderJob();
    await user.click((await step('Resume')).getByRole('button', { name: 'Check & format' }));
    expect(await screen.findByText('Saved draft v1. The resume fills 97% of the page.')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Warnings' })).toHaveTextContent('Dropped to fit one page');
    const files = screen.getByRole('navigation', { name: 'Files' });
    expect(within(files).getByRole('link', { name: /Resume PDF/ })).toHaveAttribute('href', links.resume);
    expect(within(files).getByRole('link', { name: /Resume DOCX/ })).toHaveAttribute('href', links.resume_docx);
    expect(within(files).getByRole('link', { name: /Cover letter PDF/ })).toHaveAttribute('href', links.cover_letter);
    const targeting = screen.getByRole('region', { name: 'Resume targeting' });
    expect(targeting).toHaveTextContent('100% of the required qualifications');
    expect(within(targeting).getByRole('list', { name: 'Not on your resume' })).toHaveTextContent('PhD in statistics');
    expect(screen.getByRole('list', { name: 'Draft history' })).toHaveTextContent('v1 · 2026-10-15 · rules r1234567');
  });

  it('links the newer local PDF when the Drive upload failed', async () => {
    vi.mocked(api.getJob).mockResolvedValue(jobDetail({
      ...saved,
      links: { ...jobDetail().links, resume: 'https://drive.google.com/file/d/OLD/view',
        resume_pdf: '/strelitzia/dashboard/api/jobs/abc123/files/resume_pdf' },
    }));
    renderJob();
    const files = await screen.findByRole('navigation', { name: 'Files' });
    expect(within(files).getByRole('link', { name: /Resume PDF/ })).toHaveAttribute('href', '/strelitzia/dashboard/api/jobs/abc123/files/resume_pdf');
  });

  it('a job without a draft shows no coverage', async () => {
    renderJob();
    await step('Resume');
    expect(screen.queryByRole('region', { name: 'Resume targeting' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Generate/ })).toBeNull();
  });
});

describe('JobPage fit breakdown', () => {
  it('shows the score, each component, the red flags and the AI summary', async () => {
    renderJob();
    const fit = await screen.findByRole('region', { name: 'Fit' });
    expect(fit).toHaveTextContent('Fit score 80/100');
    expect(fit).toHaveTextContent('Strong match on Python and SQL.');
    const items = within(fit).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Salary✓Importantup to $150,000/year meets your $100,000 minimum');
    expect(items[1]).toHaveTextContent('Work mode✗Nice to have');
    expect(items[2]).toHaveTextContent('Skills4/5Very important');
    expect(within(fit).getByRole('heading', { name: 'Red flags' })).toBeInTheDocument();
    expect(fit).toHaveTextContent('Mostly sales: quota-carrying');
    expect(screen.queryByText(/Stale assessment/)).toBeNull();
  });

  it('shows dealbreaker reasons and the stale note', async () => {
    vi.mocked(api.getJob).mockResolvedValue(jobDetail({
      assessment_stale: true, fit_flags: ['salary'], flag_reasons: ['salary below minimum ($80,000/year < $100,000)'],
    }));
    renderJob();
    expect(await screen.findByRole('list', { name: 'Flags' })).toHaveTextContent('⚠ salary below minimum');
    expect(screen.getByText(/Stale assessment/)).toBeInTheDocument();
  });

  it('Rescore polls the task, then reloads the breakdown', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    vi.mocked(api.rescore).mockResolvedValue(task('queued', { kind: 'rescore' }));
    vi.mocked(api.getTask).mockResolvedValueOnce(task('done', { kind: 'rescore' }));
    renderJob();
    await user.click(await screen.findByRole('button', { name: 'Rescore' }));
    expect(api.rescore).toHaveBeenCalledWith('abc123');
    expect(await screen.findByRole('status')).toHaveTextContent('Queued: assessment');
    expect(screen.getByRole('button', { name: 'Rescore' })).toBeDisabled();

    vi.mocked(api.getJob).mockResolvedValue(jobDetail({ fit_score: 95 }));
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(screen.getByRole('status')).toHaveTextContent('Finished assessment');
    await waitFor(() => expect(screen.getByRole('region', { name: 'Fit' })).toHaveTextContent('Fit score 95/100'));
    expect(screen.getByRole('button', { name: 'Rescore' })).toBeEnabled();
  });

  it('a budget stop shows the API message', async () => {
    const user = userEvent.setup();
    vi.mocked(api.rescore).mockRejectedValue(new Error('Monthly LLM budget reached: $5.00 spent'));
    renderJob();
    await user.click(await screen.findByRole('button', { name: 'Rescore' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Monthly LLM budget reached');
  });

  it('explains a job Claude has not assessed yet', async () => {
    vi.mocked(api.getJob).mockResolvedValue(jobDetail({ fit_assessment: null, fit_score: 60 }));
    renderJob();
    expect(await screen.findByText(/Not assessed by Claude yet/)).toBeInTheDocument();
  });
});

describe('JobPage edit and delete', () => {
  it('Edit saves only the changed fields and re-renders', async () => {
    const user = userEvent.setup();
    vi.mocked(api.patchJob).mockResolvedValue(jobDetail({ company: 'Globex', deadline: '2026-12-01', score_stale: true }));
    renderJob();
    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit job' });
    const company = within(dialog).getByLabelText('Company');
    await user.clear(company);
    await user.type(company, 'Globex');
    fireEvent.change(within(dialog).getByLabelText('Deadline'), { target: { value: '2026-12-01' } });
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(api.patchJob).toHaveBeenCalledWith('abc123', { company: 'Globex', deadline: '2026-12-01' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByText(/Globex/)).toBeInTheDocument();
    expect(screen.getByText(/You edited the title or company/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rescore' })).toBeEnabled();
  });

  it('Edit refuses an empty title and shows API errors', async () => {
    const user = userEvent.setup();
    vi.mocked(api.patchJob).mockRejectedValue(new Error('The company can\'t be empty'));
    renderJob();
    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit job' });
    await user.clear(within(dialog).getByLabelText('Title'));
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(within(dialog).getByRole('alert')).toHaveTextContent('can’t be empty');
    expect(api.patchJob).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText('Title'), 'ML Engineer');
    await user.selectOptions(within(dialog).getByLabelText('Work mode'), 'remote');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(api.patchJob).toHaveBeenCalledWith('abc123', { title: 'ML Engineer', work_mode: 'remote' });
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('The company can\'t be empty');
  });

  it('Delete job confirms by name, calls the API and goes back to the jobs list', async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    vi.mocked(api.deleteJob).mockResolvedValue({ ok: true, drive_folder: null, message: 'Deleted.' });
    render(
      <MemoryRouter initialEntries={['/jobs/abc123']}>
        <Routes>
          <Route path="/" element={<p>Jobs list</p>} />
          <Route path="/jobs/:key" element={<JobPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const button = await screen.findByRole('button', { name: 'Delete job' });
    await user.click(button);
    expect(confirm).toHaveBeenCalledWith(
      'Delete Data Scientist at Acme? Drafts, interviews and notes go too; files in Google Drive stay.');
    expect(api.deleteJob).not.toHaveBeenCalled();
    await user.click(button);
    expect(api.deleteJob).toHaveBeenCalledWith('abc123');
    expect(await screen.findByText('Jobs list')).toBeInTheDocument();
    confirm.mockRestore();
  });
});

describe('JobPage edit an untitled job', () => {
  it('saves other fields without asking for a title', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getJob).mockResolvedValue(jobDetail({ title: null }));
    vi.mocked(api.patchJob).mockResolvedValue(jobDetail({ title: null, salary: '$90k' }));
    renderJob();
    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit job' });
    await user.type(within(dialog).getByLabelText('Salary'), '$90k');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(api.patchJob).toHaveBeenCalledWith('abc123', { salary: '$90k' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});
