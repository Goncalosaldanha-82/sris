param(
    [string]$BaseUrl = "https://sris-production.up.railway.app",
    [string]$OrganizationName = "SRIS Pilot",
    [string]$OrganizationSlug = "sris-pilot"
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

Write-Host "SRIS - criacao segura da identidade institucional piloto" -ForegroundColor Cyan
Write-Host "Destino: $BaseUrl"
Write-Host "A IA permanece desativada; este script cria apenas utilizador, organizacao e politica."

$fullName = Read-Host "Nome completo"
$email = Read-Host "Email institucional"
$securePassword = Read-Host "Palavra-passe (minimo 10 caracteres)" -AsSecureString
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

$registerJson = @{
    email = $email
    full_name = $fullName
    password = $plainPassword
} | ConvertTo-Json -Compress
$registerBody = [System.Text.Encoding]::UTF8.GetBytes($registerJson)

try {
    Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/auth/register" `
        -ContentType "application/json; charset=utf-8" `
        -Body $registerBody | Out-Null
    Write-Host "Utilizador criado." -ForegroundColor Green
}
catch {
    $statusCode = [int]$_.Exception.Response.StatusCode
    if ($statusCode -ne 409) {
        $plainPassword = $null
        throw
    }
    Write-Host "O utilizador ja existia; sera apenas autenticado." -ForegroundColor Yellow
}

$loginJson = @{
    email = $email
    password = $plainPassword
} | ConvertTo-Json -Compress
$loginBody = [System.Text.Encoding]::UTF8.GetBytes($loginJson)
try {
    $login = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/auth/login" `
        -ContentType "application/json; charset=utf-8" `
        -Body $loginBody
}
finally {
    $plainPassword = $null
    $securePassword.Dispose()
}

$headers = @{ Authorization = "Bearer $($login.access_token)" }
$organizationResponse = Invoke-RestMethod `
    -Method Get `
    -Uri "$BaseUrl/api/organizations" `
    -Headers $headers

# Windows PowerShell 5.1 can preserve a JSON array returned by
# Invoke-RestMethod as one pipeline object. Enumerate the assigned value
# explicitly so that selecting [0] always returns an organization, not the
# array that contains it.
$organizations = @()
if ($null -ne $organizationResponse) {
    foreach ($candidate in $organizationResponse) {
        $organizations += $candidate
    }
}

if ($organizations.Count -eq 0) {
    $organizationJson = @{
        name = $OrganizationName
        slug = $OrganizationSlug
    } | ConvertTo-Json -Compress
    $organizationBody = [System.Text.Encoding]::UTF8.GetBytes($organizationJson)
    $organization = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/organizations" `
        -Headers $headers `
        -ContentType "application/json; charset=utf-8" `
        -Body $organizationBody
    Write-Host "Organizacao piloto criada." -ForegroundColor Green
}
else {
    $matchingOrganizations = @(
        $organizations | Where-Object { $_.slug -eq $OrganizationSlug }
    )
    if ($matchingOrganizations.Count -eq 1) {
        $organization = $matchingOrganizations[0]
    }
    elseif ($organizations.Count -eq 1) {
        $organization = $organizations[0]
    }
    else {
        throw "Existem varias organizacoes e nenhuma corresponde ao slug '$OrganizationSlug'."
    }
    Write-Host "Foi utilizada a organizacao ja associada ao utilizador." -ForegroundColor Yellow
}

$organizationId = [string]$organization.id
if ([string]::IsNullOrWhiteSpace($organizationId)) {
    throw "A API nao devolveu um UUID valido para a organizacao piloto. A politica nao foi alterada."
}

$policyJson = @{
    enabled = $false
    monthly_request_limit = 20
    monthly_input_token_limit = 250000
    monthly_output_token_limit = 50000
    monthly_budget_usd = "5.00"
    per_request_input_token_limit = 60000
    per_request_output_token_limit = 6000
    max_concurrent_requests = 1
} | ConvertTo-Json -Compress
$policyBody = [System.Text.Encoding]::UTF8.GetBytes($policyJson)

$policyUri = "$BaseUrl/api/organizations/$organizationId/mission-intelligence/ai-governance/policy"
$governance = Invoke-RestMethod `
    -Method Put `
    -Uri $policyUri `
    -Headers $headers `
    -ContentType "application/json; charset=utf-8" `
    -Body $policyBody

$organizationId | Set-Clipboard
Write-Host ""
Write-Host "Configuracao institucional inicial concluida." -ForegroundColor Green
Write-Host "Organizacao: $($organization.name)"
Write-Host "UUID: $organizationId"
Write-Host "Politica ativa: $($governance.policy.enabled)"
Write-Host "O UUID foi copiado para a area de transferencia."
Write-Host "Nao ative a IA antes de fechar o auto-registo e a criacao de organizacoes no Railway." -ForegroundColor Yellow
