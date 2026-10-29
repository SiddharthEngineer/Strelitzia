import { graderLabel } from '../labels';
import type { ReviewCriterionGrade, ReviewDetail, ReviewDocGrades, ReviewReplyData } from '../types';

/** The 15 grades, best first (review.GRADES on the server). */
export const GRADES = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F+', 'F', 'F-'];
const BANDS = 'ABCDF';

/** The letter band of a grade: 0 for A ... 4 for F. */
export function band(grade: string): number {
  return BANDS.indexOf(grade.charAt(0));
}

/** Graders disagree when their grades are more than one letter band apart (A- and C+, not A- and B). */
export function disagree(grades: string[]): boolean {
  const bands = grades.map(band).filter((b) => b >= 0);
  return bands.length > 1 && Math.max(...bands) - Math.min(...bands) > 1;
}

export function GradeChip({ grade }: { grade: string | null | undefined }) {
  if (!grade) return <span className="muted">—</span>;
  const letter = BANDS.charAt(band(grade)).toLowerCase() || 'f';
  return <span className={`grade-chip grade-${letter}`}>{grade}</span>;
}

type Reply = ReviewDetail['replies'][number];
const DOCS: ['resume' | 'cover_letter', string][] = [['resume', 'Resume'], ['cover_letter', 'Cover letter']];

function Cell({ item }: { item: ReviewCriterionGrade | undefined }) {
  if (!item) return <td><GradeChip grade={null} /></td>;
  return (
    <td>
      <details className="grade-detail">
        <summary><GradeChip grade={item.grade} /></summary>
        <p><strong>Evidence:</strong> {item.evidence}</p>
        <p><strong>Fix:</strong> {item.fix}</p>
      </details>
    </td>
  );
}

function DocTable({ title, docs, replies, criteria }: {
  title: string; docs: (ReviewDocGrades | null)[]; replies: Reply[]; criteria: ReviewDetail['criteria'];
}) {
  const several = replies.length > 1;
  return (
    <div className="table-scroll">
      <table className="jobs-table scorecard-table" aria-label={title}>
        <thead>
          <tr>
            <th scope="col">{title}</th>
            {replies.map((r) => <th key={r.grader} scope="col">{graderLabel(r.grader, r.model_label)}</th>)}
          </tr>
        </thead>
        <tbody>
          {criteria.map(({ key, name }) => {
            const items = docs.map((d) => d?.criteria[key]);
            const split = several && disagree(items.flatMap((i) => (i ? [i.grade] : [])));
            return (
              <tr key={key} className={split ? 'disagree' : undefined}>
                <th scope="row">
                  {name}
                  {split && <span className="disagree-mark"> · graders disagree</span>}
                </th>
                {items.map((item, i) => <Cell key={replies[i].grader} item={item} />)}
              </tr>
            );
          })}
          <tr className="overall">
            <th scope="row">Overall</th>
            {docs.map((d, i) => <td key={replies[i].grader}><GradeChip grade={d?.overall} /></td>)}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/** A review's grades: the overall grades, verdicts and top fixes, then one table per document with a column per
 * grader (evidence and fix on expand). */
export default function Scorecard({ review }: { review: ReviewDetail }) {
  const replies = review.replies;
  if (!replies.length) return null;
  const data: ReviewReplyData[] = replies.map((r) => r.reply);
  const several = replies.length > 1;
  return (
    <section className="scorecard" aria-label="Scorecard">
      <div className="table-scroll">
        <table className="jobs-table scorecard-table" aria-label="Overall">
          <thead>
            <tr>
              <th scope="col">Grader</th><th scope="col">Resume</th><th scope="col">Cover letter</th>
              <th scope="col">Phone screen?</th>
            </tr>
          </thead>
          <tbody>
            {replies.map((r) => (
              <tr key={r.grader}>
                <th scope="row">{graderLabel(r.grader, r.model_label)}</th>
                <td><GradeChip grade={r.overall_resume} /></td>
                <td><GradeChip grade={r.overall_cover} /></td>
                <td className={`verdict verdict-${r.verdict}`}>{r.verdict}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="top-fixes">
        <h3>Top fixes</h3>
        {replies.map((r, i) => (
          <div key={r.grader}>
            {several && <p className="muted small">{graderLabel(r.grader, r.model_label)}</p>}
            <ol aria-label={several ? `Top fixes from ${graderLabel(r.grader, r.model_label)}` : 'Top fixes'}>
              {(data[i]?.top_fixes ?? []).map((f, j) => <li key={j}>{f}</li>)}
            </ol>
          </div>
        ))}
      </div>
      {DOCS.map(([doc, title]) => {
        const docs = data.map((d) => d?.[doc] ?? null);
        if (!docs.some(Boolean)) return null;
        return <DocTable key={doc} title={title} docs={docs} replies={replies} criteria={review.criteria} />;
      })}
    </section>
  );
}
