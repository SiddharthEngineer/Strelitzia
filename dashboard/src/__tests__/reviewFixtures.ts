import type { ReviewDetail, ReviewGrader, ReviewReplyData } from '../types';

export const CRITERIA = [
  { key: 'relevance', name: 'Relevance' }, { key: 'evidence', name: 'Evidence' },
  { key: 'human_tone', name: 'Human tone' }, { key: 'specificity', name: 'Specificity' },
  { key: 'clarity', name: 'Clarity' }, { key: 'polish', name: 'Polish' },
];

/** A grader's reply: every criterion `grade` unless overridden. */
export function reply(grade = 'B', overrides: Record<string, string> = {}, cover = true): ReviewReplyData {
  const doc = (overall: string) => ({
    overall,
    criteria: Object.fromEntries(CRITERIA.map(({ key }) => [key, {
      grade: overrides[key] ?? grade, evidence: `Evidence for ${key}`, fix: `Fix for ${key}`,
    }])),
  });
  return {
    review: 1, prompt_version: 'p1', resume: doc(grade), cover_letter: cover ? doc('C+') : null, verdict: 'maybe',
    top_fixes: ['Lead with payments', 'Cut the Interests section', 'Name the Terraform module'],
  };
}

export function graded(grader: ReviewGrader, data: ReviewReplyData, model_label = '') {
  return {
    grader, model_label, overall_resume: data.resume.overall, overall_cover: data.cover_letter?.overall ?? null,
    verdict: data.verdict, created_at: '2026-10-28T10:00:00+00:00', reply: data,
  };
}

export function reviewDetail(extra: Partial<ReviewDetail> = {}): ReviewDetail {
  return {
    id: 'rev1', job_url: 'https://example.com/job/1', draft_id: 'd1', draft_version: 1, prompt_version: 'p1',
    created_at: '2026-10-28T09:00:00+00:00', job: { key: 'abc123', title: 'Data Scientist', company: 'Acme' },
    grades: [], current_prompt_version: 'p1', criteria: CRITERIA, prompt: 'You are a recruiter hiring for…',
    replies: [], ...extra,
  };
}
