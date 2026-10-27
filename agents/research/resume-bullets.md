# Research: what earns a place in an experience bullet

Gathered 2026-10-27 for resume-quality-2. Evidence on recruiter behaviour comes from a few studies (interviewing.io,
Ladders, Jobscan, Enhancv); bullet-writing advice is from practitioners (Google/Bock, UT Austin, Tech Interview
Handbook, McDowell), not experiments.

## 1. Components, ranked
1. **What you built or owned, and for whom (scope).** UT Austin: *what*, *why* (impact) and *how*, where the how "is more
   than just the technical stack"; a stack-only bullet is its weak example.
   https://careerservices.cns.utexas.edu/resources/resumes/strong-bullets-technical-resumes
2. **Outcome or impact.** Google's XYZ: "Accomplished [X] as measured by [Y], by doing [Z]".
   https://www.inc.com/bill-murphy-jr/google-recruiters-say-these-5-resume-tips-including-x-y-z-formula-will-improve-your-odds-of-getting-hired-at-google.html
   McDowell: accomplishments, not responsibilities, in 1-2 lines. Tech Interview Handbook: a few strong bullets beat many
   average ones.
3. **Numbers.** Time saved, cost saved, usage (teams, users), magnitude (volume, tables, coverage); for data work also
   freshness or latency and failure or error rates. **No number:** use scope (who depends on it, how critical, cadence,
   what it replaced). Never invent a figure.
4. **Problem or stakes**, in a short clause ("so finance could close the month without manual pulls").
5. **Decisions and judgment**, one clause (why this design, what tradeoff).
6. **Collaboration**: cross-team and stakeholder work.
7. **Technologies**: support, never the point. 1-3 per bullet: the ones the posting asks for or the reader needs for
   context. Incidental libraries only when the posting lists them.

Recruiters skim (median 31 s, interviewing.io, https://interviewing.io/blog/are-recruiters-better-than-a-coin-flip-at-judging-resumes;
7.4 s first pass, Ladders) and match titles and keywords; hiring engineers read for scope, ownership and the how. A
bullet serves both: outcome and scope up front, the recognisable tool in the same sentence.

## 2. Tool names: bullets vs Skills
- 76% of recruiters filter by skill keywords (Jobscan 2025 survey, vendor data, https://www.jobscan.co/organizations/ats-ready-resumes/).
- ATS mostly ranks and searches rather than auto-rejects; recruiters want short, achievement-focused bullets and no
  keyword stuffing (Enhancv survey, https://itbrief.co.uk/story/study-reveals-ats-rarely-auto-rejects-cvs-debunks-75-myth).
- Keywords should appear in context; list them in Skills and also use some in Experience (Ladders, Tech Interview Handbook).

**Rule:** Skills holds the full keyword inventory. Bullets show a few of those keywords in use, tied to a real outcome.
A tool in a bullet is evidence; a bullet that exists to show a tool is filler.

## 3. Does this bullet earn its place? (all yes)
1. **Responsibility:** with every tool name deleted, does a meaningful responsibility or result remain?
2. **Beneficiary:** does it say or imply who relied on it or what got better?
3. **Evidence:** at least one concrete measure: a number, scale, cadence or criticality.
4. **Ownership:** is the verb about owning or delivering, not about how the code works ("reads X in chunks, writes Y")?
5. **Tool justification:** is each tool in the posting or needed for context, at most 3?
6. **Distinctness:** a different responsibility from every other bullet in the role?

## 4. Before / after (numbers illustrative)
1. Before: "Wrote the export in Python: reads MySQL in chunks with Pandas, writes each chunk to Parquet with PyArrow."
   After: "Built the nightly MySQL-to-Parquet export that feeds the analytics lake, so analysts no longer query
   production; moves ~40M rows per run in Python."
2. Before: "Created Airflow DAGs with sensors and retries for ingestion jobs." After: "Owned ingestion orchestration for
   12 vendor feeds in Airflow, adding retries and late-data alerts that cut missed morning loads from weekly to rare."
3. Before: "Used dbt to write SQL models and tests in Snowflake." After: "Rebuilt the revenue reporting layer as tested
   dbt models on Snowflake, giving finance one source of truth and catching schema breaks before dashboards refreshed."
4. Before: "Wrote a Kafka consumer in Java using Avro schemas." After: "Delivered the real-time order-event pipeline
   (Kafka, Avro) that replaced hourly batch pulls, bringing fraud-team latency from ~1 hour to under a minute."

## 5. Small-but-real technical work
- **Default: fold it in** as a clause of the responsibility it served ("..., including the MySQL-to-Parquet export").
- **Own bullet only** if it passes check 1 alone (its own user, stakes or measurable effect).
- **Omit** if its only value is the tool; the tool goes in Skills.
