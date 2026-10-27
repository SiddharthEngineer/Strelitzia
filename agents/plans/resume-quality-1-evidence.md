# Plan: Resume quality 1/5: Claude judges qualifications; word matching only hints
**Status:** ❌ Not started (planned with the user 2026-10-27)
**Risk:** low (user, 2026-10-27: merge without a review wait; protected paths still get the automated review and preprod check; was review: changes the rules every draft is checked against, and the validator)
**Depends on:** —

## Goal
The packet stops telling Claude "UNEVIDENCED, do not claim" for qualifications that the library clearly backs. Today
the evidenced/unevidenced split is decided by word overlap, not by any model: a qualification sentence counts as
evidenced only when 60% of its content words appear verbatim in one project or base-resume role. On a 2026-10-27
packet for a trading-firm data role that marked 10 of 15 qualifications unevidenced, among them ones the base resume states almost word for
word, and Claude obeyed: it left them out and even dropped the candidate's only finance-domain role because it
"would read as a fixed income claim". After this plan, Claude (Opus, in the chat) assesses each qualification against
the library, the base resume and the new About me facts, and says where it stands; the app only blocks named tools
and skills that appear nowhere in the candidate's material.

## Diagnosis (why the 2026-10-27 packet was wrong)
- No stemming: "building", "maintaining" never match "Built", "maintain".
- Words a resume never uses: "programming", "communication", "mindset", "normalization", "lakehouse".
- Long sentences: one alternative list ("Data Engineer, Data Operations Engineer, Software Engineer, Site Reliability
  Engineer...") adds many content words that can't all match.
- Synonyms and domain words: corporate bonds, Treasury rates and credit spreads don't match "fixed income or credit".
- Facts that aren't resume content at all (work authorisation) can only ever be "unevidenced".
- Only the posting split into a list (`required_qualifications` etc.) comes from an LLM (Haiku, extract stage).

## Context
- `src/strelitzia/scoring/targets.py:183-204`: `evidence_map`; `:165-175` `matches`; `:20` `MAX_TERM_WORDS`.
- `src/strelitzia/scoring/workbench.py:217-231`: the Honesty rules; `:385-392` `_evidence_line`; `:419-433` the
  packet's qualification and "Not claimable" sections; `:612-615` `_coverage_warnings`.
- `src/strelitzia/scoring/validator.py:497-521` `validate_claims` (blocks unevidenced *terms* only; keep that);
  `:607-611` the letter's unevidenced check.
- Gotcha: Claude may now write to the Content Library. `pull_profile` saves nothing when a Doc has problems
  (`profile_sync.py:158-170`), so a malformed edit can't replace good data, but the packet must say to keep the format.
- Gotcha: the honesty guarantee still matters. Numbers stay checked against cited facts, and Skills items and named
  tools stay checked against the library and base resume (`validate_skills_known`, the watchlist). Only the
  sentence-level qualifications move from a gate to Claude's judgement.

## Tasks
### Task 1: Terms vs qualifications in the packet
**Runs:** unattended
**Files:** src/strelitzia/scoring/targets.py (modify), src/strelitzia/scoring/workbench.py (modify), tests/test_targets.py (modify), tests/test_workbench_packet.py (modify)
**What:** Split the packet's lists. "Tools and skills" (terms, ≤4 words): `in your material (where)` or
`not in your material: leave out of Skills and bullets`. "Qualifications" (sentences): no verdict; list them with the
word-overlap hits as "possible evidence: <slugs>" and the instruction "Assess each against the Content Library, Base
Resume and About me; write your verdict in Notes for me as claimable / partly / not, with the projects behind it."
Remove the "Not claimable (unevidenced)" heading. `matches()` gains a light stemmer (strip -ing/-ed/-s, "built"→"build")
so the hints are better; the term gate is unchanged.
**Validate:** `pytest tests/test_targets.py tests/test_workbench_packet.py -q` → a sentence target never prints
"UNEVIDENCED"; "Built and maintain" hints "building and maintaining"; an absent tool still prints "not in your material".
**Status:** ✅ 2026-10-27 (this commit)

### Task 2: Rules and checks follow
**Runs:** unattended
**Files:** src/strelitzia/scoring/workbench.py (modify), src/strelitzia/scoring/validator.py (modify), tests/test_workbench_import.py (modify)
**What:** Honesty rules: "Claim a qualification only when your assessment finds real backing; never claim a tool or
skill the packet lists as not in my material; facts like work authorisation come from About me, never the resume."
`_coverage_warnings` and the stored `unmet` use terms only. The letter check keeps blocking absent terms only.
New rules section "Working with me" (the chat is interactive; later plans add to it): "Ask me questions whenever an
answer would make the draft better, one at a time, each with your suggested answer so I can just say yes. Ask before
deciding a qualification you'd rate partly or are unsure about (for example: have you worked with X beyond project
Y?). When an answer is reusable, offer to add it to my Content Library or About me, and write it there only if I
agree, keeping the Doc's format." `PROJECT_INSTRUCTIONS` loosens "edit the Profile Docs only when I ask" to "only
when I agree" (bumps `INSTRUCTIONS_VERSION`: a manual repaste step, like M35).
**Validate:** `pytest tests/test_workbench_import.py tests/test_workbench_packet.py -q` → the rules have "Working with me"; a draft that states a qualification sentence passes; a
draft that adds an absent tool still fails.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
1. Open in Claude on a job with a long qualifications list → the packet has no "UNEVIDENCED" sentence lines; only tools truly absent from the library are flagged.
2. Claude's Notes for me give a verdict per qualification; the finance-domain role is no longer dropped for that reason.

## Decisions (user, 2026-10-27)
1. Claude's verdicts aren't checked mechanically; they show in Notes for me and the panel can review them later.
2. The chats are interactive and Claude may ask freely; reusable answers are saved to the Profile Docs with the user's OK.
