import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../api';
import Flower from '../components/Flower';
import { GRADES, GradeChip } from '../components/Scorecard';
import { day, graderLabel } from '../labels';
import type { GraderComparison, GraderStats, GraderTendency, ReviewSummary } from '../types';

const TENDENCY_LABELS: Record<GraderTendency, string> = {
  harsh: 'Harsh',
  lenient: 'Lenient',
  narrow: 'Narrow: nearly one grade for everything',
  balanced: 'Balanced',
};

/** Mean grade points (A+ = 14 ... F- = 0) as the nearest grade. */
export function pointsGrade(points: number | null | undefined): string | null {
  if (points === null || points === undefined) return null;
  return GRADES[GRADES.length - 1 - Math.round(points)] ?? null;
}

const pct = (v: number | null) => (v === null ? '–' : `${Math.round(v * 100)}%`);
const signed = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}`;

function tendency(g: GraderStats): string {
  if (!g.tendency) return '–';
  const label = TENDENCY_LABELS[g.tendency];
  return g.bias === null ? label : `${label} (${signed(g.bias)} vs the others)`;
}

function Reviews({ reviews }: { reviews: ReviewSummary[] }) {
  if (!reviews.length) {
    return <p className="muted">No reviews yet. Open a job with a draft and press Get a recruiter review.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="jobs-table" aria-label="Reviews">
        <thead>
          <tr><th>Job</th><th>Date</th><th>Draft</th><th>Grades (resume · cover letter · phone screen?)</th></tr>
        </thead>
        <tbody>
          {reviews.map((r) => (
            <tr key={r.id}>
              <td>
                {r.job?.key
                  ? <Link to={`/jobs/${encodeURIComponent(r.job.key)}`}>{r.job.title || '(untitled)'}</Link>
                  : <span className="muted">(deleted job)</span>}
                {r.job && <span className="muted"> · {r.job.company}</span>}
              </td>
              <td>{day(r.created_at)}</td>
              <td>{r.draft_version != null ? `v${r.draft_version}` : '–'}</td>
              <td>
                {r.grades.length ? (
                  <ul className="panel-grades">
                    {r.grades.map((g) => (
                      <li key={g.grader}>
                        {graderLabel(g.grader, g.model_label)}: <GradeChip grade={g.overall_resume} />
                        {' · '}<GradeChip grade={g.overall_cover} />{' · '}{g.verdict}
                      </li>
                    ))}
                  </ul>
                ) : <span className="muted">Not graded yet</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Graders({ comparison }: { comparison: GraderComparison }) {
  if (!comparison.graders.length) {
    return (
      <p className="muted">
        Paste the same review into two or more models (say Claude Sonnet, ChatGPT and Gemini) to compare how they
        grade.
      </p>
    );
  }
  return (
    <>
      <p className="muted small">
        From {comparison.reviews} review{comparison.reviews === 1 ? '' : 's'} with two or more graders: each grader's
        mean grade per criterion (resume and cover letter together), how often its verdict matched another grader's,
        and whether it grades harsher or more leniently than the others.
      </p>
      <div className="table-scroll">
        <table className="jobs-table" aria-label="Graders">
          <thead>
            <tr>
              <th>Grader</th><th>Reviews</th>
              {comparison.criteria.map((c) => <th key={c.key}>{c.name}</th>)}
              <th>Resume overall</th><th>Cover letter overall</th><th>Verdict agrees</th><th>Tendency</th>
            </tr>
          </thead>
          <tbody>
            {comparison.graders.map((g) => (
              <tr key={g.grader}>
                <th scope="row">
                  {graderLabel(g.grader)}
                  {g.model_labels.length > 0 && <div className="muted small">{g.model_labels.join(', ')}</div>}
                </th>
                <td>{g.reviews}</td>
                {comparison.criteria.map((c) => <td key={c.key}><GradeChip grade={pointsGrade(g.mean[c.key])} /></td>)}
                <td><GradeChip grade={pointsGrade(g.mean_overall.resume)} /></td>
                <td><GradeChip grade={pointsGrade(g.mean_overall.cover_letter)} /></td>
                <td>{pct(g.verdict_agreement)}</td>
                <td title={g.spread === null ? undefined : `Spread: ${g.spread.toFixed(1)} points`}>{tendency(g)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** Panel: every recruiter review, and how the graders (models) compare. */
export default function PanelPage() {
  const [reviews, setReviews] = useState<ReviewSummary[] | null>(null);
  const [comparison, setComparison] = useState<GraderComparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    Promise.all([api.listReviews(ctrl.signal), api.getGraderComparison(ctrl.signal)])
      .then(([list, graders]) => {
        setReviews(list);
        setComparison(graders);
      })
      .catch((err) => {
        if (!ctrl.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      });
    return () => ctrl.abort();
  }, []);

  if (error) return <p className="notice error" role="alert">Couldn't load the panel: {error}</p>;
  if (!reviews || !comparison) {
    return <div className="loader-state" aria-live="polite" aria-busy="true"><Flower variant="loader" size={64} />Loading…</div>;
  }
  return (
    <article className="panel-page">
      <h1>Panel</h1>
      <p className="muted">
        Recruiter reviews of your drafts, graded by any chat model. Start one from a job's page.
      </p>
      <section className="card" aria-labelledby="panel-reviews">
        <h2 id="panel-reviews">Reviews</h2>
        <Reviews reviews={reviews} />
      </section>
      <section className="card" aria-labelledby="panel-graders">
        <h2 id="panel-graders">Graders</h2>
        <Graders comparison={comparison} />
      </section>
    </article>
  );
}
