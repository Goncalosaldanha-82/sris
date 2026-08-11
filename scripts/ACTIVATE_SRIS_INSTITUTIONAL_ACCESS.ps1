param(
    [string]$BaseUrl = "https://sris-staging.up.railway.app"
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")
$ActivationUrl = "$BaseUrl/account.html?mode=activate"

Write-Host "SRIS - primeiro acesso institucional" -ForegroundColor Cyan
Write-Host "Este procedimento ja nao utiliza PowerShell, tokens copiados ou a area de transferencia."
Write-Host "Abra os logs do deployment ACTIVE e localize o bloco:" -ForegroundColor Yellow
Write-Host "SRIS: PRIMEIRO ACESSO INSTITUCIONAL DISPONIVEL"
Write-Host "Depois abra $ActivationUrl e introduza o codigo curto mostrado no log."

try {
    Start-Process $ActivationUrl
}
catch {
    Write-Warning "Nao foi possivel abrir o navegador automaticamente. Use o endereco indicado acima."
}
