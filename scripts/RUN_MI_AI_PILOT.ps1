param(
    [string]$BaseUrl = "https://sris-production.up.railway.app",
    [string]$OrganizationSlug = "sris-pilot"
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

Write-Host "SRIS - smoke test controlado de Mission Intelligence + IA" -ForegroundColor Cyan
Write-Host "Este teste autoriza uma única tentativa e volta a desativar a política no final."

$email = Read-Host "Email institucional"
$securePassword = Read-Host "Palavra-passe" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
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
# explicitly so that selecting [0] returns the organization itself.
$organizations = @()
if ($null -ne $organizationResponse) {
    foreach ($candidate in $organizationResponse) {
        $organizations += $candidate
    }
}

$matchingOrganizations = @($organizations | Where-Object { $_.slug -eq $OrganizationSlug })
if ($matchingOrganizations.Count -eq 1) {
    $organization = $matchingOrganizations[0]
}
elseif ($organizations.Count -eq 1) {
    $organization = $organizations[0]
}
else {
    throw "Não foi possível determinar inequivocamente a organização piloto."
}

$organizationId = [string]$organization.id
if ([string]::IsNullOrWhiteSpace($organizationId)) {
    throw "A API não devolveu um UUID válido para a organização piloto. Nenhuma política foi alterada."
}

$governanceUri = "$BaseUrl/api/organizations/$organizationId/mission-intelligence/ai-governance"
$policyUri = "$governanceUri/policy"
$governance = Invoke-RestMethod -Method Get -Uri $governanceUri -Headers $headers

if (-not $governance.global_provider_configured) {
    throw "O fornecedor global ainda não está configurado. Não foi feita qualquer chamada de IA."
}
if (-not $governance.organization_authorized) {
    throw "Esta organização não corresponde ao UUID autorizado no Railway."
}
if (-not $governance.policy.configured) {
    throw "A política organizacional ainda não existe."
}

function New-PolicyBody([bool]$Enabled, $Policy) {
    $policyJson = @{
        enabled = $Enabled
        monthly_request_limit = $Policy.monthly_request_limit
        monthly_input_token_limit = $Policy.monthly_input_token_limit
        monthly_output_token_limit = $Policy.monthly_output_token_limit
        monthly_budget_usd = $Policy.monthly_budget_usd
        per_request_input_token_limit = $Policy.per_request_input_token_limit
        per_request_output_token_limit = $Policy.per_request_output_token_limit
        max_concurrent_requests = $Policy.max_concurrent_requests
    } | ConvertTo-Json -Compress
    # Prevent PowerShell from unrolling the byte array into individual bytes.
    return ,([System.Text.Encoding]::UTF8.GetBytes($policyJson))
}

$policyEnabled = $false
$result = $null
try {
    Invoke-RestMethod `
        -Method Put `
        -Uri $policyUri `
        -Headers $headers `
        -ContentType "application/json; charset=utf-8" `
        -Body (New-PolicyBody $true $governance.policy) | Out-Null
    $policyEnabled = $true

    $analysisJson = @{ use_ai = $true } | ConvertTo-Json -Compress
    $analysisBody = [System.Text.Encoding]::UTF8.GetBytes($analysisJson)
    $analysisUri = "$BaseUrl/api/organizations/$organizationId/mission-intelligence/demo/M-001/analyze"
    $result = Invoke-RestMethod `
        -Method Post `
        -Uri $analysisUri `
        -Headers $headers `
        -ContentType "application/json; charset=utf-8" `
        -Body $analysisBody
}
finally {
    if ($policyEnabled) {
        Invoke-RestMethod `
            -Method Put `
            -Uri $policyUri `
            -Headers $headers `
            -ContentType "application/json; charset=utf-8" `
            -Body (New-PolicyBody $false $governance.policy) | Out-Null
    }
}

Write-Host ""
Write-Host "Execução concluída; a política voltou a ficar desativada." -ForegroundColor Green
Write-Host "AI status: $($result.ai_status)"
Write-Host "Modo: $($result.execution_mode)"
Write-Host "Run ID: $($result.run_id)"
Write-Host "Input tokens: $($result.ai_usage.input_tokens)"
Write-Host "Output tokens: $($result.ai_usage.output_tokens)"
Write-Host "Custo estimado USD: $($result.ai_usage.estimated_cost_usd)"

if ($result.ai_status -ne "completed" -or $result.execution_mode -ne "hybrid") {
    throw "A execução assistida não cumpriu o gate esperado; consulte o ledger antes de reativar."
}
