param(
    [string]$BaseUrl = "https://sris-pilot-v1-staging.up.railway.app",
    [string]$Email = "contact@sris.io",
    [string]$FullName = "Goncalo Saldanha",
    [string]$OrganizationName = "SRIS",
    [string]$OrganizationSlug = "sris",
    [string]$TokenFile = (
        Join-Path $env:LOCALAPPDATA "SRIS\institutional-activation-token.txt"
    )
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

function Get-HttpStatusCode {
    param([System.Management.Automation.ErrorRecord]$ErrorRecord)

    try {
        return [int]$ErrorRecord.Exception.Response.StatusCode
    }
    catch {
        return $null
    }
}

function Get-ActivationFailureMessage {
    param([System.Management.Automation.ErrorRecord]$ErrorRecord)

    $statusCode = Get-HttpStatusCode -ErrorRecord $ErrorRecord
    switch ($statusCode) {
        404 {
            return (
                "O servidor recusou a ativacao. Confirme o deployment e as variaveis " +
                "SRIS_ACCESS_ACTIVATION_EMAIL e SRIS_ACCESS_ACTIVATION_TOKEN."
            )
        }
        409 {
            return (
                "O token de ativacao ja foi utilizado. Gere um token novo no Railway " +
                "e aguarde pelo novo deployment."
            )
        }
        422 {
            return (
                "O servidor recusou os dados. Confirme o email, a palavra-passe " +
                "e o identificador da organizacao."
            )
        }
        default {
            if ($null -ne $statusCode) {
                return "A ativacao falhou no servidor (HTTP $statusCode)."
            }
            return "Nao foi possivel contactar o servidor SRIS."
        }
    }
}

Write-Host "SRIS - ativacao unica do acesso institucional" -ForegroundColor Cyan
Write-Host "Destino: $BaseUrl"
Write-Host "Conta: $Email"
Write-Host "Nenhum segredo sera gravado no ficheiro ou enviado para o GitHub."

$activationConsumed = $false
if (Test-Path -LiteralPath $TokenFile) {
    try {
        $encryptedToken = (
            Get-Content -LiteralPath $TokenFile -Raw
        ).Trim()
        $secureToken = ConvertTo-SecureString $encryptedToken
        Write-Host "Token cifrado local encontrado; nao precisa de o colar." -ForegroundColor Green
    }
    catch {
        throw (
            "O token cifrado local nao pode ser lido nesta conta do Windows. " +
            "Execute novamente PREPARE_SRIS_INSTITUTIONAL_TOKEN.ps1."
        )
    }
}
else {
    $secureToken = Read-Host "Cole o token temporario do Railway" -AsSecureString
}
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
}

$securePassword = Read-Host "Defina a nova palavra-passe (minimo 12 caracteres)" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
}

$secureConfirmation = Read-Host "Repita a nova palavra-passe" -AsSecureString
$confirmationPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
    $secureConfirmation
)
try {
    $plainConfirmation = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
        $confirmationPointer
    )
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($confirmationPointer)
}

try {
    $plainToken = $plainToken.Trim()
    if ($plainToken.Length -lt 32) {
        throw "O token temporario tem menos de 32 caracteres."
    }
    if ($plainPassword.Length -lt 12) {
        throw "A palavra-passe tem de possuir pelo menos 12 caracteres."
    }
    if ($plainPassword -cne $plainConfirmation) {
        throw "As duas palavras-passe nao coincidem."
    }
    if ($OrganizationSlug -notmatch "^[a-z0-9-]{2,120}$") {
        throw "O identificador da organizacao nao e valido."
    }

    $activationJson = @{
        email = $Email
        activation_token = $plainToken
        new_password = $plainPassword
        full_name = $FullName
        organization_name = $OrganizationName
        organization_slug = $OrganizationSlug
    } | ConvertTo-Json -Compress
    $activationBody = [System.Text.Encoding]::UTF8.GetBytes($activationJson)

    try {
        $activation = Invoke-RestMethod `
            -Method Post `
            -Uri "$BaseUrl/api/auth/emergency-access-activation" `
            -ContentType "application/json; charset=utf-8" `
            -Body $activationBody
    }
    catch {
        throw (Get-ActivationFailureMessage -ErrorRecord $_)
    }

    if ($activation.status -ne "institutional_access_activated") {
        throw "A API nao confirmou a ativacao institucional."
    }
    $activationConsumed = $true

    Write-Host "Conta ativada; a validar a sessao institucional..." -ForegroundColor Green

    $loginJson = @{
        email = $Email
        password = $plainPassword
    } | ConvertTo-Json -Compress
    $loginBody = [System.Text.Encoding]::UTF8.GetBytes($loginJson)
    $login = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/auth/login" `
        -ContentType "application/json; charset=utf-8" `
        -Body $loginBody

    if ([string]::IsNullOrWhiteSpace([string]$login.access_token)) {
        throw "A API nao devolveu um token de sessao."
    }

    $headers = @{ Authorization = "Bearer $($login.access_token)" }
    $me = Invoke-RestMethod `
        -Method Get `
        -Uri "$BaseUrl/api/auth/me" `
        -Headers $headers
    $organizations = @(
        Invoke-RestMethod `
            -Method Get `
            -Uri "$BaseUrl/api/organizations" `
            -Headers $headers
    )
    $organization = $organizations | Where-Object {
        $_.slug -eq $OrganizationSlug
    } | Select-Object -First 1
    if ($null -eq $organization) {
        throw "O login funcionou, mas a organizacao institucional nao foi encontrada."
    }

    $memberships = @(
        Invoke-RestMethod `
            -Method Get `
            -Uri "$BaseUrl/api/organizations/$($organization.id)/memberships" `
            -Headers $headers
    )
    $membership = $memberships | Where-Object {
        $_.user_id -eq $me.id
    } | Select-Object -First 1
    if ($null -eq $membership -or $membership.role -ne "owner") {
        throw "A conta autenticou, mas nao possui o papel de proprietario."
    }

    Write-Host "ACESSO INSTITUCIONAL CONFIRMADO" -ForegroundColor Green
    Write-Host "Utilizador: $($me.full_name) <$($me.email)>"
    Write-Host "Organizacao: $($organization.name)"
    Write-Host "ID da organizacao: $($organization.id)"
    Write-Host "Papel: proprietario"
    Write-Host "O token ficou consumido e nao pode voltar a ser utilizado."
    Write-Host (
        "Elimine agora SRIS_ACCESS_ACTIVATION_EMAIL e " +
        "SRIS_ACCESS_ACTIVATION_TOKEN no Railway."
    ) -ForegroundColor Yellow
}
finally {
    $plainToken = $null
    $plainPassword = $null
    $plainConfirmation = $null
    $encryptedToken = $null
    $activationJson = $null
    $activationBody = $null
    $activation = $null
    $loginJson = $null
    $loginBody = $null
    $login = $null
    $headers = $null
    if ($null -ne $secureToken) {
        $secureToken.Dispose()
    }
    if ($null -ne $securePassword) {
        $securePassword.Dispose()
    }
    if ($null -ne $secureConfirmation) {
        $secureConfirmation.Dispose()
    }
    if ($activationConsumed -and (Test-Path -LiteralPath $TokenFile)) {
        Remove-Item -LiteralPath $TokenFile -Force
    }
    try {
        Set-Clipboard -Value "[SRIS: segredo temporario removido]" -ErrorAction Stop
    }
    catch {
        Write-Warning "Nao foi possivel limpar automaticamente a area de transferencia."
    }
}
