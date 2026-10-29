# Review lenses — correctness · readability · architecture (diff-scoped)

The checklist `code-review-rules` S2 applies to every change hunk, on top of the team standards (`review.rules_source`) and the built-in security baseline. Stack-specific packs (e.g. `stack-rules/swift-ios.md`) add items per language; this file is stack-neutral.

> Origin: generalized from the APP iOS (Money) team's proven `pr-review` skill and its `pre-commit-code-review` / `ios-api-and-shared-components` rules.

## 1. Questions to ask for every meaningful change

1. **What breaks if this is wrong?** (correctness, blast radius)
2. **Is there an existing pattern / component / helper in this repo that should be reused?** (architecture — needs a search, see §4)
3. **Can the same outcome be achieved with less scope** — a smaller diff or a narrower blast radius? (architecture)
4. **Is this a root-cause fix or a local workaround?** (architecture)
5. **Would the next reader understand this in one pass?** (readability)
6. Stack pack questions (e.g. "is there a modern platform API / concurrency primitive that replaces this?").

Read the **changed file around the hunk and its call sites / tests** before raising anything above 🟢 — not just the diff lines.

## 2. The three lenses

### 2.1 Correctness (does it do the right thing safely?)

| Check | Typical finding |
|------|------|
| Logic | Wrong condition / off-by-one / inverted flag / unhandled enum case / wrong default |
| Concurrency & lifetime | Race, shared mutable state, missing cancellation, retain cycle, work after dealloc |
| Crash / data | Force unwrap / unchecked cast / index out of range on external data; data loss or corruption |
| Failure handling | Silent fallback that hides a failure; swallowed error on a critical path; missing error state |
| Behavior change | Breaking API / behavior change without migration; feature-flag default flipped |
| Blast radius | Global / cross-module change (typography, navigation, auth, feature flags, networking, shared UI) without evidence the other call sites were checked |
| Tests | Risky behavior with no test (not style-only diffs) |

### 2.2 Readability (can the next person maintain it?)

| Check | Typical finding |
|------|------|
| Control flow | Nested `if/else` that flattens after one early `guard` / return; arrow code |
| Repetition | The same optional / value checked repeatedly across branches; the same ID trimmed / validated several times instead of once and reused |
| Size | A function / view body doing several things; long parameter lists; a boolean-flag parameter switching behavior |
| Intent | Magic numbers / strings without a named constant; misleading or overly generic names (`data`, `tmp`, `handle2`) |
| Noise | Dead code, commented-out code, debug prints / test hooks left in, redundant modifiers or casts |
| Comments | Comments that restate the code instead of explaining *why*; a non-obvious workaround with no comment |

Example — prefer one early guard and flattened branching:

```swift
// before: propertyId trimmed / checked in every branch, nested if-let inside if/else
// after: validate once, then one flat condition (behavior unchanged — every
// "add" path received a nil payment anyway)
let propertyId = dataStore.propertyId.trimmingCharacters(in: .whitespacesAndNewlines)
guard !propertyId.isEmpty else { return }
if dataStore.guestCustomerId != nil, state.payment != nil {
    navigation.push(Destination.selectPaymentMethod)
} else {
    navigation.push(Destination.addPaymentMethod(propertyId: propertyId, payment: nil))
}
```

### 2.3 Architecture — diff-scoped design (is it built the right way *here*?)

| Check | Typical finding |
|------|------|
| Reuse | Reinvents a component / modifier / helper / formatter / extension that already exists (cite its path) |
| Layer & module | Business logic in a View / Controller; shared UI or a generic helper placed inside one feature module; a feature module reaching into another feature module |
| Duplication across modules | The same or near-identical helper now exists in two modules → reuse the shared one, or propose extracting to the shared library |
| Extend vs add | An existing helper almost does it → extend it (keeping its old behavior) instead of adding a parallel one |
| Root cause | Per-screen workaround patches for a problem owned by a shared component (e.g. a shared style forcing a font that every caller overrides) |
| Scope | Unrelated drive-by changes bundled into the feature PR; a "font change" PR that also changes layout |
| Consistency | Diverges from the repo's established pattern for the same thing (networking, DI, navigation, state, error mapping) or from a repo ADR / standard (`kb-query`) |
| Contract | Deviates from the tech solution's interface / data contract (review-level flag; field-level is `contract-diff`) |

## 3. Out of scope — leave to the human reviewer

Not ruled by this skill (mention at most as one 🟢 "for the human reviewer" note, never a gate):

- Business / product reasonableness, UX and visual-design decisions (skip token / visual debates when the user says the design is confirmed — still flag technical risks such as clipping, cross-OS rendering paths, layout regressions).
- **System-level** architecture direction: new services / modules, tech or library selection, module splits, anything that would re-open the tech solution or needs STB / ARB.
- Rewriting existing code the PR doesn't touch ("wander into historical code").

## 4. Evidence required (no taste-based findings)

| Lens | Minimum evidence before the finding is kept |
|------|------|
| Correctness 🔴 | The concrete failure path (input → line → effect) |
| Reuse / duplication | The existing implementation's `path:line` found by a search (`git grep` / `rg` on the PR head checkout, else GitHub MCP `search_code`) |
| Layer / consistency | The repo pattern it deviates from (`path` of 1–2 existing examples) or the KID of the repo standard / ADR (`kb-query`) |
| Root cause | The shared component that owns the problem and at least one other affected caller |
| Readability | The lines themselves (the rewrite in the fix suggestion is the evidence) |

No evidence → drop it or keep it as 🟢 with "unverified" in the root cause.

## 5. Level calibration per lens

| Lens | Default | 🔴 only when |
|------|------|------|
| Security | 🔴 | (per the security baseline) |
| Correctness | 🔴 for crash / data loss / wrong user-visible behavior / build break; else 🟡 | — |
| Architecture | 🟡 | It **also** has a correctness / security consequence (e.g. a cross-module change with an unchecked regression path), **or** it violates an explicit written rule (team standard / stack pack "must" / accepted ADR) |
| Readability | 🟢 (🟡 when it hides a likely bug or makes a risky path hard to verify) | Never 🔴 |

When in doubt, pick the lower level and say why — the reviewer can raise it at the confirmation step.

## 6. Comment style

1–2 short, concrete, actionable sentences; name the thing and the fix.

| Lens | Good |
|------|------|
| Architecture · root cause | "`BoxShadowGroupBoxStyle` forces `.bodySmall` on all content, so nested `textStyle` calls can clip. Consider making that default opt-in instead of per-screen workarounds." |
| Architecture · reuse | "`String.nilIfEmpty()` already exists in `Common/Utilities/String+Utils.swift`; reuse it instead of the new `emptyToNil()`." |
| Architecture · scope | "This changes Segment layout, not just fonts. Please confirm all Segment usages were checked." |
| Readability | "`propertyId` is trimmed and checked in three branches — trim once with an early `guard` and reuse it." |
| Correctness | "Typography uses `lineHeight(.exact)` on iOS 26+ but `lineSpacing` on older OS. Please sanity-check key screens on both paths." |

Bad (vague): "This could be problematic and might cause issues in some cases. Maybe reconsider the approach."
