import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import Scorecard, { disagree } from '../components/Scorecard';
import { graded, reply, reviewDetail } from './reviewFixtures';

describe('disagree', () => {
  it('is more than one letter band apart', () => {
    expect(disagree(['A-', 'C+'])).toBe(true);
    expect(disagree(['A-', 'B-'])).toBe(false);
    expect(disagree(['A+', 'F-', 'B'])).toBe(true);
    expect(disagree(['C'])).toBe(false);
  });
});

describe('Scorecard', () => {
  it('renders one grader', async () => {
    const user = userEvent.setup();
    render(<Scorecard review={reviewDetail({ replies: [graded('claude-sonnet', reply('B+', { polish: 'A-' }))] })} />);
    const overall = screen.getByRole('table', { name: 'Overall' });
    expect(within(overall).getByRole('row', { name: /Claude Sonnet/ })).toHaveTextContent('B+C+maybe');
    expect(screen.getByRole('list', { name: 'Top fixes' }).children).toHaveLength(3);

    const resume = screen.getByRole('table', { name: 'Resume' });
    expect(within(resume).getAllByRole('row')).toHaveLength(1 + 6 + 1); // header, six criteria, overall
    const polish = within(resume).getByRole('row', { name: /Polish/ });
    expect(within(polish).getByText('A-')).toHaveClass('grade-chip', 'grade-a');
    expect(within(resume).getByRole('row', { name: /Relevance/ }).querySelector('.grade-chip')).toHaveClass('grade-b');
    await user.click(within(polish).getByText('A-'));
    expect(within(polish).getByText('Fix for polish')).toBeVisible();
    expect(screen.getByRole('table', { name: 'Cover letter' })).toBeInTheDocument();
    expect(screen.queryByText(/graders disagree/)).toBeNull();
  });

  it('renders three graders and marks where they disagree', () => {
    render(<Scorecard review={reviewDetail({ replies: [
      graded('claude-sonnet', reply('B', { relevance: 'A-' })),
      graded('chatgpt', reply('B', { relevance: 'C+', clarity: 'A' }), 'GPT-5'),
      graded('gemini', reply('B-')),
    ] })} />);
    const resume = screen.getByRole('table', { name: 'Resume' });
    const head = within(resume).getAllByRole('columnheader').map((h) => h.textContent);
    expect(head).toEqual(['Resume', 'Claude Sonnet', 'ChatGPT (GPT-5)', 'Gemini']);
    expect(within(resume).getByRole('row', { name: /Relevance/ })).toHaveTextContent('graders disagree');
    expect(within(resume).getByRole('row', { name: /Clarity/ })).not.toHaveTextContent('graders disagree'); // A vs B
    expect(within(resume).getByRole('row', { name: /Polish/ })).not.toHaveTextContent('graders disagree');
    expect(screen.getByRole('list', { name: 'Top fixes from Gemini' })).toBeInTheDocument();
    expect(within(screen.getByRole('table', { name: 'Overall' })).getAllByRole('row')).toHaveLength(4);
  });

  it('leaves out the cover letter when no grader graded one', () => {
    render(<Scorecard review={reviewDetail({ replies: [graded('gemini', reply('B', {}, false))] })} />);
    expect(screen.queryByRole('table', { name: 'Cover letter' })).toBeNull();
  });
});
