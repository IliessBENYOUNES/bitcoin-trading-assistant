<#
.SYNOPSIS
  Lance un Claude Code "superviseur" dans une nouvelle fenetre : il surveille les 2 moteurs
  BTC en temps reel (effort max), verifie le lancement, et analyse en continu via /loop.

.DESCRIPTION
  Appelle le CLI `claude` (verifie : v2.1.x) avec les VRAIS flags :
    --effort max            (l'utilisateur veut effort max ; sinon -Effort xhigh pour reduire le cout)
    --permission-mode auto  (read-only autorise sans prompt ; destructif bloque)
    --model claude-opus-4-8
    --add-dir <repo EXP>    (acces lecture au worktree experimental)
  Le prompt initial (court) renvoie aux instructions completes : scripts/claude-monitor-prompt.md.
  Necessite `claude` dans le PATH et une session Claude authentifiee.

.EXAMPLE
  .\scripts\start-monitor.ps1
  .\scripts\start-monitor.ps1 -Effort xhigh -Interval 3m
#>
param(
    [ValidateSet("low", "medium", "high", "xhigh", "max")]
    [string]$Effort = "max",
    [string]$Model = "claude-opus-4-8",
    [string]$Interval = "5m"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainRepo = "C:\Users\ilies\git\bitcoin-trading-assistant"
$ExpRepo = "C:\Users\ilies\git\bitcoin-trading-v2-experiment"
$PromptFile = Join-Path $ScriptDir "claude-monitor-prompt.md"

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Warning "[monitor] CLI 'claude' introuvable dans le PATH — superviseur NON lance."
    return
}

# Prompt initial court : renvoie aux instructions detaillees + lance la supervision.
$initial = "Tu es le SUPERVISEUR temps reel des 2 moteurs de trading BTC (run demarre apres un reset complet, base propre). " + `
    "Lis d'abord tes instructions completes dans le fichier '$PromptFile', puis execute-les : " + `
    "verifie le lancement des 4 serveurs + moteurs + l'etat du feed de donnees, puis lance une surveillance continue " + `
    "(/loop $Interval) qui compare MAIN (scalping) vs EXP (multi-strategie v2.1.0) et ecrit son analyse horodatee " + `
    "dans docs/journaux/live-analysis-claude.md. Reste factuel et chiffre."

$cmd = "Set-Location '$MainRepo'; " + `
    "Write-Host '[monitor] Claude superviseur (effort=$Effort, modele=$Model, intervalle=$Interval)'; " + `
    "claude --model $Model --effort $Effort --permission-mode auto --add-dir '$ExpRepo' -n btc-monitor `"$initial`""

Start-Process powershell -ArgumentList '-NoExit', '-Command', $cmd
Write-Host "[monitor] Superviseur Claude lance dans une nouvelle fenetre (effort=$Effort, intervalle=$Interval)."
Write-Host "[monitor] Son analyse en continu : $MainRepo\docs\journaux\live-analysis-claude.md"
