---
type: Pitfall
title: 预订日期按设备时区解析导致跨日
description: 入住日期是酒店当地日期，不能按设备时区转换。
level: L2
enforcement: default
owner: team:sample-mobile
source_class: B
status: stable
tags: [booking, date]
generated: { by: kb-summarizer/x.y, at: 2025-12-01T10:00:00+08:00 }
verified:
  - { by: human:tl-a, at: 2025-12-02T10:00:00+08:00 }
stale_after: 2026-08-01T00:00:00+08:00
---

# 规避方式

入住日期用 `yyyy-MM-dd` 字符串传递，不转 Date。
