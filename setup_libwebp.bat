@echo off
REM Batch script to download and set up libwebp for Windows
REM Run this script: setup_libwebp.bat

echo ========================================
echo libwebp Setup Script for Windows
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
set DOWNLOAD_URL=https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.2.1-windows-x64.zip
set ZIP_FILE=%SCRIPT_DIR%libwebp.zip
set EXTRACT_DIR=%SCRIPT_DIR%libwebp_temp
set DLL_SOURCE=%EXTRACT_DIR%\bin\libwebp.dll
set DLL_DEST=%SCRIPT_DIR%libwebp.dll

echo Step 1: Downloading libwebp...
powershell -Command "Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing"
if errorlevel 1 (
    echo Download failed!
    pause
    exit /b 1
)
echo Download complete
echo.

echo Step 2: Extracting files...
powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force"
if errorlevel 1 (
    echo Extraction failed!
    pause
    exit /b 1
)
echo Extraction complete
echo.

echo Step 3: Copying libwebp.dll...
if exist "%DLL_SOURCE%" (
    copy "%DLL_SOURCE%" "%DLL_DEST%" /Y
    echo libwebp.dll copied to: %DLL_DEST%
) else (
    echo libwebp.dll not found in extracted files!
    pause
    exit /b 1
)
echo.

echo Step 4: Cleaning up...
del "%ZIP_FILE%" 2>nul
rmdir /s /q "%EXTRACT_DIR%" 2>nul
echo Cleanup complete
echo.

echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo libwebp.dll has been placed in:
echo   %DLL_DEST%
echo.
echo You can now restart your Streamlit app to use libwebp!
echo.
pause

