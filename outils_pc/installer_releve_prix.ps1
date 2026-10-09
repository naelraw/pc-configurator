# Installe le releve des prix PC Radar au demarrage de Windows (session de l'utilisateur,
# sans droits administrateur) : mot de passe admin enregistre une fois, raccourci dans le
# dossier Demarrage, programme lance tout de suite sans fenetre.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'releve_prix_pc.py'
$pyw = (Get-Command pythonw.exe -All -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notlike '*WindowsApps*' } | Select-Object -First 1).Source
if (-not $pyw) { Write-Host 'Python est introuvable sur ce PC : installe-le depuis python.org puis relance.'; exit 1 }
$py = Join-Path (Split-Path $pyw) 'python.exe'

# Arrete un releve deja en cours (reinstallation).
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
  Where-Object { $_.CommandLine -like '*releve_prix_pc.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$env:PYTHONIOENCODING = 'utf-8'
& $py $script --configurer
if ($LASTEXITCODE -ne 0) { Write-Host 'Installation annulee.'; exit 1 }

$lien = Join-Path ([Environment]::GetFolderPath('Startup')) 'PC Radar - releve des prix.lnk'
$raccourci = (New-Object -ComObject WScript.Shell).CreateShortcut($lien)
$raccourci.TargetPath = $pyw
$raccourci.Arguments = '"' + $script + '"'
$raccourci.WorkingDirectory = $PSScriptRoot
$raccourci.Save()

Start-Process -FilePath $pyw -ArgumentList ('"' + $script + '"') -WorkingDirectory $PSScriptRoot
Write-Host ''
Write-Host 'Installe : le releve des prix tourne maintenant en arriere-plan,'
Write-Host 'et redemarrera tout seul a chaque demarrage du PC.'
Write-Host ('Journal : ' + (Join-Path $env:LOCALAPPDATA 'PCRadar\releve.log'))
