# Research: writing a cover letter (early/mid-career software and data engineers, US, 2025-26)

Gathered 2026-10-27 for the resume-quality plans. It is the source for the cover-letter rules, the About me
questionnaire and the review rubric. Sources are listed at the end of each section. Statistics from vendor surveys
(for example "67% of recruiters can spot AI letters") could not be traced to a primary study, so don't quote them.

The sources agree on these points: letters are often skimmed or skipped at big companies. When someone does read one,
a short, specific letter with real stories wins, and a generic one is worse than none. At smaller or specialised shops,
the reader is often the hiring engineer, so specific stories and personality pay off more.

## 1. Structure
- **Length:** 250-350 words, never more than a page.
- **P1, the hook (2-3 sentences):** the role, plus a *specific* reason this team and this work appeal to you, tied to one
  fact about the candidate. If someone referred them, name the referrer here.
- **P2, the main story (~120 words):** one concrete episode that maps onto the posting's core responsibility. Cover the
  situation, what *I* did and decided, the result, and why it matters to this team.
- **P3, a second story or the "why me" bridge (~70 words):** a shorter second story that covers a different
  requirement, or a work habit backed by evidence. This paragraph also holds context such as a career change.
- **P4, the close (2 sentences):** fit in one line, what they want to work on next, and thanks. No filler.
  Mention work authorisation only if the posting raises it.
- **Salutation:** "Dear Hiring Team" is fine.

Sources: https://capd.mit.edu/resources/how-to-write-an-effective-cover-letter/ ·
https://www.techinterview.org/post/3233474628/cover-letters-engineers/ ·
https://grad.illinois.edu/professional-development/applying-jobs/cover-letters

## 2. Great letters vs bad ones
- Every source names the same top mistake: **restating the resume.** The letter supplies what a resume can't: why the
  candidate made a decision, how they reason, what they care about, how they behave when things break.
- A letter that lists tasks and tools ("I used pyarrow to...") is a resume in prose. **Choose 1-2 stories, not 6 facts.**
- **Story selection:** rank projects by overlap with the posting's 2-3 *core responsibilities*, not its tool list.
- **Technical detail:** 1-2 named technologies per story, only where they carry meaning. Lead with the problem, the stakes
  and the judgment call. One number per story is enough. A concrete *decision*, such as choosing not to build something,
  signals seniority better than a list of tools.

Sources: https://www.askamanager.org/2018/05/how-to-write-a-great-cover-letter.html ·
https://news.ycombinator.com/item?id=1783915 · https://www.lilachbullock.com/cover-letter-software-engineer-role/

## 3. Motivation, why this company, goals
- Motivation is **causal and personal**, not adjectival: the moment or experience that produced the interest, not
  "passionate about data".
- **Why this company:** one specific thing (a product, an engineering blog post, the team's scope in the posting, the
  firm's market, a conversation with an employee), connected to the candidate's own goal. No copied website text, no
  generic praise of "the mission".
- **Career goal:** one sentence on what they want to get deeper at.
- **Why this industry:** the candidate supplies the reason; the LLM must never invent it.

Sources: https://careers.northeastern.edu/blog/2025/01/21/how-to-use-chatgpt-to-write-a-cover-letter-that-sounds-like-you/ ·
https://grad.illinois.edu/professional-development/applying-jobs/cover-letters

## 4. Tone and voice
- First person, plain verbs, mixed sentence lengths; sounds like the candidate talking to an engineer. Confidence comes
  from specifics. Credit others where it's true.
- **Banned phrases:** "I am writing to express my interest", "I'm excited to apply for", "esteemed organization",
  "passionate", "proven track record", "detail-oriented", "hard worker", "great problem solver", "results-driven",
  "dynamic", "leverage", "synergy", "delve", "tapestry", "fast-paced environment", "I am confident that",
  "I would welcome the opportunity", "unique blend of", "not only X but also Y", "In today's data-driven world".
- **Banned patterns:** triplets of adjectives, dash-heavy rhythm, every paragraph opening with "I", a closing summary
  that repeats the letter, rhetorical questions, a different tool name in every sentence.

Sources: https://www.career.msstate.edu/blog/2025/10/01/how-recruiters-actually-read-cover-letters/ ·
https://www.metaintro.com/blog/cover-letter-with-ai-that-sounds-like-you · https://news.ycombinator.com/item?id=1783915

## 5. Questionnaire (the About me Profile Doc)
**Answered once (R):**
1. How did you get into engineering or data? A specific moment, not a summary.
2. What kind of problem makes you lose track of time? One example.
3. The piece of work you're proudest of, and the hard *decision* in it.
4. A time something broke in production or the data was wrong. What did you do?
5. What would a former manager or teammate say you're unusually good at? Real feedback if you have it.
6. What do you want to be much better at in 2-3 years?
7. What kind of team and environment brings out your best work?
8. Why these industries or domains? Up to 3, with a true reason for each.
9. Values or working habits you care about, with an example of each.
10. A non-work interest or side project worth mentioning (only if relevant or memorable).
11. Anything a reader might misread on your resume (gap, short tenure, field change), with one line of context.
12. Constraints: work authorisation or sponsorship, relocation, location or remote, start date.
13. Three phrases you'd never say, plus a short sample of your own writing as a voice reference.

**Per application (P):**
14. What specifically drew you to this company or team? Something concrete you read, used or heard.
15. Do you know anyone there, or have a referral?
16. Which 1-2 of your projects fit best, and why? (Optional; overrides the automatic pick.)
17. Anything to emphasise or avoid for this application?

## 6. Rules for the LLM
- Use only facts from the About me Doc, the content library, the base resume and the posting. Never invent motivation,
  metrics or company facts.
- 250-350 words in 4 paragraphs.
- 1-2 stories mapped to the posting's top responsibilities: problem, action, result, relevance; at most 2 named tools each.
- One specific reason for this company, from the per-application answers.
- Plain first person, in the candidate's voice sample. Vary how sentences open.
- Don't restate the resume, list technologies or describe small tasks. No banned phrase or pattern.
- No salary. Work authorisation only if the posting raises it.
- If a needed input is missing (why this company, say), write `[NEEDS INPUT: ...]` instead of inventing it.

## 7. Review rubric
1. **Hook:** could the first sentence go into another company's letter? Then it fails.
2. **Stories:** at most 2, each with a stake, a decision and a result.
3. **Resume test:** more than 30% restates resume bullets? Fails.
4. **Tool density:** any sentence that exists mainly to name a tool?
5. **Specific why:** at least one concrete company or team detail, linked to the candidate's goal.
6. **Voice:** no banned phrases; reads naturally aloud.
7. **Accuracy:** every claim traces to the inputs.
8. **Length and close:** 250-350 words; the close looks forward and isn't filler.
