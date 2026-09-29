---
name: harness-invoke
description: >-
  按被触发的端／仓库与目标环境，从团队 profile 定位唯一 Harness 流水线并触发，随后轮询执行状态
  直到终态（成功／失败／中止），回报 execution 句柄与结果；高环境（Staging／Prod）触发前必须人工确认，
  低环境（Test）可直接触发。当 CI/CD 环节需要触发 Harness 流水线完成构建／部署或查询执行状态时使用；
  触发词：触发流水线 / 触发 Harness / 跑流水线 / 部署到 / 查执行状态 / harness invoke / trigger pipeline。
metadata:
  agent: CI/CD Agent
---

# harness-invoke — 选流水线、触发并轮询执行状态

按被触发的端／仓库与目标环境从团队配置定位**唯一** Harness 流水线并触发，随后轮询 Execution 直到终态，回报结果。触发已有流水线、不新建、不改流水线定义；高环境部署为写操作，触发前须人工确认。

| 维度 | 说明 |
|------|------|
| 定位 | 选定唯一流水线 → 触发 → 轮询执行状态到终态 → 回报结果 |
| 输入 | 端／仓库 + 目标环境 + 分支／tag（及可选运行时变量）＋团队 Harness 配置 |
| 产出 | 触发结论 + execution 句柄（URL/ID）+ 终态结果（成功／失败／中止／超时仍运行）＋失败时的阶段级摘要 |
| 边界 | 只触发已有流水线并查状态；不新建/改流水线、不改代码、不建 tag、不判构建质量 |

## 0. Config values

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方经 profile 选择环节解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或文件不存在 → 停止，不臆测。

| 用途 | 配置键 |
|------|----|
| Harness 连接 scope | `profiles/{profile}.yaml` → `mcp.harness`（`base_url` / `org_id` / `project_id`；account 绑定在 MCP 会话/PAT，不进 profile、调用时无需传） |
| 流水线清单 | `profiles/{profile}.yaml` → `mcp.harness.pipelines`（扁平列表，每项含 `id`＝真实 pipeline identifier、`name`、定位标签：APP 用 `platform`（`ios`/`android`/`both`）＋`env`，同 platform+env 有多条时再用 `usage` 区分（如 `adhoc`/`regression`/`gold`/`testflight`）；CMS 用 `app`＋`env`） |
| 高环境清单 | `profiles/{profile}.yaml` → `mcp.harness.high_risk_envs`（列出的环境触发前须人工确认） |
| 轮询口径 | `profiles/{profile}.yaml` → `mcp.harness.poll`（`timeout_seconds` / `interval_seconds`） |

连接 scope 缺失，或按标签无法在 `pipelines` 唯一命中目标 `id` → 停止并回报（scope 缺→「需补齐 `mcp.harness`」；命中歧义→请调用方指明），不臆造流水线 identifier（否则会触发错误流水线）。

## 1. Prerequisites

| # | 条件 |
|---|------|
| 1 | 已明确被触发的目标（APP：端＋环境；CMS：应用）与分支或 tag（缺任一则先向调用方问清，不臆测） |
| 2 | 目标 pipeline `id` 能在 `mcp.harness.pipelines` 按标签唯一定位（歧义/缺失即停并要求指明或补齐） |
| 3 | Harness MCP 鉴权可用（鉴权失败则先做鉴权，仍失败则停止回报） |
| 4 | 目标环境属高风险清单时，已取得人工确认（见 S2） |

## 2. Workflow

```
- S1 定位唯一流水线（按标签在 pipelines 清单命中 id）
- S2 环境闸：高风险环境触发前须人工确认
- S3 触发流水线（传分支/tag 与运行时变量），拿到 execution 句柄
- S4 轮询执行状态到终态（按 poll 口径），完整保留阶段结果
- S5 回报：触发结论 + execution 句柄 + 终态结果（失败附阶段级摘要）
```

### S1 定位流水线

从 `mcp.harness.pipelines` 扁平清单按标签唯一命中目标项的 `id`：APP 按 `platform`（`ios`/`android`/`both`）＋`env` 匹配，若同 platform+env 命中多条（如 Android test 下有 `adhoc`/`regression`），再按 `usage` 收敛到唯一；CMS 按 `app` 匹配（部署流水线的目标环境在流水线内部选择）。仍命中多个 → 停止并请调用方指明具体流水线；命中不到 → 回报清单缺该流水线、要求补齐，不猜。连接 scope（`base_url`/`org_id`/`project_id`）一并取齐；调 MCP 时可直接用 `base_url` 拼出的 Harness UI URL 走 `url` 快捷方式让其自动抽取 org/project，account 绑定在会话/PAT、无需传。

### S2 环境闸（高环境人工确认）

目标环境在 `mcp.harness.high_risk_envs`（默认 `staging`/`prod`）内 → 触发前**必须取得人工确认**：向调用方明确将触发哪条流水线、目标环境、分支/tag 与关键变量，得到确认后才触发；未确认则停在 `waiting_user`，不触发。低环境（`test`）可直接触发。

