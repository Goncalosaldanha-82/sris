Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir
$AppUrl = 'http://localhost:8000'

function Test-DockerCli {
    return [bool](Get-Command docker -ErrorAction SilentlyContinue)
}

function Test-DockerEngine {
    if (-not (Test-DockerCli)) { return $false }
    & docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Start-DockerDesktop {
    $dockerExe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $dockerExe) {
        Start-Process $dockerExe
        return $true
    }
    return $false
}

function Wait-DockerEngine([int]$Seconds = 120) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerEngine) { return $true }
        Start-Sleep -Seconds 3
        [System.Windows.Forms.Application]::DoEvents()
    }
    return $false
}

function Test-App {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $AppUrl -TimeoutSec 3
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch { return $false }
}

function Get-ComposeStatus {
    if (-not (Test-DockerEngine)) { return 'Docker parado' }
    $output = & docker compose ps --format 'table {{.Service}}\t{{.Status}}' 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { return $output.Trim() }
    return $output.Trim()
}

$form = New-Object System.Windows.Forms.Form
$form.Text = 'SRIS Enterprise Launcher'
$form.Size = New-Object System.Drawing.Size(700,560)
$form.StartPosition = 'CenterScreen'
$form.BackColor = [System.Drawing.Color]::FromArgb(11,23,18)
$form.ForeColor = [System.Drawing.Color]::White
$form.Font = New-Object System.Drawing.Font('Segoe UI',10)
$form.FormBorderStyle = 'FixedSingle'
$form.MaximizeBox = $false

$title = New-Object System.Windows.Forms.Label
$title.Text = 'SRIS ENTERPRISE'
$title.Font = New-Object System.Drawing.Font('Segoe UI Semibold',24)
$title.ForeColor = [System.Drawing.Color]::FromArgb(205,174,92)
$title.Location = New-Object System.Drawing.Point(30,22)
$title.AutoSize = $true
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = 'Mission Intelligence Center'
$subtitle.Font = New-Object System.Drawing.Font('Segoe UI',12)
$subtitle.ForeColor = [System.Drawing.Color]::FromArgb(185,204,194)
$subtitle.Location = New-Object System.Drawing.Point(34,66)
$subtitle.AutoSize = $true
$form.Controls.Add($subtitle)

$statusPanel = New-Object System.Windows.Forms.Panel
$statusPanel.Location = New-Object System.Drawing.Point(30,105)
$statusPanel.Size = New-Object System.Drawing.Size(620,115)
$statusPanel.BackColor = [System.Drawing.Color]::FromArgb(20,38,30)
$form.Controls.Add($statusPanel)

$statusHeadline = New-Object System.Windows.Forms.Label
$statusHeadline.Text = 'A verificar o sistema...'
$statusHeadline.Font = New-Object System.Drawing.Font('Segoe UI Semibold',14)
$statusHeadline.Location = New-Object System.Drawing.Point(18,16)
$statusHeadline.AutoSize = $true
$statusPanel.Controls.Add($statusHeadline)

$statusDetail = New-Object System.Windows.Forms.Label
$statusDetail.Text = ''
$statusDetail.Font = New-Object System.Drawing.Font('Consolas',9)
$statusDetail.ForeColor = [System.Drawing.Color]::FromArgb(170,190,180)
$statusDetail.Location = New-Object System.Drawing.Point(20,52)
$statusDetail.Size = New-Object System.Drawing.Size(580,50)
$statusPanel.Controls.Add($statusDetail)

function New-Button($Text, $X, $Y, $Width = 190) {
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $Text
    $button.Location = New-Object System.Drawing.Point($X,$Y)
    $button.Size = New-Object System.Drawing.Size($Width,48)
    $button.FlatStyle = 'Flat'
    $button.FlatAppearance.BorderSize = 1
    $button.FlatAppearance.BorderColor = [System.Drawing.Color]::FromArgb(70,108,89)
    $button.BackColor = [System.Drawing.Color]::FromArgb(27,56,42)
    $button.ForeColor = [System.Drawing.Color]::White
    $button.Cursor = [System.Windows.Forms.Cursors]::Hand
    return $button
}

$startButton = New-Button '▶  Iniciar SRIS' 30 245
$openButton = New-Button '🌐  Abrir Plataforma' 245 245
$stopButton = New-Button '■  Parar SRIS' 460 245
$statusButton = New-Button '↻  Atualizar Estado' 30 310
$logsButton = New-Button '≡  Ver Logs' 245 310
$folderButton = New-Button '📁  Abrir Pasta' 460 310
$form.Controls.AddRange(@($startButton,$openButton,$stopButton,$statusButton,$logsButton,$folderButton))

