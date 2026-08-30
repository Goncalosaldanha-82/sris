$ErrorActionPreference = "Stop"

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
    $env:SRIS_LOCAL_ACTIVATION_TOKEN = $plainToken
    Set-Clipboard -Value $plainToken

    Write-Host "TOKEN SRIS PREPARADO" -ForegroundColor Green
    Write-Host "O token tem $($plainToken.Length) caracteres e foi copiado."
    Write-Host "No Railway, edite SRIS_ACCESS_ACTIVATION_TOKEN e prima Ctrl+V."
    Write-Host "Nao feche esta janela. O token ficou apenas na memoria do PowerShell."
    Write-Host "Nao gere outro token. O script de ativacao usara este mesmo valor."
}
finally {
    if ($null -ne $bytes) {
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
    $plainToken = $null
}
