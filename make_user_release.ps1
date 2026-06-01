$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$dist = Join-Path $PSScriptRoot "dist"
$package = Join-Path $dist "AI-Assignment-Assistant-user"
$zip = Join-Path $dist "AI-Assignment-Assistant-user.zip"

if (Test-Path $package) { Remove-Item -LiteralPath $package -Recurse -Force }
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
New-Item -ItemType Directory -Force -Path $package | Out-Null

$files = @(
  "app.py",
  "harness.py",
  "requirements.txt",
  "run_windows.bat",
  "run_windows.ps1",
  "README_USER.md",
  ".gitignore"
)

foreach ($file in $files) {
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination (Join-Path $package $file)
}

Compress-Archive -LiteralPath $package -DestinationPath $zip -Force
Write-Host "Created $zip"
