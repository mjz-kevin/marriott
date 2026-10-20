# Branch naming and multi-person rules

Aligned with the team Branching Strategy (Confluence DBU4 / Branching Strategy): a Feature looks like `{JIRA-KEY}-Xxx-Xxx`; AI output is further wrapped in `code.branch.prefix`, isolated from human branches.

## Naming

Render `code.branch.template` (default `{prefix}/{story_key}-{slug}`):

| Segment | Rule | Example |
|----|------|----|
| `{prefix}` | From `code.branch.prefix`, i.e. the AI namespace | `feat-ai` |
| `{story_key}` | The Jira Story key, keeping the original case; lowercase it only if the template requires lowercase | `GCD-404` |
| `{slug}` | The product/feature theme, **2–3 Title-Case words**, joined by `-`. Taken from the summary's core object, not the whole summary sentence | `Mby-Audio` |

Full-name example: `feat-ai/GCD-404-Mby-Audio`.

Forbidden:

- Slugifying the whole Story summary (too long, doesn't fit `{KEY}-Xxx-Xxx`)
- An all-lowercase long kebab (`deliver-cms-content-model-and-publishing-workflow`)
- Omitting `{prefix}` (collides with the human Feature `GCD-404-Mby-Audio`)
- Omitting `{story_key}` (the uniqueness scan relies on it)

`{slug}` selection: prefer the proper/product name (MBY → `Mby`), then add one or two feature words (`Audio` / `Page` / `Cms`). Don't pile up verb phrases (Deliver / Implement / Add).

## Multiple people

The documented model: one Feature branch per person / per feature; deleted after merging into the baseline. When an Epic spans Sprints, pull a Feature from `epic/` again and merge it back into the Epic when done. This skill creates only the one **Story-level** AI branch.

| Scenario | Approach |
|------|------|
| Different Stories, different people in parallel | Each opens its own `feat-ai/{story_key}-{slug}`, not occupying each other |
| Multiple people changing the same Story together | **Share** the one this skill maintains; each pulls / rebases then pushes, one PR |
| The same Story needs sub-tasks split out | A human opens a separate short branch (e.g. `feat-ai/GCD-404-Schema`), merging back into the Story-level branch or baseline when done. **This skill doesn't create sub-task branches** |
| The same Story already has ≥2 AI branches | Stop, hand to the user to pick/clean up, don't guess, don't create a third |

One Story, one AI branch: on re-entry, reuse the existing `prefix` + `{story_key}` branch, don't open another one because the summary was rewritten.

## Remote vs local

| Action | Channel |
|------|------|
| Query the remote (uniqueness) | GitHub MCP (`get_branch` / `list_branches`, must page through all) |
| Query local (uniqueness) | `git for-each-ref` matching prefix + Story key (covers "created but not pushed") |
| Create the official remote ref | After the local is ready, **ask the user first**; after consent and SHA verification, `git push -u origin {branch}`; use MCP `create_branch` only when local can't push |
| Create / checkout locally | Git commands |

Forbidden: pushing without explicit consent in this turn; promoting an unverified local branch to the official remote; force-push.

"Create branch" doesn't equal consent to push. Run `git push` only after the user says "push." Pushing subsequent feature commits is also not in this skill.
