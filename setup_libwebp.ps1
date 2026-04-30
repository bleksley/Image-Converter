# PowerShell script to download and set up libwebp for Windows
# Run this script from PowerShell: .\setup_libwebp.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "libwebp Setup Script for Windows" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$downloadUrl = "https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.2.1-windows-x64.zip"
$zipFile = Join-Path $scriptDir "libwebp.zip"
$extractDir = Join-Path $scriptDir "libwebp_temp"
$dllSource = Join-Path $extractDir "bin\libwebp.dll"
$dllDest = Join-Path $scriptDir "libwebp.dll"

Write-Host "Step 1: Downloading libwebp..." -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $zipFile -UseBasicParsing
    Write-Host "✓ Download complete" -ForegroundColor Green
} catch {
    Write-Host "✗ Download failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 2: Extracting files..." -ForegroundColor Yellow
try {
    Expand-Archive -Path $zipFile -DestinationPath $extractDir -Force
    Write-Host "✓ Extraction complete" -ForegroundColor Green
} catch {
    Write-Host "✗ Extraction failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 3: Copying libwebp.dll..." -ForegroundColor Yellow
if (Test-Path $dllSource) {
    try {
        Copy-Item -Path $dllSource -Destination $dllDest -Force
        Write-Host "✓ libwebp.dll copied to: $dllDest" -ForegroundColor Green
    } catch {
        Write-Host "✗ Copy failed: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✗ libwebp.dll not found in extracted files" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 4: Cleaning up..." -ForegroundColor Yellow
try {
    Remove-Item -Path $zipFile -Force
    Remove-Item -Path $extractDir -Recurse -Force
    Write-Host "✓ Cleanup complete" -ForegroundColor Green
} catch {
    Write-Host "⚠ Cleanup had issues (this is okay): $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "libwebp.dll has been placed in:" -ForegroundColor White
Write-Host "  $dllDest" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now restart your Streamlit app to use libwebp!" -ForegroundColor White
Write-Host ""

