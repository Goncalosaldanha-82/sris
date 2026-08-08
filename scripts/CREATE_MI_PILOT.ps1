param(
    [string]$BaseUrl = "https://sris-production.up.railway.app",
    [string]$OrganizationName = "SRIS Pilot",
    [string]$OrganizationSlug = "sris-pilot"
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

Write-Host "SRIS - criação segura da identidade institucional piloto" -ForegroundColor Cyan
Write-Host "Destino: $BaseUrl"
Write-Host "A IA permanece desativada; este script cria apenas utilizador, organização e política."

$fullName = Read-Host "Nome completo"
$email = Read-Host "Email institucional"
$securePassword = Read-Host "Palavra-passe (mínimo 10 caracteres)" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
}

if ($plainPassword.Length -lt 10) {
    $plainPassword = $null
    throw "A palavra-passe tem de possuir pelo menos 10 caracteres."
}

$registerBody = @{
    email = $email
    full_name = $fullName
    password = $plainPassword
} | ConvertTo-Json

try {
    Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/auth/register" `
        -ContentType "application/json" `
        -Body $registerBody | Out-Null
    Write-Host "Utilizador criado." -ForegroundColor Green
}
catch {
    $statusCode = [int]$_.Exception.Response.StatusCode
    if ($statusCode -ne 409) {
        $plainPassword = $null
        throw
    }
    Write-Host "O utilizador já existia; será apenas autenticado." -ForegroundColor Yellow
}

$loginBody = @{
    email = $email
    password = $plainPassword
} | ConvertTo-Json
try {
    $login = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/auth/login" `
        -ContentType "application/json" `
        -Body $loginBody
}
finally {
    $plainPassword = $null
    $securePassword.Dispose()
}

$headers = @{ Authorization = "Bearer $($login.access_token)" }
$organizations = @(
    Invoke-RestMethod `
        -Method Get `
        -Uri "$BaseUrl/api/organizations" `
        -Headers $headers
)

if ($organizations.Count -eq 0) {
    $organizationBody = @{
        name = $OrganizationName
        slug = $OrganizationSlug
    } | ConvertTo-Json
    $organization = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/organizations" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $organizationBody
    Write-Host "Organização piloto criada." -ForegroundColor Green
}
else {
    $matchingOrganizations = @($organizations | Where-Object { $_.slug -eq $OrganizationSlug })
    if ($matchingOrganizations.Count -eq 1) {
        $organization = $matchingOrganizations[0]
    }
    elseif ($organizations.Count -eq 1) {
        $organization = $organizations[0]
    }
    else {
        throw "Existem várias organizações e nenhuma corresponde ao slug '$OrganizationSlug'."
    }
    Write-Host "Foi utilizada a organização já associada ao utilizador." -ForegroundColor Yellow
}

$policyBody = @{
    enabled = $false
    monthly_request_limit = 20
    monthly_input_token_limit = 250000
    monthly_output_token_limit = 50000
    monthly_budget_usd = "5.00"
    per_request_input_token_limit = 60000
    per_request_output_token_limit = 3000
    max_concurrent_requests = 1
} | ConvertTo-Json

$policyUri = "$BaseUrl/api/organizations/$($organization.id)/mission-intelligence/ai-governance/policy"
$governance = Invoke-RestMethod `
    -Method Put `
    -Uri $policyUri `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $policyBody

$organization.id | Set-Clipboard
Write-Host ""
Write-Host "Configuração institucional inicial concluída." -ForegroundColor Green
Write-Host "Organização: $($organization.name)"
Write-Host "UUID: $($organization.id)"
Write-Host "Política ativa: $($governance.policy.enabled)"
Write-Host "O UUID foi copiado para a área de transferência."
Write-Host "Não ative a IA antes de fechar o auto-registo e a criação de organizações no Railway." -ForegroundColor Yellow