$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Location = New-Object System.Drawing.Point(30,382)
$logBox.Size = New-Object System.Drawing.Size(620,105)
$logBox.Multiline = $true
$logBox.ScrollBars = 'Vertical'
$logBox.ReadOnly = $true
$logBox.BackColor = [System.Drawing.Color]::FromArgb(7,15,11)
$logBox.ForeColor = [System.Drawing.Color]::FromArgb(185,204,194)
$logBox.Font = New-Object System.Drawing.Font('Consolas',9)
$form.Controls.Add($logBox)

function Write-LauncherLog($Message) {
    $logBox.AppendText("[$((Get-Date).ToString('HH:mm:ss'))] $Message`r`n")
    $logBox.SelectionStart = $logBox.Text.Length
    $logBox.ScrollToCaret()
    [System.Windows.Forms.Application]::DoEvents()
}

function Update-Status {
    if (-not (Test-DockerCli)) {
        $statusHeadline.Text = 'Docker Desktop não encontrado'
        $statusHeadline.ForeColor = [System.Drawing.Color]::Tomato
        $statusDetail.Text = 'Instale o Docker Desktop para executar o SRIS.'
        return
    }
    if (-not (Test-DockerEngine)) {
        $statusHeadline.Text = 'Docker parado'
        $statusHeadline.ForeColor = [System.Drawing.Color]::Orange
        $statusDetail.Text = 'O Launcher pode iniciar o Docker automaticamente.'
        return
    }
    $compose = Get-ComposeStatus
    if (Test-App) {
        $statusHeadline.Text = 'SRIS operacional'
        $statusHeadline.ForeColor = [System.Drawing.Color]::LightGreen
    } else {
        $statusHeadline.Text = 'Docker operacional · SRIS parado ou a iniciar'
        $statusHeadline.ForeColor = [System.Drawing.Color]::Khaki
    }
    $statusDetail.Text = $compose
}

$startButton.Add_Click({
    try {
        Write-LauncherLog 'A iniciar o SRIS...'
        if (-not (Test-Path (Join-Path $ProjectDir '.env'))) {
            [System.Windows.Forms.MessageBox]::Show('Falta o ficheiro .env. Execute PRIMEIRA_CONFIGURACAO_SRIS.cmd antes de iniciar.', 'Configuração necessária', 'OK', 'Warning') | Out-Null
            return
        }
        if (-not (Test-DockerEngine)) {
            Write-LauncherLog 'A iniciar o Docker Desktop...'
            if (-not (Start-DockerDesktop)) { throw 'Não foi possível localizar o Docker Desktop.' }
            if (-not (Wait-DockerEngine 150)) { throw 'O motor Docker não ficou operacional dentro do tempo esperado.' }
        }
        $output = & docker compose up -d 2>&1 | Out-String
        Write-LauncherLog $output.Trim()
        $deadline = (Get-Date).AddSeconds(90)
        while ((Get-Date) -lt $deadline -and -not (Test-App)) {
            Start-Sleep -Seconds 2
            [System.Windows.Forms.Application]::DoEvents()
        }
        Update-Status
        if (Test-App) {
            Write-LauncherLog 'SRIS iniciado com sucesso.'
            Start-Process $AppUrl
        } else {
            Write-LauncherLog 'O serviço arrancou, mas ainda não responde no navegador. Consulte os logs.'
        }
    } catch {
        Write-LauncherLog "ERRO: $($_.Exception.Message)"
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Erro ao iniciar', 'OK', 'Error') | Out-Null
    }
})

$openButton.Add_Click({
    if (Test-App) { Start-Process $AppUrl }
    else { [System.Windows.Forms.MessageBox]::Show('O SRIS ainda não está operacional. Clique em Iniciar SRIS.', 'SRIS parado', 'OK', 'Information') | Out-Null }
})

$stopButton.Add_Click({
    if (Test-DockerEngine) {
        Write-LauncherLog 'A encerrar os serviços...'
        $output = & docker compose down 2>&1 | Out-String
        Write-LauncherLog $output.Trim()
    }
    Update-Status
})

$statusButton.Add_Click({ Update-Status })
$logsButton.Add_Click({
    if (Test-DockerEngine) {
        $output = & docker compose logs --tail 120 2>&1 | Out-String
        $logBox.Text = $output
        $logBox.SelectionStart = $logBox.Text.Length
        $logBox.ScrollToCaret()
    }
})
$folderButton.Add_Click({ Start-Process explorer.exe $ProjectDir })

$form.Add_Shown({ Update-Status })
[void]$form.ShowDialog()
