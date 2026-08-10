param(
    [string]$BaseUrl = "https://sris-staging.up.railway.app",
    [string]$Email = "goncalo.saldanha82@gmail.com",
    [string]$FullName = "Goncalo Saldanha",
    [string]$OrganizationName = "SRIS",
    [string]$OrganizationSlug = "sris",
    [switch]$ResetPreparedToken,
    [switch]$ClearCredentialClipboard
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

function ConvertTo-PlainText {
    param([System.Security.SecureString]$SecureValue)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Get-HttpStatusCode {
    param([System.Management.Automation.ErrorRecord]$ErrorRecord)

    try {
        return [int]$ErrorRecord.Exception.Response.StatusCode
    }
    catch {
        return $null
    }
}

function New-ActivationToken {
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 48
    try {
        $generator.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    }
    finally {
        $generator.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

function Save-PreparedToken {
    param(
        [string]$StatePath,
        [string]$Token
    )

    $secureValue = ConvertTo-SecureString $Token -AsPlainText -Force
    try {
        $state = [ordered]@{
            format_version = 1
            base_url = $BaseUrl
            email = $Email
            created_at_utc = [DateTime]::UtcNow.ToString("o")
            token_ciphertext = ConvertFrom-SecureString $secureValue
        }
        $state | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
    }
    finally {
        $secureValue.Dispose()
    }
}

function Get-PreparedToken {
    param([string]$StatePath)

    try {
        $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        if ($state.format_version -ne 1) {
            throw "formato de estado desconhecido"
        }
        if ($state.base_url -ne $BaseUrl -or $state.email -ne $Email) {
            throw "o estado pertence a outro ambiente ou utilizador"
        }
        $secureValue = ConvertTo-SecureString ([string]$state.token_ciphertext)
        try {
            return ConvertTo-PlainText -SecureValue $secureValue
        }
        finally {
            $secureValue.Dispose()
        }
    }
    catch {
        throw (
            "O token preparado nao pode ser recuperado com este utilizador do Windows. " +
            "Execute novamente com -ResetPreparedToken para preparar um token novo."
        )
    }
}

function Clear-ClipboardMarker {
    try {
        Set-Clipboard -Value "[SRIS: segredo temporario removido]" -ErrorAction Stop
    }
    catch {
        Write-Warning "Nao foi possivel limpar automaticamente a area de transferencia."
    }
}

function Test-SrisHealth {
    try {
        $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health"
    }
    catch {
        throw "O staging nao respondeu ao health check. Nao prossiga com a ativacao."
    }

    if ($health.status -ne "ok" -or $health.database -ne "ok") {
        throw "O staging ou a base de dados nao estao operacionais."
    }
}

function Confirm-InstitutionalSession {
    param([string]$Password)

    $loginJson = @{
        email = $Email
        password = $Password
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

    return [PSCustomObject]@{
        User = $me
        Organization = $organization
    }
}

function Write-Success {
    param([PSCustomObject]$Session)

    Write-Host "ACESSO INSTITUCIONAL CONFIRMADO" -ForegroundColor Green
    Write-Host "Utilizador: $($Session.User.full_name) <$($Session.User.email)>"
    Write-Host "Organizacao: $($Session.Organization.name)"
    Write-Host "ID da organizacao: $($Session.Organization.id)"
    Write-Host "Papel: proprietario"
    Write-Host "O token ficou consumido e nao pode voltar a ser utilizado."
    Write-Host "A palavra-passe exata que a API validou foi copiada." -ForegroundColor Green
    Write-Host "NAO elimine ainda as variaveis temporarias do Railway." -ForegroundColor Yellow
    Write-Host "Abra o staging numa janela InPrivate, escreva o email e cole a palavra-passe." -ForegroundColor Cyan
    Write-Host "So depois de o login visual funcionar deve limpar a area de transferencia" -ForegroundColor Yellow
    Write-Host "e eliminar SRIS_ACCESS_ACTIVATION_EMAIL e SRIS_ACCESS_ACTIVATION_TOKEN."
}

function Publish-VerifiedCredential {
    param(
        [string]$Password,
        [PSCustomObject]$Session
    )

    Set-Clipboard -Value $Password
    $script:credentialClipboardContainsPassword = $true
    Write-Success -Session $Session
}

Write-Host "SRIS - ativacao unica do acesso institucional" -ForegroundColor Cyan
Write-Host "Destino: $BaseUrl"
Write-Host "Conta: $Email"
Write-Host "O token nunca sera pedido manualmente nem guardado no GitHub."

if ($ClearCredentialClipboard) {
    Clear-ClipboardMarker
    Write-Host "A credencial temporaria foi removida da area de transferencia." -ForegroundColor Green
    exit 0
}

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw "O Windows nao disponibilizou LOCALAPPDATA; nao e possivel proteger o token."
}

$stateDirectory = Join-Path $env:LOCALAPPDATA "SRIS"
$stateName = (([Uri]$BaseUrl).Host -replace "[^a-zA-Z0-9.-]", "_")
$statePath = Join-Path $stateDirectory "institutional-access-$stateName.json"

New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null

if ($ResetPreparedToken -and (Test-Path -LiteralPath $statePath)) {
    Remove-Item -LiteralPath $statePath -Force
    Write-Host "O token local anterior foi eliminado." -ForegroundColor Yellow
}

if (-not (Test-Path -LiteralPath $statePath)) {
    $preparedToken = New-ActivationToken
    try {
        Save-PreparedToken -StatePath $statePath -Token $preparedToken
        Set-Clipboard -Value $preparedToken

        Write-Host ""
        Write-Host "PREPARACAO CRIADA" -ForegroundColor Green
        Write-Host "O token novo foi copiado e ficou protegido para este utilizador do Windows."
        Write-Host ""
        Write-Host "No Railway > staging > sris > Variables:" -ForegroundColor Cyan
        Write-Host "1. Mantenha SRIS_ACCESS_ACTIVATION_EMAIL=$Email"
        Write-Host "2. Substitua SRIS_ACCESS_ACTIVATION_TOKEN com Ctrl+V"
        Write-Host "3. Grave, faca Deploy e aguarde por ACTIVE"
        Write-Host "4. Execute depois exatamente o mesmo comando PowerShell"
        Write-Host ""
        Write-Host "Pode fechar esta janela. O token nao se perde." -ForegroundColor Yellow
        exit 0
    }
    finally {
        $preparedToken = $null
    }
}

$plainToken = Get-PreparedToken -StatePath $statePath
$securePassword = $null
$secureConfirmation = $null
$plainPassword = $null
$plainConfirmation = $null
$activationJson = $null
$activationBody = $null
$script:credentialClipboardContainsPassword = $false

try {
    Test-SrisHealth
    Write-Host "Foi recuperado o token protegido desta ativacao." -ForegroundColor Green

    $deploymentReady = Read-Host "O novo deployment esta ACTIVE no Railway? Escreva S para continuar"
    if ($deploymentReady.Trim().ToUpperInvariant() -ne "S") {
        Set-Clipboard -Value $plainToken
        Write-Host "Ativacao interrompida sem alterar a conta." -ForegroundColor Yellow
        Write-Host "O mesmo token foi copiado novamente para corrigir a variavel no Railway."
        exit 0
    }

    Clear-ClipboardMarker

    $securePassword = Read-Host "Defina a nova palavra-passe (minimo 12 caracteres)" -AsSecureString
    $plainPassword = ConvertTo-PlainText -SecureValue $securePassword
    $secureConfirmation = Read-Host "Repita a nova palavra-passe" -AsSecureString
    $plainConfirmation = ConvertTo-PlainText -SecureValue $secureConfirmation

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
        $statusCode = Get-HttpStatusCode -ErrorRecord $_
        if ($statusCode -eq 404) {
            Set-Clipboard -Value $plainToken
            Write-Host ""
            Write-Host "ATIVACAO NAO EXECUTADA: TOKEN DO RAILWAY DIFERENTE" -ForegroundColor Red
            Write-Host "A conta e a palavra-passe nao foram alteradas. Nao gere outro token."
            Write-Host "O token certo foi copiado novamente para a area de transferencia."
            Write-Host "Substitua apenas SRIS_ACCESS_ACTIVATION_TOKEN, faca Deploy, aguarde ACTIVE"
            Write-Host "e execute novamente o mesmo comando. O token local permanece protegido."
            exit 2
        }
        if ($statusCode -eq 409) {
            try {
                $session = Confirm-InstitutionalSession -Password $plainPassword
                Publish-VerifiedCredential -Password $plainPassword -Session $session
                Remove-Item -LiteralPath $statePath -Force
                exit 0
            }
            catch {
                Remove-Item -LiteralPath $statePath -Force
                throw (
                    "O token ja foi consumido, mas a sessao nao foi confirmada. " +
                    "Execute o mesmo comando para preparar um token novo."
                )
            }
        }
        if ($statusCode -eq 422) {
            throw "O servidor recusou o email, a palavra-passe ou a organizacao."
        }
        if ($null -ne $statusCode) {
            throw "A ativacao falhou no servidor (HTTP $statusCode)."
        }
        throw "Nao foi possivel contactar o servidor SRIS."
    }

    if ($activation.status -ne "institutional_access_activated") {
        throw "A API nao confirmou a ativacao institucional."
    }

    Write-Host "Conta ativada; a validar a sessao institucional..." -ForegroundColor Green
    $session = Confirm-InstitutionalSession -Password $plainPassword
    Publish-VerifiedCredential -Password $plainPassword -Session $session
    Remove-Item -LiteralPath $statePath -Force
}
catch {
    Write-Host ""
    Write-Host "ATIVACAO INTERROMPIDA" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
finally {
    $plainToken = $null
    $plainPassword = $null
    $plainConfirmation = $null
    $activationJson = $null
    $activationBody = $null
    $activation = $null
    $session = $null
    if ($null -ne $securePassword) {
        $securePassword.Dispose()
    }
    if ($null -ne $secureConfirmation) {
        $secureConfirmation.Dispose()
    }
    if (
        -not (Test-Path -LiteralPath $statePath) -and
        -not $script:credentialClipboardContainsPassword
    ) {
        Clear-ClipboardMarker
    }
}
