---
name: fix-traceback
description: New prompt
invokable: true
---

Analyze the provided traceback/error log in the context of QGIS 4 and Qt6/PyQt6 migration.
1. Identify if the issue is caused by Qt6 API breaking changes (missing attributes, scoped enums, removed methods like exec_ or QVariant).
2. Explain the exact cause of the issue in 1-2 concise sentences.
3. Provide the refactored, fully compliant QGIS 4 / Qt6 code fix.