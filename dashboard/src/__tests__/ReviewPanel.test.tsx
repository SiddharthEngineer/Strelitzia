import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';
import ReviewPanel from '../components/ReviewPanel';
import { jobDetail } from './fixtures';
import { graded, reply, reviewDetail } from './reviewFixtures';

vi.mock('../api');

const job = jobDetail({ draft_version: 1 });

beforeEach(() => {
  vi.mocked(api.listJobReviews).mockResolvedValue([]);
  vi.mocked(api.copyText).mockResolvedValue();
});

describe('ReviewPanel', () => {
  it('is hidden until the job has a draft', () => {
    const { container } = render(<ReviewPanel job={jobDetail({ draft_version: null })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('creates a review, copies its prompt and imports two graders', async () => {
    const user = userEvent.setup();
    const created = reviewDetail();
    vi.mocked(api.createReview).mockResolvedValue(created);
    const sonnet = graded('claude-sonnet', reply('B+'));
    const gpt = graded('chatgpt', reply('C'), 'GPT-5 Thinking');
    vi.mocked(api.importReviewReply)
      .mockResolvedValueOnce({ ok: true, warnings: [], review: reviewDetail({ replies: [sonnet] }) })
      .mockResolvedValueOnce({ ok: true, warnings: ['The reply lists 2 top fixes, not 3.'],
                               review: reviewDetail({ replies: [sonnet, gpt] }) });
    render(<ReviewPanel job={job} />);

    await user.click(await screen.findByRole('button', { name: 'Get a recruiter review' }));
    expect(api.createReview).toHaveBeenCalledWith('abc123');
    expect(api.copyText).toHaveBeenCalledWith(created.prompt);
    expect(await screen.findByRole('button', { name: 'Copied prompt' })).toBeInTheDocument();
    const chats = screen.getByRole('navigation', { name: 'Chats' });
    for (const name of [/claude\.ai/, /chatgpt\.com/, /gemini\.google\.com/]) {
      expect(within(chats).getByRole('link', { name })).toHaveAttribute('target', '_blank');
    }

    await user.type(screen.getByRole('textbox', { name: 'Reply' }), 'sonnet reply');
    await user.click(screen.getByRole('button', { name: 'Import' }));
    expect(api.importReviewReply).toHaveBeenLastCalledWith('rev1', 'claude-sonnet', '', 'sonnet reply');
    expect(await screen.findByText('Imported Claude Sonnet\'s review.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Reply' })).toHaveValue('');

    await user.selectOptions(screen.getByRole('combobox', { name: 'Grader' }), 'chatgpt');
    await user.type(screen.getByRole('textbox', { name: /Model name/ }), 'GPT-5 Thinking');
    await user.type(screen.getByRole('textbox', { name: 'Reply' }), 'gpt reply');
    await user.click(screen.getByRole('button', { name: 'Import' }));
    expect(api.importReviewReply).toHaveBeenLastCalledWith('rev1', 'chatgpt', 'GPT-5 Thinking', 'gpt reply');
    expect(await screen.findByText('Imported ChatGPT (GPT-5 Thinking)\'s review.')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Warnings' })).toHaveTextContent('2 top fixes');
  });

  it('shows import errors inline for each grader', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listJobReviews).mockResolvedValue([reviewDetail()]);
    vi.mocked(api.getReview).mockResolvedValue(reviewDetail());
    vi.mocked(api.importReviewReply)
      .mockResolvedValueOnce({ ok: false, errors: ['The reply has no ```json block.'] })
      .mockResolvedValueOnce({ ok: false, errors: ['resume.criteria.polish.grade: \'E\' is not one of the grades'] });
    render(<ReviewPanel job={job} />);

    await user.type(await screen.findByRole('textbox', { name: 'Reply' }), 'no json here');
    await user.click(screen.getByRole('button', { name: 'Import' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('no ```json block');

    await user.selectOptions(screen.getByRole('combobox', { name: 'Grader' }), 'gemini');
    await user.click(screen.getByRole('button', { name: 'Import' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('not one of the grades'));
    expect(api.importReviewReply).toHaveBeenLastCalledWith('rev1', 'gemini', '', 'no json here');
    expect(screen.getByRole('textbox', { name: 'Reply' })).toHaveValue('no json here'); // kept to fix and retry
  });

  it('asks for the model name with Other', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listJobReviews).mockResolvedValue([reviewDetail()]);
    vi.mocked(api.getReview).mockResolvedValue(reviewDetail());
    render(<ReviewPanel job={job} />);
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Grader' }), 'other');
    await user.type(screen.getByRole('textbox', { name: 'Reply' }), 'a reply');
    await user.click(screen.getByRole('button', { name: 'Import' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Name the model you used.');
    expect(api.importReviewReply).not.toHaveBeenCalled();
  });

  it('says when the review is of an older draft', async () => {
    vi.mocked(api.listJobReviews).mockResolvedValue([reviewDetail({ draft_version: 3 })]);
    vi.mocked(api.getReview).mockResolvedValue(reviewDetail({ draft_version: 3 }));
    render(<ReviewPanel job={jobDetail({ draft_version: 4 })} />);
    expect(await screen.findByText(/This review is of draft v3; v4 is newer\./)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Get a new review' })).toBeInTheDocument();
  });

  it('shows why a review can\'t start', async () => {
    const user = userEvent.setup();
    vi.mocked(api.createReview).mockRejectedValue(new Error('This job has no draft to review yet.'));
    render(<ReviewPanel job={job} />);
    await user.click(await screen.findByRole('button', { name: 'Get a recruiter review' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('no draft to review yet');
  });
});
