$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
npm --prefix frontend run build
& .venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\teams_offline_archive.spec
Copy-Item README.md "dist\Teams Offline Archive\README.md"
$Smoke = Start-Process -FilePath "dist\Teams Offline Archive\Teams Offline Archive.exe" -ArgumentList "--self-test" -Wait -PassThru
if ($Smoke.ExitCode -ne 0) {
    throw "Packaged executable self-test failed with exit code $($Smoke.ExitCode)."
}
Compress-Archive -Force -Path "dist\Teams Offline Archive" -DestinationPath "dist\TeamsOfflineArchive-windows-x64.zip"
Write-Output "dist\TeamsOfflineArchive-windows-x64.zip"
