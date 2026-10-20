---
type: Module
title: 预订模块（booking）
description: >-
  负责酒店预订下单、订单确认与取消；
  入口为 BookingViewModel，核心为 BookingService。
level: L2
enforcement: default
owner: team:sample-mobile
source_class: D
status: stable
tags: [booking, reservation]
applies_to:
  paths: ["Sources/Booking/**"]
generated: { by: human:dev-a, at: 2026-08-20T10:00:00+08:00 }
verified:
  - { by: human:tl-a, at: 2026-08-21T10:00:00+08:00 }
stale_after: 2027-02-21T00:00:00+08:00
---

# 职责

| 类 | 职责 |
|---|---|
| `BookingViewModel` | 预订页状态管理 |
| `BookingService` | 调用预订接口，处理取消与重试，见 [网络请求标准](/standards/networking.md) |

# 修改指南

- 取消预订必须二次确认。
- 订单号示例使用 `ORDER-TEST-0001` 这类合成数据。
