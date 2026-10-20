---
type: ADR
title: ADR-0001 新页面统一使用 SwiftUI
description: 新增页面使用 SwiftUI，存量 UIKit 页面按需迁移。
level: L2
enforcement: default
owner: team:sample-mobile
source_class: D
status: stable
overrides: [kb://enterprise/architecture/principles/ui-framework.md]
generated: { by: human:dev-a, at: 2026-06-01T10:00:00+08:00 }
---

# Context

团队已具备 SwiftUI 经验。

# Decision

新页面使用 SwiftUI；企业 UI 原则见 [UI 框架原则](kb://enterprise/architecture/principles/ui-framework.md)。

# Consequences

最低系统版本需 iOS 16。
