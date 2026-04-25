param(
    [int]$IntervalSeconds = 3600,
    [switch]$Once,
    [switch]$Detached,
    [string]$Python = "python",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")

if ($Detached) {
    $argsList = @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-IntervalSeconds", "$IntervalSeconds",
        "-Python", "`"$Python`""
    )

    if ($Once) {
        $argsList += "-Once"
    }

    if ($OutputDir -ne "") {
        $argsList += @("-OutputDir", "`"$OutputDir`"")
    }

    Start-Process powershell -ArgumentList $argsList -WorkingDirectory $RepoRoot
    Write-Host "[journal-exporter] Fenêtre détachée lancée. Intervalle: $IntervalSeconds secondes."
    exit 0
}

Set-Location $RepoRoot

$pythonArgs = @(
    "scripts/continuous_journal_exporter.py",
    "--interval-seconds", "$IntervalSeconds"
)

if ($Once) {
    $pythonArgs += "--once"
}

if ($OutputDir -ne "") {
    $pythonArgs += @("--output-dir", $OutputDir)
}

Write-Host "[journal-exporter] Repo: $RepoRoot"
Write-Host "[journal-exporter] Commande: $Python $($pythonArgs -join ' ')"
& $Python @pythonArgs
exit $LASTEXITCODE
