# Research: how a recruiter reviews one application (criteria for the recruiter panel)

Written 2026-10-29 for `recruiter-panel-1-review`. It is the source for the criteria and the grade scale in
`scoring/review.py`. It builds on `cover-letter.md`, `resume-bullets.md` and `resume-sections.md` (same audience:
early/mid-career software and data engineers, US) and doesn't repeat them. As there, vendor-survey percentages that
can't be traced to a primary study are left out.

## 1. How an application gets screened
- **The first scan (6-10 seconds).** Eye-tracking studies of recruiters (TheLadders, 2012 and 2018) found an initial
  look of roughly 6-7 seconds per resume, spent on the current and previous titles and companies, dates, education and
  the top of the page. The decision in that window is "read on or reject", so the fit has to be visible at the top,
  in titles, the headline and the first bullets of the recent role.
- **The ATS match.** Most mid-size and large employers keep applications in an applicant-tracking system. Recruiters
  search and filter it by the posting's terms (skills, tools, titles), and some systems rank applicants against the
  posting. Required qualifications written in the posting's own words, backed by work, are what gets found; a skills
  list with no work behind it reads as keyword stuffing once a person looks.
- **The hiring-manager read.** Past the screen, the hiring manager (often an engineer) reads for evidence: what the
  candidate built or decided, at what scale, with what result. Vague bullets ("worked on various projects") and
  inflated claims cost more here than missing keywords.
- **The cover letter.** Often skipped at large companies; when read, it is read for *why this team* and one or two
  real stories. A generic letter is worse than none (`cover-letter.md` §2).

Sources: TheLadders eye-tracking study (2012) and its 2018 update · `cover-letter.md`, `resume-bullets.md`,
`resume-sections.md` and the sources listed there.

## 2. AI-text tells a recruiter notices
- Stock phrases: "I am excited to apply", "proven track record", "passionate about leveraging", "fast-paced
  environment", "delve", "tapestry", "spearheaded" on every bullet.
- Rule-of-three lists and parallel triplets everywhere ("scalable, reliable, and efficient").
- Buzzword stacks with no object ("drove cross-functional synergy"), em-dash-heavy rhythm, every sentence the same length.
- Claims with no specifics: no system, number, team or decision a person could ask about in an interview.
- A letter that could be sent to any company by swapping the name.

## 3. Criteria and scale
Each criterion is graded separately for the resume and for the cover letter, on a 15-step scale
A+ A A- B+ B B- C+ C C- D+ D D- F+ F F- (A+ = 14 points ... F- = 0, for averages). Every grade comes with evidence
(quoted from the document) and one concrete fix.

1. **Relevance**: the posting's required and preferred qualifications are shown (quote the evidence; partial counts).
2. **Evidence**: claims are backed by concrete work, scope and results; nothing inferred or inflated.
3. **Human tone**: reads as written by the candidate; no AI tells (stock phrases, rule-of-three lists, buzzwords).
4. **Specificity**: written for this company and role, not a template (weighs most for the cover letter).
5. **Clarity**: a recruiter sees the fit in 10 seconds; scannable, no filler.
6. **Polish**: grammar, consistency, length (one page; cover letter under ~350 words).

Plus an **overall** grade per document and a **verdict**: phone screen yes / maybe / no, with the top three fixes.

## Decisions
1. (User, 2026-10-27) Signed off as listed: the six criteria above (Relevance, Evidence, Human tone, Specificity,
   Clarity, Polish), each graded separately for the resume and the cover letter, plus an overall grade per document
   and a verdict (phone screen yes / maybe / no) with the top three fixes. Unchanged from the plan.
2. The grader plays a recruiter hiring for the job, and the job description is the hiring criteria, so the same
   prompt works in Claude, ChatGPT or Gemini without a project or files.
