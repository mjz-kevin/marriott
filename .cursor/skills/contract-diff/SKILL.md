---
name: contract-diff
description: >-
  Compare the interface implementation in the code against the interface definition in the Story-level
  detailed tech solution field by field (field name / type / nullability / default value / error code /
  failure fallback), flagging deviations such as missing, extra, type mismatch, and nullability
  mismatch. Use when the verification step needs to confirm whether the implementation conforms to the
  solution's interface contract;
  triggers: contract diff / contract check / 接口契约检查 / 契约比对 / 接口比对 / 接口方案检查.
metadata:
  agent: Verification Agent
---

# contract-diff — field-by-field comparison of implementation vs solution interfaces

Using the detailed tech solution's interface definitions as the contract baseline, compare the interface implementation in the code field by field and flag every deviation. The solution is the baseline; an implementation deviating from the solution is an issue (unless the solution itself has been confirmed to change).

| Dimension | Description |
|------|------|
| Purpose | Compare the implementation interfaces vs the solution interface definitions field by field and flag deviations |
| Input | The code's interface implementation + the detailed tech solution's interface-definition sections + the team contract spec |
| Output | A per-interface, per-field deviation list (missing / extra / type mismatch / nullability mismatch / default-value mismatch / error-code mismatch / missing fallback) |
| Scope | Only does contract comparison and ruling; doesn't change code or the solution |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| Contract-baseline source | `profiles/{profile}.yaml` → `code.contract.source` (default `tech_solution_detail`, i.e. the interface-definition sections of the Story-level detailed solution) |
| Comparison granularity | `profiles/{profile}.yaml` → `code.contract.match` (`field_level` = field by field) |

Required config keys missing (TBD) → stop and ask for them.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The detailed tech solution's interface-definition sections exist (the contract baseline); if missing, comparison can't be done — stop and report |
| 2 | The implementation code is already on the Feature branch, so the corresponding interface implementation can be located |
| 3 | The build has passed (field-level comparison is unreliable when compilation fails; fix the build first) |

## 2. Workflow

```
- S1 Extract the interface-contract list from the detailed solution (per interface, per field)
- S2 Extract the actual fields of the corresponding interface from the code (per language difference; if it can't be reliably extracted, mark it pending human confirmation)
- S3 Compare field by field, flagging the deviation type
- S4 Aggregate the deviation list and rule pass or fail
- S5 Report the conclusion: pass → proceed / fail → send back to the development step
```

### S1 Extract the contract baseline

Extract from the detailed solution's interface definitions, for each interface: the request / trigger timing, field name, type, nullability, default value, error code, and null / failure-fallback strategy. The solution's mock examples are reference only; the contract follows the field-definition table.

### S2 Extract the corresponding fields from the implementation (per language difference)

The comparison targets are "the solution's interface definition vs the corresponding DTO / model definition in the implementation"; the extraction method differs by language:

| Language | Contract carrier | Extraction method |
|------|------|------|
| TypeScript | `interface` / `type` / zod schema, etc. | Read the type definition statically, reliable at field level |
| payload collection (CMS) | the `fields` definition of a payload `CollectionConfig` | Read the collection's field name / type / required / defaultValue, compare field by field against the solution's interface definition |
| Swift | `Codable` struct / networking-layer model | Read the struct properties and `CodingKeys`, which may be scattered across files |
| Kotlin | `data class` / serialization annotations | Read the properties and `@SerializedName`/`@Json` annotations |

Fields may be scattered across multiple files, so locate the model for that interface first, then compare field by field. **When an interface's implementation fields can't be reliably extracted statically (e.g. dynamic parsing, hand-written JSON, multi-layer wrapping), don't guess, don't misjudge it as a deviation; mark it a "pending human confirmation" item for a human to check.**

### S3 Compare field by field

For each field of each interface, rule the deviation type:

| Deviation type | Meaning |
|------|------|
| Missing | The solution has it, the implementation doesn't |
| Extra | The implementation has it, the solution doesn't define it (needs confirmation whether it's over-implementation) |
| Type mismatch | The field type doesn't match the solution |
| Nullability mismatch | Nullability doesn't match the solution (solution non-null but implementation nullable, or vice versa) |
| Default-value mismatch | The default value doesn't match the solution |
| Error-code mismatch | The error-code set doesn't match the solution |
| Missing fallback | The solution specifies a null / failure fallback, the implementation doesn't implement it or fails silently |

### S4 Ruling

| Conclusion | Criteria |
|------|------|
| Pass | No deviation, or only deviations that have been confirmed and accepted |
| Fail | Any unaccepted deviation exists (missing / type / nullability / error code / missing fallback, etc.) |

An "extra" field, if it's a reasonable extension the solution doesn't cover, is marked a pending-confirmation item for a human to rule, not ruled a fail directly.

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Solution is the baseline | The contract follows the solution's interface definitions; an implementation deviation is an issue, unless the solution has been confirmed to change |
| Field by field | Compare field by field per the `code.contract.match` spec, don't stop at the interface-name level |
| Always check the fallback | The null / failure fallback is part of the contract; a missing or silently-failing implementation is ruled a deviation |
| Rule only, don't change | Only compare and rule; don't change the implementation or the solution |
| Stop if the solution is missing | With no interface-definition baseline, don't invent a contract; stop and report |
| Fall back when extraction fails | When implementation fields can't be reliably extracted statically, mark "pending human confirmation", don't guess or misjudge as a deviation |
| Respect the retry limit | The self-loop carries a retry limit; past the limit, prompt for human intervention |

## 4. Quality gates

- The contract baseline comes from the config-declared source (the detailed solution's interface definitions), not invented
- Every field of every interface was compared (name / type / nullability / default / error code / fallback)
- The deviation list flags the deviation type and the interface / field it's in
- "Extra" fields are handed to a human as pending-confirmation items, not ruled a fail directly
- Give an explicit next step among "proceed / send back / prompt for human"

## 5. Output

```markdown
Interface-contract check — {Pass | Fail}

| Interface | Field | Deviation type | Solution definition | Implementation state |
|------|------|------|------|------|
| {interface} | {field} | {type} | {solution} | {implementation} |

- **Pending confirmation (extra fields)**: {list / none}
- **Conclusion**: {pass → proceed / send back to the development step / retry limit exceeded, prompt for human intervention}
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| No interface-definition baseline | Stop and report; don't invent a contract |
| Compilation hasn't passed | Fix the build first, defer field-level comparison |
| Both the solution and the implementation contain real sensitive values | Stop and report, redact and then compare |
| Repeated deviations beyond the retry limit | Prompt for human intervention, don't send back endlessly |

## 7. Related

- Upstream: build-verify (contract comparison is more reliable after the build passes)
- Downstream: pass → unit-test-runner (run the unit tests); fail → send back to the development step to fix
