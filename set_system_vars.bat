@echo off
setlocal enabledelayedexpansion

:: Check if running with admin privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running with admin privileges.
) else (
    echo This script requires admin privileges. Please run as administrator.
    pause
    exit /b 1
)

:: Get the current script directory (working directory)
set "WORKING_DIR=%~dp0"

:: Remove trailing backslash if present
if "%WORKING_DIR:~-1%"=="\" set "WORKING_DIR=%WORKING_DIR:~0,-1%"

:: Remove quotations from path, if present
set "WORKING_DIR=!WORKING_DIR:"=!"

:: --- Dynamically Determine Python Version ---
set "PYTHON_FOLDER="
set "PYTHON_VERSION="
for /d %%i in ("%WORKING_DIR%\apps\Python*") do (
    set "PYTHON_FOLDER=%%i"
    echo Found Python folder: !PYTHON_FOLDER!

    :: Extract the version using string manipulation
    set "TEMP_VERSION=%%~nxi"
    set "TEMP_VERSION=!TEMP_VERSION:Python=!"
    set "PYTHON_VERSION=!TEMP_VERSION!"
)

:: Error handling if python not found.
if not defined PYTHON_VERSION (
    echo Error: Python installation not found in "%WORKING_DIR%\apps".
    pause
    exit /b 1
)

echo Found Python version: %PYTHON_VERSION%
set "QGIS_PYTHON_DIR=%WORKING_DIR%\apps\Python%PYTHON_VERSION%"
:: --- End of Python Version Detection ---

:: Set folder to QGIS LTR
set "QGIS_BIN_DIR=%WORKING_DIR%\apps\qgis-ltr\bin"
set "QGIS_SHARE_DIR=%WORKING_DIR%\apps\qgis-ltr\share"
set "QGIS_PYTHON_LIBS_DIR=%WORKING_DIR%\apps\qgis-ltr\python"
set "QGIS_QT_PLUGIN_DIR=%WORKING_DIR%\apps\qgis-ltr\qtplugins"

:: Set environment variables
echo Setting QGIS environment variables...

:: PATH
echo   Setting PATH...
set "NEW_PATH=%QGIS_BIN_DIR%;%QGIS_PYTHON_DIR%\Scripts;%QGIS_PYTHON_DIR%;%PATH%"
setx PATH "%NEW_PATH%" /M
echo   PATH set to: %NEW_PATH%

:: PYTHONPATH
echo   Setting PYTHONPATH...
set "NEW_PYTHONPATH=%QGIS_PYTHON_LIBS_DIR%;%QGIS_PYTHON_DIR%;%QGIS_PYTHON_DIR%\Lib\site-packages"
setx PYTHONPATH "%NEW_PYTHONPATH%" /M
echo   PYTHONPATH set to: %NEW_PYTHONPATH%

:: QGIS_PREFIX_PATH
echo   Setting QGIS_PREFIX_PATH...
setx QGIS_PREFIX_PATH "%WORKING_DIR%\apps\qgis-ltr" /M
echo   QGIS_PREFIX_PATH set to: %WORKING_DIR%\apps\qgis-ltr

:: GDAL_DATA
echo   Setting GDAL_DATA...
setx GDAL_DATA "%QGIS_SHARE_DIR%\gdal" /M
echo   GDAL_DATA set to: %QGIS_SHARE_DIR%\gdal

:: QT_PLUGIN_PATH
echo   Setting QT_PLUGIN_PATH...
setx QT_PLUGIN_PATH "%QGIS_QT_PLUGIN_DIR%" /M
echo   QT_PLUGIN_PATH set to: %QGIS_QT_PLUGIN_DIR%

:: Ask for system reboot
:REBOOT_PROMPT
echo.
set /p "REBOOT_CHOICE=Do you want to reboot the system now to apply the changes? (y/n): "
if /i "%REBOOT_CHOICE%"=="y" (
    echo Rebooting the system...
    shutdown /r /t 5 /f
    exit /b 0
) else if /i "%REBOOT_CHOICE%"=="n" (
    echo The system must be restarted for the environment variables to take effect.
    echo Please restart the system manually.
    pause
    exit /b 0
) else (
    echo Invalid choice. Please enter 'y' or 'n'.
    goto REBOOT_PROMPT
)

endlocal
