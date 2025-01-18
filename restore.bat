@echo off
REM Перехід до директорії, де знаходиться .bat файл
cd /d "%~dp0"

REM Перевірка наявності папки backups
if not exist backups (
    echo Папка backups не знайдена. Відновлення неможливе.
    exit
)

REM Пошук останньої створеної папки
for /f "delims=" %%F in ('dir backups /b /ad-h /o-d /t=c') do (
    set last_backup=backups\%%F
    goto found
)

:found
if not defined last_backup (
    echo Останній бекап не знайдено. Відновлення неможливе.
    exit
)

REM Відновлення файлів
xcopy "%last_backup%\*.py" . /Y >nul
xcopy "%last_backup%\*.ui" . /Y >nul
xcopy "%last_backup%\*.ini" . /Y >nul

REM Вивід повідомлення про завершення
echo Файли відновлено з папки "%last_backup%"

REM Закриття вікна після завершення
exit