### S3 触发

经 Harness MCP 用 S1 的 scope + pipeline `id` 触发流水线（可用 `harness_execute` 的 run 动作或 `url` 快捷方式），传入分支/tag 与运行时变量（inputs/variables 按流水线定义）。触发成功后记录 **execution 句柄**（execution id 与可点击 URL）。触发调用失败：先做一次鉴权重试；仍失败则回报并停止，不重复盲触发（避免重复触发同一部署）。

### S4 轮询到终态

按 `mcp.harness.poll` 的 `interval_seconds` 轮询该 execution 状态，直到进入终态：

| 终态 | 含义 |
|------|------|
| 成功（Success） | 流水线执行完成且成功 |
| 失败（Failed/Errored） | 执行失败——保留失败阶段/步骤名与错误摘要 |
| 中止（Aborted/Expired/Rejected） | 被中止/超时/审批拒绝等非成功终态 |

超过 `timeout_seconds` 仍未终态 → 停止轮询，回报「仍在运行」并给出 execution 句柄，交人工在 Harness 侧继续观察，**不判成败**。

### S5 回报

回报触发结论、execution 句柄（URL/ID）、终态结果；失败时附**阶段级摘要**（哪个 stage/step 失败、错误概要），不抛原始长日志。

## 3. Rules

| 规则 | 说明 |
|------|------|
| 只触发已有流水线 | 不新建、不修改流水线定义；只按清单里的 `id` 触发已有流水线 |
| 唯一定位不臆测 | 目标 `id` 必须从 `mcp.harness.pipelines` 按标签唯一命中；歧义/缺失即停，不猜流水线 |
| 高环境须人工确认 | 目标环境属 `high_risk_envs` 时触发前必须取得人工确认，否则不触发 |
| 触发幂等安全 | 触发失败先鉴权重试一次；不重复盲触发同一环境部署 |
| 轮询到终态 | 触发后轮询至终态或超时；超时回报「仍在运行」+ 句柄，不判成败 |
| 失败给阶段摘要 | 失败回报阶段级摘要，不抛原始长日志、不臆测根因 |
| 不判构建质量 | 只回报流水线执行结果；代码是否可编译/测试是否通过由相应验证环节判定 |
| 只回报不改代码 | 本环节不改代码、不建分支/tag、不写 Jira 字段 |

## 4. Quality gates

- 目标流水线 `id` 由 `mcp.harness.pipelines` 按标签唯一命中（非臆测、非歧义）
- 高环境触发前已取得人工确认（低环境可直接触发）
- 已拿到 execution 句柄（URL/ID）并可追溯
- 已轮询至终态；或超时则明确回报「仍在运行」+ 句柄，未误判成败
- 失败时含阶段级摘要（失败 stage/step + 错误概要）
- 未新建/修改流水线、未改代码

## 5. Output

```markdown
Harness 触发：{目标：端+env / app} · pipeline={id}
分支/tag：{branch_or_tag}

- **触发**：成功 / 失败（{原因}）
- **Execution**：{execution_url}（id={execution_id}）
- **结果**：✅ 成功 | ❌ 失败 | ⛔ 中止 | ⏳ 超时仍运行
- **失败阶段**（仅失败时）：{stage/step} — {错误概要}
- **下一步**：{成功→通知/进下一环境 | 失败→交开发排查 | 超时→人工在 Harness 观察}
```

## 6. Troubleshooting

| 现象 | 处理 |
|------|------|
| `mcp.harness` 连接 scope 缺失 | 停止并回报需补齐 `mcp.harness`（指明缺哪个键与 owner），不臆造流水线 |
| 按标签无法唯一命中流水线 | 命中多个 → 请调用方指明具体流水线；命中不到 → 回报清单缺该流水线、要求补齐；均不猜 |
| 目标环境属高风险清单但未取得确认 | 停在 `waiting_user`，先向人工确认再触发，不擅自触发 |
| Harness MCP 鉴权失败 | 先做鉴权；仍失败则回报鉴权/权限问题，不重复盲触发 |
| 触发调用失败 | 鉴权重试一次；仍失败回报并停止，不反复盲触发同一部署 |
| 轮询超时仍未终态 | 回报「仍在运行」+ execution 句柄，交人工在 Harness 侧观察，不判成败 |
| 流水线失败 | 回报阶段级摘要（失败 stage/step + 错误概要），交开发/DevOps 排查，不臆测根因、不自动重触发 |
| 需重跑失败流水线 | 是否重触发由人工决定；本环节不自动重跑（避免重复部署） |

## 7. Related

- Upstream：人工确认合并后的分支/tag 与目标（由 CI/CD 环节给定端/应用、环境、分支）
- Downstream：流水线成功 → 通知构建/部署结果、进入下一环境或功能测试环节；失败 → 交开发/DevOps 排查
