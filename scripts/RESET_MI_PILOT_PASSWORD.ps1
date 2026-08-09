param(
    [string]$BaseUrl = "https://sris-production.up.railway.app",
    [string]$Email = "goncalo.saldanha82@gmail.com"
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

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

    $recovery = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/auth/emergency-password-recovery" `
        -ContentType "application/json; charset=utf-8" `
        -Body $recoveryBody

    if ($recovery.status -ne "password_updated") {
        throw "A API nao confirmou a reposicao da palavra-passe."
    }

    Write-Host "Palavra-passe reposta; a validar o novo inicio de sessao..." -ForegroundColor Green

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
    $loginJson = $null
    $secureToken.Dispose()
    $securePassword.Dispose()
    $secureConfirmation.Dispose()
    "" | Set-Clipboard
}
