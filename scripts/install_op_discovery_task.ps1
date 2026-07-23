param(
    [Parameter(Mandatory = $true)][string]$AppExecutable,
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [switch]$EnableIntegration,
    [switch]$RequireExisting
)

$ErrorActionPreference = "Stop"
$taskName = "ProducaoOperacional-ImportarNovasOPs"
$daysByKey = [ordered]@{
    monday = "Monday"; tuesday = "Tuesday"; wednesday = "Wednesday"; thursday = "Thursday"
    friday = "Friday"; saturday = "Saturday"; sunday = "Sunday"
}

if (-not (Test-Path -LiteralPath $AppExecutable)) {
    throw "Executável não encontrado: $AppExecutable"
}
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Configuração não encontrada: $ConfigPath"
}

# O setup e a tela de personalização compartilham esta rotina. Valores genéricos
# só atendem instalações sem bloco de integração; dados operacionais ficam fora do Git.
$raw = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -eq $raw.op_discovery) {
    $raw | Add-Member -NotePropertyName op_discovery -NotePropertyValue ([pscustomobject]@{})
}
$defaults = [ordered]@{
    enabled = $false
    source_root_candidates = @("\\SERVIDOR\Compartilhamento", "Z:\")
    production_relative_path = "Clientes\00_PRODUZINDO"
    groups = @("00_GRUPO_A", "00_GRUPO_B")
    document_extensions = @(".odt", ".docx", ".pdf")
    schedule = [ordered]@{ days = @("monday", "tuesday", "wednesday", "thursday", "friday"); times = @("08:00", "14:00", "17:00") }
    initial_sector_name = "Projeto"
    worker_lease_minutes = 20
}
foreach ($entry in $defaults.GetEnumerator()) {
    if ($null -eq $raw.op_discovery.PSObject.Properties[$entry.Key]) {
        $raw.op_discovery | Add-Member -NotePropertyName $entry.Key -NotePropertyValue $entry.Value
    }
}
if ($EnableIntegration) {
    $raw.op_discovery.PSObject.Properties.Remove("enabled")
    $raw.op_discovery | Add-Member -NotePropertyName enabled -NotePropertyValue $true
}

$schedule = $raw.op_discovery.schedule
$selectedDays = @($schedule.days | ForEach-Object { "$($_)".Trim().ToLowerInvariant() } | Where-Object { $daysByKey.Contains($_) } | Select-Object -Unique)
$selectedTimes = @($schedule.times | ForEach-Object { "$($_)".Trim() } | Where-Object { $_ -match '^(?:[01]\d|2[0-3]):[0-5]\d$' } | Select-Object -Unique)
if ($selectedDays.Count -eq 0 -or $selectedTimes.Count -eq 0) {
    throw "A integração precisa de ao menos um dia e um horário válidos (HH:MM)."
}

$temporary = "$ConfigPath.tmp"
$raw | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -LiteralPath $temporary -Destination $ConfigPath -Force

$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($RequireExisting -and $null -eq $existingTask) {
    Write-Output "Nenhuma tarefa integradora existente foi alterada."
    exit 0
}

$taskDays = @($selectedDays | ForEach-Object { $daysByKey[$_] })
$triggers = foreach ($time in $selectedTimes) {
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek $taskDays -At $time
}
$action = New-ScheduledTaskAction -Execute $AppExecutable -Argument ('--sync-new-ops --config "{0}"' -f $ConfigPath)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$identity = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null
Write-Output ("Tarefa '{0}' configurada: {1}; {2}." -f $taskName, ($taskDays -join ", "), ($selectedTimes -join ", "))
