$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

function New-Token([int]$Bytes = 48) {
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer).Replace('+','-').Replace('/','_').TrimEnd('=')
}

Write-Host ''
Write-Host '==========================================' -ForegroundColor DarkYellow
Write-Host ' SRIS Enterprise - Primeira Configuracao' -ForegroundColor DarkYellow
Write-Host '==========================================' -ForegroundColor DarkYellow
Write-Host ''

if (Test-Path '.env') {
    $answer = Read-Host 'Ja existe um ficheiro .env. Pretende mante-lo? (S/n)'
    if ($answer -notmatch '^[Nn]$') {
        Write-Host 'Configuracao existente preservada.' -ForegroundColor Green
    } else {
        Remove-Item '.env' -Force
    }
}

if (-not (Test-Path '.env')) {
    $dbUser = 'sris_local'
    $dbPass = New-Token 36
    $secretKey = New-Token 64
    $encryptionKey = New-Token 32
    $storageUser = 'sris_local_storage'
    $storagePass = New-Token 36

    @"
ENVIRONMENT=development
APP_NAME=SRIS Enterprise Experience Alpha
SECRET_KEY=$secretKey
ENCRYPTION_MASTER_KEY=$encryptionKey
POSTGRES_USER=$dbUser
POSTGRES_PASSWORD=$dbPass
DATABASE_URL=postgresql+psycopg://${dbUser}:${dbPass}@postgres:5432/sris
REDIS_URL=redis://redis:6379/0
ACCESS_TOKEN_MINUTES=20
REFRESH_TOKEN_DAYS=14
ALLOWED_ORIGINS=http://localhost:8000
COOKIE_SECURE=false
OBJECT_STORAGE_ENDPOINT=http://minio:9000
OBJECT_STORAGE_BUCKET=sris-backups
OBJECT_STORAGE_ACCESS_KEY=$storageUser
OBJECT_STORAGE_SECRET_KEY=$storagePass
OBJECT_STORAGE_REGION=eu-west-1
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=no-reply@example.com
BOOTSTRAP_DEMO=false
"@ | Set-Content '.env' -Encoding UTF8
    Write-Host 'Ficheiro .env criado com segredos aleatorios.' -ForegroundColor Green
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker Desktop nao encontrado. Instale-o antes de continuar.'
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $dockerExe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $dockerExe)) { throw 'Docker Desktop nao encontrado.' }
    Write-Host 'A iniciar o Docker Desktop...'
    Start-Process $dockerExe
    $deadline = (Get-Date).AddMinutes(3)
    do {
        Start-Sleep -Seconds 3
        & docker info *> $null
    } while ($LASTEXITCODE -ne 0 -and (Get-Date) -lt $deadline)
    if ($LASTEXITCODE -ne 0) { throw 'O Docker nao ficou operacional.' }
}

Write-Host 'A construir e iniciar os servicos...'
& docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Falha no arranque dos servicos.' }

$email = Read-Host 'Email do administrador [admin@example.com]'
if ([string]::IsNullOrWhiteSpace($email)) { $email = 'admin@example.com' }
$org = Read-Host 'Nome da organizacao [Organizacao Piloto]'
if ([string]::IsNullOrWhiteSpace($org)) { $org = 'Organizacao Piloto' }
$passwordSecure = Read-Host 'Defina uma palavra-passe forte para o administrador' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($passwordSecure)
try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
if ([string]::IsNullOrWhiteSpace($password)) { throw 'A palavra-passe nao pode ficar vazia.' }

Write-Host 'A criar o administrador...'
& docker compose exec -T app python -m app.scripts.bootstrap_admin --email $email --password $password --organization $org
if ($LASTEXITCODE -ne 0) {
    Write-Host 'O administrador pode ja existir. A configuracao prossegue.' -ForegroundColor Yellow
}

$slug = ($org.ToLowerInvariant() -replace '[^a-z0-9]+','-').Trim('-')
Write-Host 'A carregar a demonstracao...'
& docker compose exec -T app python -m app.scripts.seed_demo --organization-slug $slug
if ($LASTEXITCODE -ne 0) {
    Write-Host 'A demonstracao pode ja existir. A configuracao prossegue.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Configuracao concluida.' -ForegroundColor Green
Write-Host "Abra o Launcher e use: $email"
Write-Host 'A palavra-passe nao foi guardada em texto pelo configurador.'
Write-Host ''
Read-Host 'Prima Enter para terminar'
