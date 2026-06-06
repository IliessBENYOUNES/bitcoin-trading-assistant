<#
.SYNOPSIS
  Lance TOUT en une commande : 4 serveurs (MAIN + EXP, backends + frontends), active les
  moteurs (EXP = multi-strategie, MAIN = scalping), demarre le journal exporter, et lance
  le superviseur Claude temps reel.

.DESCRIPTION
  - Ferme d'abord les fenetres/process du run PRECEDENT (par marqueur de ligne de commande),
    pour ne pas empiler des fenetres -> plus de doublons illisibles.
  - Chaque serveur tourne dans sa propre fenetre TITREE (BTC-...), persistante (runs multi-jours).
  Astuce : pour tout faire DANS IntelliJ (onglets terminal in-IDE), utiliser plutot les
  Run Configurations "BTC ..." (.idea/runConfigurations) + le compound "BTC start-all".

.EXAMPLE
  .\scripts\start-all.ps1
  .\scripts\start-all.ps1 -NoKill -NoMonitor -MonitorEffort xhigh
#>
param(
    [int]$TickSeconds = 60,
    [int]$ExportIntervalSeconds = 3600,
    [switch]$NoKill,
    [switch]$NoExporter,
    [switch]$NoMonitor,
    [ValidateSet("low", "medium", "high", "xhigh", "max")]
    [string]$MonitorEffort = "max",
    [string]$MonitorInterval = "5m"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainRepo  = "C:\Users\ilies\git\bitcoin-trading-assistant"
$ExpRepo   = "C:\Users\ilies\git\bitcoin-trading-v2-experiment"
$MainPy    = "$MainRepo\backend\venv\Scripts\python.exe"
$ExpPy     = "$ExpRepo\backend\venv\Scripts\python.exe"
$Launcher  = "$ScriptDir\launch_backend.py"

# ---------------------------------------------------------------------------
# Fermeture du run precedent : tue les process dont la ligne de commande matche
# nos marqueurs (ferme aussi les fenetres PowerShell -NoExit qui les hebergent),
# SANS toucher au shell courant ($PID) ni a des process non lies.
# ---------------------------------------------------------------------------
if (-not $NoKill) {
    Write-Host "[start-all] Fermeture des fenetres/process du run precedent..."
    $pattern = 'launch_backend\.py|continuous_journal_exporter|start-journal-exporter|--port 5173|--port 5174|btc-monitor|claude-monitor-prompt|--engine exp|--engine main'
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -and ($_.CommandLine -match $pattern)
    } | ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
    Start-Sleep -Seconds 2
}

# ---------------------------------------------------------------------------
# Backends (DB routee vers bitcoin_experiment / bitcoin_assistant via launch_backend.py)
# ---------------------------------------------------------------------------
Write-Host "[start-all] Backends..."
Start-Process powershell -ArgumentList @('-NoExit', '-Command', "`$Host.UI.RawUI.WindowTitle='BTC-EXP-BACKEND'; & '$ExpPy' '$Launcher' --engine exp")
Start-Process powershell -ArgumentList @('-NoExit', '-Command', "`$Host.UI.RawUI.WindowTitle='BTC-MAIN-BACKEND'; & '$MainPy' '$Launcher' --engine main")

# ---------------------------------------------------------------------------
# Frontends
# ---------------------------------------------------------------------------
Write-Host "[start-all] Frontends..."
Start-Process powershell -ArgumentList @('-NoExit', '-Command', "`$Host.UI.RawUI.WindowTitle='BTC-EXP-FRONTEND'; Set-Location '$ExpRepo\frontend'; `$env:VITE_API_BASE_URL='http://localhost:8001'; npx vite --port 5174 --strictPort")
Start-Process powershell -ArgumentList @('-NoExit', '-Command', "`$Host.UI.RawUI.WindowTitle='BTC-MAIN-FRONTEND'; Set-Location '$MainRepo\frontend'; `$env:VITE_API_BASE_URL='http://localhost:8000'; npx vite --port 5173 --strictPort")

# ---------------------------------------------------------------------------
# Attente des backends (/health)
# ---------------------------------------------------------------------------
Write-Host "[start-all] Attente des backends (/health)..."
foreach ($p in 8001, 8000) {
    $ok = $false
    for ($i = 0; $i -lt 40; $i++) {
        try { Invoke-RestMethod "http://127.0.0.1:$p/health" -TimeoutSec 3 | Out-Null; $ok = $true; break }
        catch { Start-Sleep -Seconds 1 }
    }
    if ($ok) { Write-Host "  backend $p : OK" } else { Write-Warning "  backend $p : NON joignable" }
}

# ---------------------------------------------------------------------------
# Activation des moteurs
# ---------------------------------------------------------------------------
Write-Host "[start-all] Activation des moteurs..."
$body = @{ interval_seconds = $TickSeconds; profile = "scalping" } | ConvertTo-Json
try { Invoke-RestMethod -Method Post "http://127.0.0.1:8001/paper/engine-mode?mode=experimental" | Out-Null; Write-Host "  EXP  -> multi-strategie" } catch { Write-Warning "  EXP engine-mode: $_" }
try { Invoke-RestMethod -Method Post "http://127.0.0.1:8001/paper/autonomous/start" -ContentType "application/json" -Body $body | Out-Null; Write-Host "  EXP  -> autonomous ON ($TickSeconds s)" } catch { Write-Warning "  EXP autonomous: $_" }
try { Invoke-RestMethod -Method Post "http://127.0.0.1:8000/paper/autonomous/start" -ContentType "application/json" -Body $body | Out-Null; Write-Host "  MAIN -> autonomous ON ($TickSeconds s, scalping)" } catch { Write-Warning "  MAIN autonomous: $_" }

# ---------------------------------------------------------------------------
# Journal exporter (capture continue) + superviseur Claude
# ---------------------------------------------------------------------------
if (-not $NoExporter) {
    Write-Host "[start-all] Journal exporter (detache, intervalle ${ExportIntervalSeconds}s)..."
    & "$ScriptDir\start-journal-exporter.ps1" -IntervalSeconds $ExportIntervalSeconds -Detached
}

if (-not $NoMonitor) {
    Write-Host "[start-all] Superviseur Claude temps reel (effort=$MonitorEffort, intervalle=$MonitorInterval)..."
    & "$ScriptDir\start-monitor.ps1" -Effort $MonitorEffort -Interval $MonitorInterval
}

Write-Host ""
Write-Host "[start-all] TERMINE."
Write-Host "  EXP  (multi-strategie) : http://localhost:5174  (backend 8001)"
Write-Host "  MAIN (scalping)        : http://localhost:5173  (backend 8000)"
Write-Host "  Journaux captures      : $MainRepo\docs\journaux\"
Write-Host "  Analyse Claude live    : $MainRepo\docs\journaux\live-analysis-claude.md (superviseur)"
Write-Host "  Verifier le feed live  : Invoke-RestMethod 'http://127.0.0.1:8001/market/price?symbol=BTC/USD'"
Write-Host "  Stopper un moteur      : Invoke-RestMethod -Method Post 'http://127.0.0.1:8001/paper/autonomous/stop'"
