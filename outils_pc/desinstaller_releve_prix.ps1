# Retire le releve des prix PC Radar : arrete le programme, supprime le raccourci du
# dossier Demarrage et le mot de passe admin enregistre sur ce PC.
$lien = Join-Path ([Environment]::GetFolderPath('Startup')) 'PC Radar - releve des prix.lnk'
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
  Where-Object { $_.CommandLine -like '*releve_prix_pc.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
if (Test-Path $lien) { Remove-Item $lien -Force }
$config = Join-Path $env:LOCALAPPDATA 'PCRadar\releve.json'
if (Test-Path $config) { Remove-Item $config -Force }
Write-Host 'Releve des prix arrete et retire du demarrage de Windows.'
