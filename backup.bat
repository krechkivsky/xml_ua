@echo off
REM Перехід до директорії, де знаходиться .bat файл
cd /d "%~dp0"

REM Створення змінної з поточною датою та часом у форматі YYYY-MM-DD HH-MM
setlocal enabledelayedexpansion
for /f "tokens=2 delims==" %%A in ('wmic os get localdatetime /value ^| find "="') do set datetime=%%A
set year=!datetime:~0,4!
set month=!datetime:~4,2!
set day=!datetime:~6,2!
set hour=!datetime:~8,2!
set minute=!datetime:~10,2!
set backup_dir=backups\!year!-!month!-!day! !hour!-!minute!

REM Створення підкаталогу
mkdir "!backup_dir!"

REM Копіювання файлів
xcopy *.py "!backup_dir!\" /Y
xcopy *.ui "!backup_dir!\" /Y
xcopy *.ini "!backup_dir!\" /Y

REM Виведення повідомлення про завершення
echo Бекап завершено.
