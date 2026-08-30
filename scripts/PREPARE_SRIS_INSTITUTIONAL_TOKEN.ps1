param(
    [string]$TokenFile = (
        Join-Path $env:LOCALAPPDATA "SRIS\institutional-activation-token.txt"
    )
)

$ErrorActionPreference = "Stop"

$tokenDirectory = Split-Path -Parent $TokenFile
New-Item -ItemType Directory -Path $tokenDirectory -Force | Out-Null

$bytes = New-Object byte[] 48
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $generator.GetBytes($bytes)
}
finally {
    $generator.Dispose()
}

$plainToken = [Convert]::ToBase64String($bytes).TrimEnd("=")
$plainToken = $plainToken.Replace("+", "-").Replace("/", "_")

try {
    $secureToken = ConvertTo-SecureString $plainToken -AsPlainText -Force
    $encryptedToken = ConvertFrom-SecureString $secureToken
    Set-Content -Path $TokenFile -Value $encryptedToken -Encoding UTF8
    Set-Clipboard -Value $plainToken

    Write-Host "TOKEN SRIS PREPARADO" -ForegroundColor Green
    Write-Host "O token tem $($plainToken.Length) caracteres e foi copiado."
    Write-Host "No Railway, edite SRIS_ACCESS_ACTIVATION_TOKEN e prima Ctrl+V."
    Write-Host "Nao gere outro token. O script de ativacao usara este mesmo valor."
}
finally {
    if ($null -ne $bytes) {
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
    $plainToken = $null
    $encryptedToken = $null
    if ($null -ne $secureToken) {
        $secureToken.Dispose()
    }
}
