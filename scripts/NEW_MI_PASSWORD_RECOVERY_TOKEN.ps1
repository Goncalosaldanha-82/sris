$ErrorActionPreference = "Stop"

Write-Host "SRIS - token temporario para recuperacao da palavra-passe" -ForegroundColor Cyan

$bytes = New-Object byte[] 32
$generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $generator.GetBytes($bytes)
}
finally {
    $generator.Dispose()
}

$token = ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
$token | Set-Clipboard

Write-Host "Token aleatorio criado e copiado para a area de transferencia." -ForegroundColor Green
Write-Host "Nao o mostre, fotografe, envie por mensagem ou grave no repositorio." -ForegroundColor Yellow
Write-Host "O token so funcionara uma vez e apenas para o utilizador piloto configurado."

$token = $null
[Array]::Clear($bytes, 0, $bytes.Length)
