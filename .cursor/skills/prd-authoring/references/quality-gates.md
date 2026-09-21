# Quality Gates

Authoring skills pass G1–G7 and G11 before delivery; publishing skills pass G8–G11 before writing.

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
| `faithful to the official template` `enforced by quality gates` `not written into the template` | Skill/template notes for the author written into the PRD |
| The body's H1 is `PRD Template` | Treating the template file name as the product title |

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

The AI may give suggestions and defaults, but the confirmation action must be done by a human.

## G7 Idempotency

Before publishing to Confluence, dedup by title CQL; before creating a Jira ticket, dedup by "Parent + Summary."
On a hit with an existing object → update (Confluence) / skip and prompt (Jira); **creating duplicate objects is forbidden**.

## G8 Permission Boundary

| Action | Allowed step | Description |
|--------|--------------|-------------|
| Confluence writes | Requirement authoring/publishing, tech-solution authoring/publishing steps | R+W |
| Jira ticket creation and field writes | Ticket-creation step | R+W |
| Jira status transitions and comments | Restricted | No field restructuring or deletion |

## G9 Diagram Renderability

For any product containing a mermaid diagram (architecture, flowchart, sequence, etc.), verify item by item before delivery; any failure → send that diagram back for correction:

| Check | Anti-pattern | Correct |
|-------|--------------|---------|
| Double-quote node text | `A[MBY Audio H5 Page]` | `A["MBY Audio H5 Page"]` |
| Forbid HTML line-break tags | `C["Module<br/>note"]` | `C["Module (note)"]` |
| Quote edge labels | `E -->|select chapter| F` | `E -->|"select chapter"| F` |
| ASCII node IDs | `甲["Member"]` | `A["Member"]` |
| Syntactically renderable | Delivered without verification | Confirmed no Lexical error via a mermaid previewer / live |

**Publishing side**: if Confluence has no Mermaid rendering plugin, writing a raw mermaid code macro may only show the source. The publishing step must render diagrams into image attachments and embed them, not relying on a site plugin.
