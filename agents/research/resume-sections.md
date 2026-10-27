# Research: headline, summary and bullets on a one-page engineering resume (1-4 years, US)

Gathered 2026-10-27 for the resume-quality plans. Sources are listed inline.

## 1. Headline vs summary vs none
**Verdict: neither by default.** Name and contact line, then Experience. Add **one 1-2 line Summary** only when a
trigger applies. Never a keyword-list headline, never an objective.

- Against: techinterview.org says the top third is too valuable for taglines or summaries below staff level; open with
  the current role and its strongest bullets
  (https://www.techinterview.org/post/3233474602/software-engineer-resume-guide/).
- Optional: FAANG Tech Leads keeps a summary for career breaks, domain switches or title mismatches
  (https://www.faangtechleads.com/resume/professional-summary).
- For: Tech Interview Handbook allows a summary under 50 words that starts with the role noun
  (https://github.com/yangshun/tech-interview-handbook, resume.md).
- Eye-tracking (Ladders 2018, weak evidence): ~7.4 s first skim, mostly titles, companies, dates
  (https://www.hrdive.com/news/eye-tracking-study-shows-recruiters-look-at-resumes-for-7-seconds/541582/).

**Summary triggers:** the current title doesn't match the target role (e.g. "Data Scientist" applying for data
engineering), a domain switch, a gap, a relocation or authorisation note that helps, or the page is ~3 lines short.

**A good summary:** 1-2 lines, 25-50 words: role noun + years, one specialization that matches the posting, one proof
point (scale, outcome or domain). No adjectives about yourself, no tool list.
- Good: "Data Engineer with 3 years building batch and streaming pipelines for fintech risk teams. Owns ingestion for
  40+ sources feeding daily regulatory reports."
- Bad: "Data Engineer | Python | Spark | Delta Lake | Airflow | AWS" (keyword stuffing, repeats Skills).
- Bad: "Passionate, detail-oriented engineer seeking a challenging role to leverage my skills in..." (objective, fluff).

## 2. Bullet rules
1. Lead with ownership and outcome, not tools: action + scope + result (Google's XYZ; MIT CAPD's PAR,
   https://capd.mit.edu/resources/career-toolkit-crafting-an-effective-resume/).
2. Strong verb first; present tense for the current role. No "Responsible for", "Helped", "Worked on".
3. Describe what you owned and changed, not tasks. Bad: "Wrote pandas scripts to clean CSVs." Good: "Owned ingestion
   for 12 vendor feeds; cut daily load failures from ~5/week to <1/month."
4. Quantify where honest; otherwise give scope (who used it, how critical).
5. Libraries go in Skills. Platform names (Spark, Airflow, Kafka, AWS) are fine inline, at most 1-2 per bullet;
   low-level libraries (pandas, pyarrow, requests) only in Skills unless the library *is* the achievement. Every
   technology the posting asks for must appear somewhere in plain text, which Skills satisfies
   (https://www.techinterview.org/post/3233474612/skills-section-engineering-resume/).
6. One idea per bullet, one line ideally, two at most; no 1-3 word widow on the second line.
7. Order by relevance; the first bullet of the current role is the most-read line on the page.
8. No soft-skill claims; show collaboration through scope ("with 3 product teams").
9. Nothing you can't discuss in depth in an interview.

## 3. Page fill (US letter, 0.5" margins, ~10pt)
- Published: 3-6 bullets per role, recent roles get more; Skills 4-6 lines.
- Working budget (layout arithmetic, not a published figure): ~95-110 characters per full line, ~48-55 lines per page.
  Most recent role 4-6 bullets, earlier role 3-4, third role or internship 2-3; ~10-14 bullets in all.
- Short by 2-4 lines: a bullet on the top role, or a one-line summary. Over: cut the oldest role's bullets first,
  shorten two-line bullets.
