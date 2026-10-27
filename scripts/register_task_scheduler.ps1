<#
.SYNOPSIS
    Registra a execução diária do pipeline do Ibovespa Analytics no Agendador de
    Tarefas do Windows.

.DESCRIPTION
    Este script NÃO é executado automaticamente pela aplicação ou por qualquer
    agente — é uma alteração no sistema operacional e deve ser executada
    deliberadamente, uma vez, por quem administra a máquina.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\register_task_scheduler.ps1
#>

param(
    [string]$TaskName = "IbovespaAnalyticsPipeline",
    [string]$TimeOfDay = "19:00"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ScriptPath = Join-Path $ProjectRoot "scripts\run_pipeline.py"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Ambiente virtual não encontrado em $PythonExe. Crie-o com 'python -m venv .venv' e instale as dependências antes de registrar a tarefa."
    exit 1
}

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`" --trigger scheduled" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At $TimeOfDay
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Execução diária do pipeline de ingestão/indicadores do Ibovespa Analytics (pós-fechamento de mercado)." -Force

Write-Host "Tarefa '$TaskName' registrada para execução diária às $TimeOfDay."
Write-Host "Para verificar: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "Para remover:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
