@echo off
chcp 65001 > nul

:: Встановіть правильний шлях до вашої інсталяції QGIS
:: також треба відредагувати ./.vscode/settings.json
set "QGIS_ROOT=D:\Program Files\QGIS 3.28.3"

echo [+] Setting up QGIS environment...

:: Завантажуємо змінні середовища QGIS
call "%QGIS_ROOT%\o4w_env.bat"

echo [+] Starting Visual Studio Code...

:: Запускаємо VS Code в поточній директорії
code .
