---
description: A description of your rule
---

# QGIS 4 & Qt6 / PyQt6 Migration Rules

You are working on a QGIS Python plugin migrating from QGIS 3 (Qt5) to QGIS 4 (Qt6).
When generating or refactoring code, always enforce these rules:

1. **Imports & Exec:**
   - Prefer `from qgis.PyQt import QtCore, QtGui, QtWidgets` over direct `PyQt6` imports.
   - `exec_()` is removed. Use `exec()` for QDialog and QApplication.

2. **Qt6 Fully Qualified Enums:**
   - Unscoped enums are removed in Qt6. All Qt enums MUST be fully qualified.
   - Example: Use `Qt.AlignmentFlag.AlignLeft` instead of `Qt.AlignLeft`.
   - Example: Use `QFileDialog.Option.ExistingFile` instead of `QFileDialog.ExistingFile`.

3. **Type Handling & Layouts:**
   - `QVariant` type enums (e.g., `QVariant.String`) are removed. Use native Python types (`str`, `int`, `float`).
   - `QLayout.setMargin()` is removed. Use `setContentsMargins(l, t, r, b)`.

4. **PyQGIS API:**
   - Ensure metadata compatibility with QGIS 4 (qgisMinimumVersion=4.0).