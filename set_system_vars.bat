@echo off
setlocal enabledelayedexpansion
echo ###########################################################################
echo # This script configures the environment for QGIS plugin development.     #
echo # The changes will only apply to THIS command prompt window.            #
echo ###########################################################################

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
echo.

:: PATH
echo   Adding to PATH:
echo     ^> %QGIS_BIN_DIR%
echo     ^> %QGIS_PYTHON_DIR%\Scripts
echo     ^> %QGIS_PYTHON_DIR%
set "PATH=%QGIS_BIN_DIR%;%QGIS_PYTHON_DIR%\Scripts;%QGIS_PYTHON_DIR%;%PATH%"

:: PYTHONPATH
echo.
echo   Setting PYTHONPATH:
echo     ^> %QGIS_PYTHON_LIBS_DIR%
echo     ^> %QGIS_PYTHON_DIR%\Lib\site-packages
set "PYTHONPATH=%QGIS_PYTHON_LIBS_DIR%;%QGIS_PYTHON_DIR%\Lib\site-packages"

:: QGIS_PREFIX_PATH
set "QGIS_PREFIX_PATH=%WORKING_DIR%\apps\qgis-ltr"

:: GDAL_DATA
set "GDAL_DATA=%QGIS_SHARE_DIR%\gdal"

:: QT_PLUGIN_PATH
set "QT_PLUGIN_PATH=%QGIS_QT_PLUGIN_DIR%"

echo.
echo --- Environment is ready for QGIS plugin development! ---
echo.
echo You can now use commands like 'pyrcc5', 'pyuic5', and run your tests.
echo To exit this special environment, simply close this window.

endlocal
