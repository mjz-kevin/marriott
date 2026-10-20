---
type: Waiver
title: 豁免：旧版网络层暂不设置统一超时
description: Legacy 网络层在迁移完成前豁免网络请求标准第 2 条。
level: L2
enforcement: informative
owner: team:sample-mobile
source_class: D
status: stable
waives: kb://repo-sample-app/standards/networking.md
waived_rules: [2]
waives_version: 2026-09-01T10:00:00+08:00
applies_to:
  paths: ["Sources/Legacy/**"]
generated: { by: human:dev-a, at: 2026-09-10T10:00:00+08:00 }
verified:
  - { by: human:tl-a, at: 2026-09-11T10:00:00+08:00 }
stale_after: 2027-01-31T00:00:00+08:00
---

# Scope

仅 `Sources/Legacy/**`，仅第 2 条。
