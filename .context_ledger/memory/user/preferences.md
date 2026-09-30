# User Preferences (update in place)

How the user likes things done **on this project**. Seeded from
Pre-Flight at bootstrap; grows as sessions reveal preferences —
corrections the user gives, patterns they approve, things they state
outright. This file exists so the user never has to give the same
correction twice.

## Learning rules

1. **Record preferences, not instructions.** A preference is standing:
   it would apply to future sessions ("plain-language changelog
   entries"). An instruction is one-off ("skip the tests this once") —
   it dies with the session and does not belong here.
2. **Every bullet carries provenance** — how and when it was learned:
   `(pre-flight)`, `(stated, YYYY-MM-DD)`, `(correction, YYYY-MM-DD)`,
   `(approved pattern, YYYY-MM-DD)`. An explicit statement or correction
   outranks an inferred pattern.
3. **Current-state file.** When the user changes their mind, update the
   bullet in place and refresh its provenance — don't keep the stale
   version. History lives in the session log, not here.
4. **A session instruction beats a recorded preference for that
   session.** Follow the instruction; afterwards, if it looked like a
   standing change of mind, update this file.
5. **Committed to git — keep it professional.** Working-style facts
   only. Never personal details, never opinions about people, never
   credentials.

<!-- TEMPLATE — keep these headings; add bullets under each as learned.
Format: - <preference> — <how to apply it> (provenance, YYYY-MM-DD)
## Workflow
- <e.g., push to main directly; one logical change per commit> (pre-flight)

## Communication
- <e.g., plain-language changelog, technical detail in reports> (stated, 2026-07-11)

## Code style
- <e.g., comment the why not the what; prefer DRY helpers> (correction, 2026-07-11)

## Review depth
- <e.g., fix safe issues, flag architectural ones for approval> (pre-flight)

## Risk & approvals
- <e.g., never bump a major version without flagging it; schema changes need explicit approval> (correction, 2026-07-11)
-->

## Workflow

- Drop a bad session's commits instead of stacking revert commits on top — reset to the last good commit when the commits are still local-only, so they cannot be pushed by accident later; use a revert commit only for history that already reached the remote. (stated, 2026-09-26 — "we are reverting to the session before Alex", after a session deleted the product package and committed `.env` as a tracked backup)

## Communication

- Say exactly what was and was not read or checked; a failed tool read is reported as failed, never as done. An overstated "I read all of it" is the quickest way to lose trust. (correction, 2026-09-30 — four times in one session)
- Short progress lines while working; lead the final report with what changed and what is still unverified. (correction, 2026-09-30)

## Source material

- Read the owner's PDFs and images **as pictures, not as extracted text**; the decks are image-only anyway. How: `docs/sources/HOW-TO-READ-THE-MATERIAL.md`. (stated, 2026-09-30 — "take the pdfs as screenshots and actually read them not texts")
- The owner's files live in `~/Desktop/Trading/` and `~/Desktop/DAILY_TRADING_CONCEPTS.zip`; the owner generated the decks themselves. Do not commit the PDFs; describe them page by page in `docs/sources/`. (stated, 2026-09-30)
- The engine should imitate how a person sees and interprets the chart; look at a rendered chart (`clicktrader smc-chart`) before and after changing detection. (stated, 2026-09-30)

## Code style

## Review depth

- When a session is opened to verify or fix something, do all of it in phases, record an ADR for the decision, and do not stop to ask whether to continue. (correction, 2026-09-30 — "why ask, I initiated this session especially for this")
- Verifying someone's work means opening their sources, not reading their summary. (correction, 2026-09-30)

## Risk & approvals
