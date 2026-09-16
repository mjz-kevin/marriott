# Pull Request 模板方案

本目录提供一套符合最佳实践的 GitHub Pull Request 模板，包含一个**通用默认模板**和一套**按场景划分的多模板方案**。

## 目录结构

```
template/PR/
├── README.md                      # 本说明文件
├── pull_request_template.md       # 默认模板（通用，所有 PR 自动加载）
└── PULL_REQUEST_TEMPLATE/         # 多模板目录（按场景选择）
    ├── feature.md                 # 新功能
    ├── bugfix.md                  # 缺陷修复
    ├── hotfix.md                  # 线上紧急修复
    ├── refactor.md                # 重构
    ├── docs.md                    # 文档
    └── release.md                 # 版本发布
```

## 如何启用

GitHub 只会识别位于仓库特定位置的模板。本目录仅作为**模板方案的存放/管理位置**，启用时需要将其复制到 GitHub 约定的位置之一：

- `.github/`（推荐）
- 仓库根目录
- `docs/`

### 方式一：单一默认模板

把默认模板放到 `.github/` 下即可，所有新建 PR 会自动带上该模板：

```bash
mkdir -p .github
cp template/PR/pull_request_template.md .github/pull_request_template.md
```

### 方式二：多模板方案（推荐给中大型/企业团队）

把多模板目录放到 `.github/` 下：

```bash
mkdir -p .github
cp template/PR/pull_request_template.md .github/pull_request_template.md
cp -R template/PR/PULL_REQUEST_TEMPLATE .github/PULL_REQUEST_TEMPLATE
```

> 说明：`.github/pull_request_template.md`（默认）与 `.github/PULL_REQUEST_TEMPLATE/`（多模板）可以共存。
> 未指定模板时使用默认模板；指定 `?template=` 时使用对应场景模板。

## 如何选择指定模板

在 PR 创建页 URL 后追加 `template` 查询参数（文件名需完全一致）：

```
https://github.com/<org>/<repo>/compare/main...my-branch?expand=1&template=feature.md
```

常用示例：

| 场景 | URL 参数 |
|------|----------|
| 新功能 | `?template=feature.md` |
| 缺陷修复 | `?template=bugfix.md` |
| 紧急修复 | `?template=hotfix.md` |
| 重构 | `?template=refactor.md` |
| 文档 | `?template=docs.md` |
| 发布 | `?template=release.md` |

也可结合 `&expand=1` 直接展开 PR 描述编辑框。

## 各模板适用场景

| 模板 | 适用场景 | 特别强调的字段 |
|------|----------|----------------|
| `pull_request_template.md` | 通用，无明确场景时 | 变更类型、自测清单、影响范围 |
| `feature.md` | 新增功能 | 设计方案、特性开关/灰度、测试覆盖 |
| `bugfix.md` | 修复缺陷 | 复现步骤、根因分析、影响用户范围、回归测试 |
| `hotfix.md` | 线上紧急止血 | 严重程度、回滚方案、线上验证、后续跟进 |
| `refactor.md` | 不改变外部行为的优化 | 行为一致性保证、风险评估 |
| `docs.md` | 文档/注释变更 | 死链检查、示例一致性 |
| `release.md` | 版本发布 | 变更清单、迁移、发布窗口、回滚 |

## 企业落地最佳实践

1. **配合 `CODEOWNERS`**：在 `.github/CODEOWNERS` 指定各模块负责人，PR 自动请求对应审查者。
2. **配合分支保护规则**：要求至少 N 个 Approve、CI 通过、所有对话已解决方可合并。
3. **强调安全项**：每个模板都包含「无敏感信息泄漏」检查项，建议同时开启 GitHub Secret Scanning。
4. **关联工单系统**：模板固定保留 Jira / Issue 关联字段，便于需求-代码-发布全链路追溯。
5. **控制清单长度**：checklist 保持在 5~7 项，避免团队无脑打勾而失去意义。
6. **破坏性变更醒目标注**：默认与 feature/release 模板均含 breaking change 区块，保护下游。
7. **模板持续演进**：将模板纳入版本管理，随团队流程迭代，避免与实际流程脱节。

## 自定义建议

- 若团队使用 GitLab，可将模板改放到 `.gitlab/merge_request_templates/` 目录，机制类似。
- 若团队节奏很快，可基于默认模板裁剪出「精简版」，只保留「做了什么 / 为什么 / 关联 Issue / 核心检查项」。
- 可按团队技术栈补充专有检查项（如前端的无障碍性、后端的接口幂等、数据的合规脱敏等）。
