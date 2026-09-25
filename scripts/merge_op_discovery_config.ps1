param(
    [Parameter(Mandatory = $true)][string]$TargetConfig,
    [Parameter(Mandatory = $true)][string]$TemplateConfig
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $TargetConfig)) {
    throw "Configuração instalada não encontrada: $TargetConfig"
}
if (-not (Test-Path -LiteralPath $TemplateConfig)) {
    throw "Modelo de configuração não encontrado: $TemplateConfig"
}

# Atualizações não podem substituir banco, SMTP ou preferências existentes. O
# único acréscimo seguro é o bloco de integração quando ele ainda não existe.
$target = Get-Content -LiteralPath $TargetConfig -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -ne $target.op_discovery) {
    Write-Output "A configuração de integração existente foi preservada."
    exit 0
}

$template = Get-Content -LiteralPath $TemplateConfig -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -eq $template.op_discovery) {
    Write-Output "O modelo não possui configuração de integração para adicionar."
    exit 0
}

$target | Add-Member -NotePropertyName op_discovery -NotePropertyValue $template.op_discovery
$temporary = "$TargetConfig.tmp"
$target | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -LiteralPath $temporary -Destination $TargetConfig -Force
Write-Output "A configuração de integração foi adicionada sem alterar os demais dados locais."
