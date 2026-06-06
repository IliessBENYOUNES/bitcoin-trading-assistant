<#
.SYNOPSIS
  Lance un Claude Code "superviseur" dans une nouvelle fenetre : surveille les 2 moteurs
  BTC en temps reel (effort max), verifie le lancement, analyse en continu via /loop.

.NOTES
  Flags verifies sur l'install 2.1.167 : --effort max, --permission-mode auto, --model,
  --add-dir, -n. Construit la commande SANS continuation backtick (fragile en PS 5.1).
#>
param(
    [ValidateSet("low", "medium", "high", "xhigh", "max")]
    [string]$Effort = "max",
    [string]$Model = "claude-opus-4-8",
    [string]$Interval = "5m"
)

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainRepo   = "C:\Users\ilies\git\bitcoin-trading-assistant"
$ExpRepo    = "C:\Users\ilies\git\bitcoin-trading-v2-experiment"
$PromptFile = Join-Path $ScriptDir "claude-monitor-prompt.md"

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Warning "[monitor] CLI 'claude' introuvable dans le PATH - superviseur NON lance."
    return
}

# Prompt initial : une seule ligne, sans guillemets internes (evite tout souci de quoting).
$initial = "Tu es le SUPERVISEUR temps reel des 2 moteurs BTC (run apres reset, base propre). Lis le fichier $PromptFile puis applique-le: verifie le lancement des 4 serveurs + moteurs + l etat du feed, puis lance /loop $Interval pour comparer MAIN (scalping) vs EXP (multi-strategie v2.1.0), verifier le gate v2.1.0, et ecris ton analyse horodatee dans docs/journaux/live-analysis-claude.md. Reste factuel et chiffre, lecture seule."

# Commande de la nouvelle fenetre, construite par concatenation explicite (pas de backtick).
$title = "`$Host.UI.RawUI.WindowTitle = 'BTC-MONITOR';"
$claude = "claude --model $Model --effort $Effort --permission-mode auto --add-dir `"$ExpRepo`" -n btc-monitor `"$initial`""
$inner = "Set-Location `"$MainRepo`"; $title Write-Host '[monitor] Claude superviseur (effort=$Effort)'; $claude"

Start-Process powershell -ArgumentList @('-NoExit', '-Command', $inner)
Write-Host "[monitor] Superviseur Claude lance dans une fenetre (effort=$Effort, intervalle=$Interval)."
Write-Host "[monitor] Analyse en continu : $MainRepo\docs\journaux\live-analysis-claude.md"
