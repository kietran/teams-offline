$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
npm --prefix frontend run build
& .venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\teams_offline_archive.spec
Copy-Item README.md "dist\Teams Offline Archive\README.md"
Compress-Archive -Force -Path "dist\Teams Offline Archive" -DestinationPath "dist\TeamsOfflineArchive-windows-x64.zip"
Write-Output "dist\TeamsOfflineArchive-windows-x64.zip"
