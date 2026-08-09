param(
    [string]$BaseUrl = "https://sris-production.up.railway.app",
    [string]$Email = "goncalo.saldanha82@gmail.com"
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

function Get-RecoveryFailureMessage {
    param([System.Management.Automation.ErrorRecord]$ErrorRecord)

    $statusCode = Get-HttpStatusCode -ErrorRecord $ErrorRecord
    switch ($statusCode) {
        404 {
            return (
                "O servidor recusou a recuperacao. Confirme que o novo token e o email " +
                "estao ativos no Railway e que o deployment terminou com sucesso."
            )
        }
        409 {
            return (
                "O token temporario ja foi utilizado. Gere um token novo, substitua-o " +
                "no Railway e conclua o respetivo deployment."
            )
        }
        422 {
            return "O servidor recusou os dados da reposicao por serem invalidos."
        }
        default {
            if ($null -ne $statusCode) {
                return "A recuperacao falhou no servidor (HTTP $statusCode)."
            }
            return "Nao foi possivel contactar o servidor SRIS para concluir a recuperacao."
        }
    }
}

Write-Host "SRIS - reposicao unica da palavra-passe institucional" -ForegroundColor Cyan
Write-Host "Destino: $BaseUrl"
Write-Host "Esta operacao nao ativa a politica nem executa qualquer chamada de IA."

$secureToken = Read-Host "Cole o token temporario" -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
}

$securePassword = Read-Host "Nova palavra-passe (minimo 12 caracteres)" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
}

$secureConfirmation = Read-Host "Repita a nova palavra-passe" -AsSecureString
$confirmationPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureConfirmation)
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
        throw "O token temporario nao e valido."
    }
    if ($plainPassword.Length -lt 12) {
        throw "A nova palavra-passe tem de possuir pelo menos 12 caracteres."
    }
    if ($plainPassword -cne $plainConfirmation) {
        throw "As duas palavras-passe nao coincidem."
    }

    $recoveryJson = @{
        email = $Email
        recovery_token = $plainToken
        new_password = $plainPassword
    } | ConvertTo-Json -Compress
    $recoveryBody = [System.Text.Encoding]::UTF8.GetBytes($recoveryJson)

    try {
        $recovery = Invoke-RestMethod `
            -Method Post `
            -Uri "$BaseUrl/api/auth/emergency-password-recovery" `
            -ContentType "application/json; charset=utf-8" `
            -Body $recoveryBody
    }
    catch {
        throw (Get-RecoveryFailureMessage -ErrorRecord $_)
    }

    if ($recovery.status -ne "password_updated") {
        throw "A API nao confirmou a reposicao da palavra-passe."
    }

    Write-Host "Palavra-passe reposta; a validar o novo inicio de sessao..." -ForegroundColor Green

    $loginJson = @{
        email = $Email
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
    catch {
        throw (
            "A palavra-passe foi alterada, mas a validacao automatica do novo inicio " +
            "de sessao falhou. Nao reutilize o token."
        )
    }

    if ([string]::IsNullOrWhiteSpace([string]$login.access_token)) {
        throw "A palavra-passe foi alterada, mas o novo inicio de sessao nao foi confirmado."
    }

    Write-Host "Reposicao concluida e novo inicio de sessao confirmado." -ForegroundColor Green
    Write-Host "O token ficou consumido e nao pode voltar a ser utilizado."
    Write-Host "Elimine agora as duas variaveis temporarias no Railway." -ForegroundColor Yellow
}
finally {
    $plainToken = $null
    $plainPassword = $null
    $plainConfirmation = $null
    $recoveryJson = $null
    $recoveryBody = $null
    $recovery = $null
    $loginJson = $null
    $loginBody = $null
    $login = $null
    if ($null -ne $secureToken) {
        $secureToken.Dispose()
    }
    if ($null -ne $securePassword) {
        $securePassword.Dispose()
    }
    if ($null -ne $secureConfirmation) {
        $secureConfirmation.Dispose()
    }

    # Windows PowerShell 5.1 can convert an empty pipeline value to $null and
    # make Set-Clipboard throw. A harmless non-secret marker reliably removes
    # the token without ever masking the original recovery result.
    try {
        Set-Clipboard -Value "[SRIS: segredo temporario removido]" -ErrorAction Stop
    }
    catch {
        Write-Warning "Nao foi possivel limpar automaticamente a area de transferencia."
    }
}
