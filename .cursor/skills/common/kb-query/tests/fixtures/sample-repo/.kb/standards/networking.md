---
type: Standard
title: 网络请求标准
description: 所有网络请求必须经过统一的 APIClient，带超时与重试上限，禁止在视图层直接发请求。
level: L2
enforcement: mandatory
owner: team:sample-mobile
source_class: D
status: stable
tags: [network, api]
applies_to:
  paths: ["Sources/Network/**", "Sources/Legacy/**"]
generated: { by: human:dev-a, at: 2026-09-01T10:00:00+08:00 }
verified:
  - { by: human:tl-a, at: 2026-09-02T10:00:00+08:00 }
stale_after: 2027-09-02T00:00:00+08:00
---

# Rules

1. 所有网络请求必须通过 `APIClient` 发出。
2. 每个请求必须设置超时，默认 15 秒。
3. 重试最多 2 次，且只对幂等请求重试。

# Rationale

统一入口便于埋点与降级。
