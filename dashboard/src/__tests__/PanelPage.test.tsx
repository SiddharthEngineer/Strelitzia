import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';
import PanelPage, { pointsGrade } from '../pages/PanelPage';
import type { GraderStats, ReviewSummary } from '../types';
import { CRITERIA } from './reviewFixtures';

vi.mock('../api');

const REVIEW: ReviewSummary = {
  id: 'rev1', job_url: 'https://example.com/job/1', draft_id: 'd3', draft_version: 3, prompt_version: 'p1',
  created_at: '2026-10-28T09:00:00+00:00', job: { key: 'abc123', title: 'Data Scientist', company: 'Acme' },
  grades: [
    { grader: 'claude-sonnet', model_label: '', overall_resume: 'B+', overall_cover: 'C', verdict: 'maybe',
      created_at: '2026-10-28T09:10:00+00:00' },
    { grader: 'chatgpt', model_label: 'GPT-5', overall_resume: 'A-', overall_cover: null, verdict: 'yes',
      created_at: '2026-10-28T09:20:00+00:00' },
  ],
};

function stats(extra: Partial<GraderStats>): GraderStats {
  return {
    grader: 'claude-sonnet', model_labels: [], reviews: 2,
    mean: Object.fromEntries(CRITERIA.map(({ key }) => [key, 10])), mean_overall: { resume: 10, cover_letter: 7 },
    verdict_agreement: 0.5, bias: 0, spread: 2, tendency: 'balanced', ...extra,
  };
}

const renderPage = () => render(<MemoryRouter><PanelPage /></MemoryRouter>);

beforeEach(() => {
  vi.mocked(api.listReviews).mockResolvedValue([REVIEW]);
  vi.mocked(api.getGraderComparison).mockResolvedValue({ reviews: 2, criteria: CRITERIA, graders: [
    stats({ grader: 'claude-sonnet', model_labels: ['Sonnet 4.5'] }),
    stats({ grader: 'chatgpt', bias: -2.3, tendency: 'harsh', verdict_agreement: 1, mean: { relevance: 4.6 } }),
    stats({ grader: 'gemini', bias: 0.2, spread: 0.4, tendency: 'narrow' }),
  ] });
});

describe('pointsGrade', () => {
  it('rounds mean points to the nearest grade', () => {
    expect(pointsGrade(14)).toBe('A+');
    expect(pointsGrade(10.4)).toBe('B');
    expect(pointsGrade(0)).toBe('F-');
    expect(pointsGrade(null)).toBeNull();
  });
});

describe('PanelPage', () => {
  it('lists reviews with each grader\'s overall grades, linking to the job', async () => {
    renderPage();
    const table = await screen.findByRole('table', { name: 'Reviews' });
    expect(within(table).getByRole('link', { name: 'Data Scientist' })).toHaveAttribute('href', '/jobs/abc123');
    const row = within(table).getAllByRole('row')[1];
    expect(row).toHaveTextContent('v3');
    expect(row).toHaveTextContent('Claude Sonnet: B+ · C · maybe');
    expect(row).toHaveTextContent('ChatGPT (GPT-5): A- · — · yes');
  });

  it('compares the graders', async () => {
    renderPage();
    const table = await screen.findByRole('table', { name: 'Graders' });
    const [, sonnet, gpt, gemini] = within(table).getAllByRole('row');
    expect(sonnet).toHaveTextContent('Sonnet 4.5');
    expect(within(sonnet).getAllByText('B')).toHaveLength(7); // six criteria and the resume overall
    expect(gpt).toHaveTextContent('100%');
    expect(gpt).toHaveTextContent('Harsh (−2.3 vs the others)');
    expect(within(gpt).getByText('D+')).toHaveClass('grade-d'); // relevance 4.6 points
    expect(gemini).toHaveTextContent('Narrow');
  });

  it('explains how to compare graders before there are any', async () => {
    vi.mocked(api.listReviews).mockResolvedValue([]);
    vi.mocked(api.getGraderComparison).mockResolvedValue({ reviews: 0, criteria: CRITERIA, graders: [] });
    renderPage();
    expect(await screen.findByText(/No reviews yet/)).toBeInTheDocument();
    expect(screen.getByText(/two or more models/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('shows a load error', async () => {
    vi.mocked(api.listReviews).mockRejectedValue(new Error('boom'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
  });
});
