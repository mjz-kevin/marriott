# Stack pack — Swift / iOS (APP · ios-dragon-app)

Loaded by `code-review-rules` when the APP profile's `review.rules_source.swift` lists this file (`kind: bundled`). Adds iOS-specific items to the generic lenses in `../review-lenses.md`. Cite items as `swift-ios §N.M`.

> Source: the APP iOS (Money) team's `pr-review` skill and the `ios-api-and-shared-components` / `pre-commit-code-review` rules. When the iOS repo commits its own rule file, switch the profile entry to `kind: repo_file` and retire this pack.

Minimum deployment target: **iOS 18**. If the repo's deployment target changes, update §1.

## 1. iOS 18+ platform APIs (lens: architecture · 🟡 by default)

| # | Rule |
|---|------|
| 1.1 | Prefer modern platform APIs: flag deprecated / legacy UIKit / SwiftUI / WebKit / Foundation APIs when an iOS 18+ replacement exists. |
| 1.2 | Flag unnecessary `#available` branches / fallback paths for versions below the minimum target. |
| 1.3 | Flag newer async / delegate APIs skipped in favor of older callback-based ones without a stated reason (e.g. `WKNavigationDelegate` async `decidePolicyFor`). |
| 1.4 | Flag Obj-C runtime / KVC workarounds (`perform(#selector)`, `value(forKey:)`, `objc_msgSend`) where a supported Swift API exists — **unless** it works around a known platform bug; then ask to isolate it in one shared helper rather than spreading it. |
| 1.5 | Do **not** flag availability-gated use of newer APIs (e.g. iOS 26-only) that legitimately needs a fallback for supported versions — but do ask to sanity-check both rendering paths when the split is user-visible (🟡 correctness). |

## 2. Swift Concurrency over GCD / blocks (lens: architecture; 🔴 when it causes a race)

| # | Rule |
|---|------|
| 2.1 | New `DispatchQueue` / `DispatchGroup` / `OperationQueue` / `performSelector` / callback chains where `async`/`await`, `Task`, `AsyncSequence` or `actor` fit → 🟡. |
| 2.2 | New `@escaping` completion handlers in new code that could be `async` functions → 🟡. |
| 2.3 | `DispatchQueue.main.async` used for flow control that `@MainActor` / structured concurrency handles → 🟡. |
| 2.4 | Blocking hops (`sync`, semaphores, `DispatchGroup.wait`) on paths that should suspend → 🟡, 🔴 if on the main thread or deadlock-prone. |
| 2.5 | `Task { }` wrapping async work without cancellation / lifetime handling (task outlives its view / owner, no `[weak self]` where needed) → 🟡, 🔴 on a proven race / crash. |
| 2.6 | **Accept** GCD / blocks when interfacing with legacy Obj-C SDKs, WebKit / UIKit callbacks without async overloads, or when migration would balloon scope unrelated to the PR — the code should state the reason in a comment; missing reason → 🟢. |

## 3. Shared components and helpers (lens: architecture · 🟡)

Shared libraries: **`Common`**, **`CommonData`**, **`CommonUI`** (under `Module/ios-dragon-library-common*/`).

| # | Rule |
|---|------|
| 3.1 | A new utility method / extension / helper / ViewModifier must not duplicate an existing one. **Search before flagging** (e.g. `nilIfEmpty()`, `isBlank()` live in `Common/Utilities/String+Utils.swift`) and cite the existing `path:line`. |
| 3.2 | The same or near-identical helper in two modules → reuse the shared one; if the shared libraries don't have it yet, suggest extracting it into the right shared library. |
| 3.3 | An existing shared helper that *almost* fits → suggest extending it (keeping its current behavior) instead of adding a parallel helper. |
| 3.4 | A UI component / helper reused from another **feature** module → suggest moving it into a shared library first. Moving cross-module code needs the author's / team's agreement — phrase it as a suggestion, never 🔴. |
| 3.5 | Missed reuse of existing abstractions: text styles, environment keys, shared ViewModifiers, formatters, design tokens. |
| 3.6 | Redundant modifiers on top of a style that already sets them (e.g. `.fontWeight(.medium)` on a `.labelExtraSmall` that is already Medium — may synthesize a heavier weight) → 🟢 / 🟡. |

## 4. Search commands (PR head checkout)

Run on the PR head (`git fetch origin pull/{n}/head:pr-{n}-review`), read-only:

```bash
# legacy concurrency
git grep -n 'DispatchQueue\|dispatch_async\|@escaping\|OperationQueue\|performSelector\|DispatchGroup\|NotificationCenter\.default\.addObserver' pr-{n}-review -- '*.swift'
# availability / runtime workarounds
git grep -n '#available\|@objc\|perform(#selector\|value(forKey\|objc_msgSend' pr-{n}-review -- '*.swift'
# does a helper with this name / purpose already exist?
git grep -n 'func <name>\|extension String' pr-{n}-review -- 'Module/ios-dragon-library-common*/**/*.swift'
```

Without a local checkout use GitHub MCP `search_code` (`repo:{owner/name} <symbol>`) and `get_file_contents` with `ref = head SHA`.

## 5. Pre-existing code

Flag these patterns **only in lines the PR adds or changes**; existing GCD / legacy APIs in untouched code are out of scope (at most one 🟢 "consider a follow-up" note when the PR extends them substantially).
