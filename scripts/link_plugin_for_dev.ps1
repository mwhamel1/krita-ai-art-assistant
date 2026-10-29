# Link this repo into Krita's user plugin folder so Krita loads one copy of the files.
# Run from anywhere. Close and restart Krita after running, then enable the plugin.

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$packageName = "ai_art_assistant"
$desktopName = "ai_art_assistant.desktop"
$pykrita = Join-Path $env:APPDATA "krita\pykrita"

if (-not (Test-Path $pykrita)) {
    New-Item -ItemType Directory -Path $pykrita | Out-Null
}

function Remove-LinkOrRefuse([string]$Path, [bool]$ExpectDirectory) {
    if (-not (Test-Path $Path)) {
        return
    }
    $item = Get-Item $Path -Force
    $isReparse = ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    if ($ExpectDirectory -and $item.PSIsContainer) {
        if ($isReparse) {
            cmd /c "rmdir `"$Path`"" | Out-Null
            return
        }
        throw "A real folder already exists at $Path. Move it aside and re-run this script."
    }
    if (-not $item.PSIsContainer) {
        Remove-Item $Path -Force
        return
    }
    throw "Unexpected item at $Path"
}

$packageSrc = Join-Path $repoRoot $packageName
$packageDst = Join-Path $pykrita $packageName
$desktopSrc = Join-Path $repoRoot $desktopName
$desktopDst = Join-Path $pykrita $desktopName

if (-not (Test-Path $packageSrc)) {
    throw "Plugin folder not found: $packageSrc"
}
if (-not (Test-Path $desktopSrc)) {
    throw "Desktop file not found: $desktopSrc"
}

Remove-LinkOrRefuse $packageDst $true
cmd /c "mklink /J `"$packageDst`" `"$packageSrc`""
if ($LASTEXITCODE -ne 0) {
    throw "Could not create folder link for $packageName"
}

Remove-LinkOrRefuse $desktopDst $false
cmd /c "mklink /H `"$desktopDst`" `"$desktopSrc`""
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $desktopDst)) {
    cmd /c "mklink `"$desktopDst`" `"$desktopSrc`""
}
if (-not (Test-Path $desktopDst)) {
    Copy-Item $desktopSrc $desktopDst -Force
    Write-Warning "Copied the .desktop file instead of linking it. Re-run this script if that file changes."
}

Write-Host "Linked plugin into:"
Write-Host "  $packageDst"
Write-Host "  $desktopDst"
Write-Host ""
Write-Host "Next: restart Krita, then Settings > Configure Krita > Python Plugin Manager > enable AI Art Assistant, then restart Krita again."