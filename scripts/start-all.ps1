<#
.SYNOPSIS
  Lance TOUT en une commande : les 4 serveurs (MAIN + EXP, backends + frontends),
  active les moteurs (EXP = multi-strategie, MAIN = scalping) ET demarre le
  journal exporter en continu pour capturer les donnees au fil de l'eau.

.DESCRIPTION
  A lancer dans TON PowerShell (pas via l'agent) pour beneficier du reseau reel
  -> feed de donnees live. Chaque serveur tourne dans sa propre fenetre et SURVIT
  a la fermeture de cette console (runs multi-jours). Le exporter ecrit dans
  docs/journaux/ toutes les heures (snapshots + .jsonl + manifeste).

.EXAMPLE
  .\scripts\start-all.ps1
  .\scripts\start-all.ps1 -TickSeconds 60 -ExportIntervalSeconds 1800
  .\scripts\start-all.ps1 -NoKill -NoExporter
#>
param(
    [int]$TickSeconds = 60,
    [int]$ExportIntervalSeconds = 3600,
    [switch]$NoKill,
    [switch]$NoExporter
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainRepo  = "C:\Users\ilies\git\bitcoin-trading-assistant"
$ExpRepo   = "C:\Users\ilies\git\bitcoin-trading-v2-experiment"
$MainPy    = "$MainRepo\backend\venv\Scripts\python.exe"
$ExpPy     = "$ExpRepo\backend\venv\Scripts\python.exe"
$Launcher  = "$ScriptDir\launch_backend.py"

if (-not $NoKill) {
    Write-Host "[start-all] Kill python.exe / node.exe..."
    taskkill /F /IM python.exe 2>$null | Out-Null
    taskkill /F /IM node.exe   2>$null | Out-Null
    Start-Sleep -Seconds 2
}

Write-Host "[start-all] Backends (DB routee vers bitcoin_experiment / bitcoin_assistant)..."
Start-Process powershell -ArgumentList '-NoExit','-Command',"& '$ExpPy' '$Launcher' --engine exp"
Start-Process powershell -ArgumentList '-NoExit','-Command',"& '$MainPy' '$Launcher' --engine main"

Write-Host "[start-all] Frontends..."
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$ExpRepo\frontend'; `$env:VITE_API_BASE_URL='http://localhost:8001'; npx vite --port 5174 --strictPort"
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$MainRepo\frontend'; `$env:VITE_API_BASE_URL='http://localhost:8000'; npx vite --port 5173 --strictPort"

Write-Host "[start-all] Attente des backends (/health)..."
foreach ($p in 8001, 8000) {
    $ok = $false
    for ($i = 0; $i -lt 40; $i++) {
        try { Invoke-RestMethod "http://127.0.0.1:$p/health" -TimeoutSec 3 | Out-Null; $ok = $true; break }
        catch { Start-Sleep -Seconds 1 }
    }
    if ($ok) { Write-Host "  backend $p : OK" } else { Write-Warning "  backend $p : NON joignable" }
}

Write-Host "[start-all] Activation des moteurs..."
$body = @{ interval_seconds = $TickSeconds; profile = "scalping" } | ConvertTo-Json
try { Invoke-RestMethod -Method Post "http://127.0.0.1:8001/paper/engine-mode?mode=experimental" | Out-Null; Write-Host "  EXP  -> multi-strategie" } catch { Write-Warning "  EXP engine-mode: $_" }
try { Invoke-RestMethod -Method Post "http://127.0.0.1:8001/paper/autonomous/start" -ContentType "application/json" -Body $body | Out-Null; Write-Host "  EXP  -> autonomous ON ($TickSeconds s)" } catch { Write-Warning "  EXP autonomous: $_" }
try { Invoke-RestMethod -Method Post "http://127.0.0.1:8000/paper/autonomous/start" -ContentType "application/json" -Body $body | Out-Null; Write-Host "  MAIN -> autonomous ON ($TickSeconds s, scalping)" } catch { Write-Warning "  MAIN autonomous: $_" }

if (-not $NoExporter) {
    Write-Host "[start-all] Journal exporter (detache, intervalle ${ExportIntervalSeconds}s)..."
    & "$ScriptDir\start-journal-exporter.ps1" -IntervalSeconds $ExportIntervalSeconds -Detached
}

Write-Host ""
Write-Host "[start-all] TERMINE."
Write-Host "  EXP  (multi-strategie) : http://localhost:5174  (backend 8001)"
Write-Host "  MAIN (scalping)        : http://localhost:5173  (backend 8000)"
Write-Host "  Journaux captures      : $MainRepo\docs\journaux\"
Write-Host "  Verifier le feed live  : Invoke-RestMethod 'http://127.0.0.1:8001/market/price?symbol=BTC/USD'"
Write-Host "  Stopper un moteur      : Invoke-RestMethod -Method Post 'http://127.0.0.1:8001/paper/autonomous/stop'"
