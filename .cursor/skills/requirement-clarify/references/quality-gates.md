# Quality Gates

Authoring skills pass G1–G6 before delivery; publishing skills pass G7–G8 before writing.

## G1 Structural Completeness

The product must cover all **required sections** of the template. Optional sections/items not involved keep the heading and write `—` (or "Not applicable this cycle") but must not be deleted entirely, otherwise the reader can't tell "not done" from "forgot to write."

Decision: missing any required section → block.

## G2 Placeholder Zeroing

Scan for residual placeholders; a hit blocks:

| Pattern | Description |
|---------|-------------|
| `[Enter name]` `[Description]` `[Role]` `TBD` `TODO` `???` | Unfilled content |
| `…` appearing in an AC | AC not finished |
| A section heading directly followed by the next section heading | Empty section |

Exception: an optional section/item not involved may use `—` as a checklist trace ("assessed, not needed this cycle"); items the template itself requires to be left empty (like the "Glossary" and "Appendix links") may also use `—`. These `—` marks are not treated as unfilled residue, but must be logged in the to-confirm list in the delivery conversation when they represent a pending decision.

## G3 Synthetic Data and PII

- Example data in PRD / User Story / test cases must be **synthetic data**, not reused production values
- Interface examples and test data in tech solutions must be **mock**; real secrets, internal domains, member IDs, and order IDs are forbidden
- Before writing out, scan for real secrets, internal domains, member IDs, order IDs, and phone numbers; a hit blocks the submission

Decision: hit → block; no "warn and continue."

## G4 Acceptance-Criteria Testability

Each AC must satisfy all of:

| Check | Anti-pattern | Correct |
|-------|--------------|---------|
| Has a clear precondition | "The user can view" | "GIVEN the user is logged in and the account has 1 valid order" |
| Has an observable result | "Smooth experience" | "THEN the order list renders within 1 second" |
| No vague words | "normal" / "reasonable" / "friendly" / "fast" | Replace with quantifiable or decidable descriptions |
| Mappable to test cases | An AC that can't yield any test step | An AC maps to 1–N cases |
| Covers exceptions and boundaries | Only the happy path | At least 1 exception AC + 1 boundary AC |

Decision: any AC unqualified → send that AC back for rewrite; doesn't block the whole.

## G5 Terminology Consistency

The same concept can have only one name throughout. Scan before producing:

- Role names (member / user / guest) unified
- State names (published / live / Published) unified
- Field names consistent with code / interface definitions

Inconsistency → warning; list a comparison table for the author to decide.

## G6 Human-Confirmation Gate

The following products **must stop and wait for human confirmation after delivery** and must not auto-flow into the publishing step:

| Product | Confirmer |
|---------|-----------|
| PRD | PO |
| PRD-level tech solution | TL (write-back to the PRD appendix link needs no PO sign-off) |
| Spike conclusion | TL |
| Story-level detailed solution | DEV |
| User Story list | PO |

## G7 Idempotency

Before publishing to Confluence, dedup by title CQL; before creating a Jira ticket, dedup by "Parent + Summary."
On a hit with an existing object → update (Confluence) / skip and prompt (Jira); **creating duplicate objects is forbidden**.

## G8 Sensitive-Information Scan

Before writing out, scan for real secrets, internal domains, member IDs, order IDs, and phone numbers; on a hit, terminate the write and report the location and type of the hit to the user; do not mask and auto-continue.
