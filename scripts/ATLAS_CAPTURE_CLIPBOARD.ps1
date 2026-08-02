param(
    [string]$Repo = "C:\Users\barba\Documents\GitHub\sris",
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$drop = Join-Path $Repo "docs\atlas\chat-drop"
New-Item -ItemType Directory -Force -Path $drop | Out-Null

$content = Get-Clipboard -Raw
if ([string]::IsNullOrWhiteSpace($content)) {
    throw "The clipboard is empty."
}

$file = Join-Path $drop "conversation-$timestamp.md"
$content | Set-Content -Path $file -Encoding UTF8

Write-Host "Saved clipboard transcript to: $file"

$applyFlag = ""
if ($Apply) {
    $applyFlag = "--apply"
}

Push-Location $Repo
try {
    python -m app.atlas_chat_bridge.cli ingest --input $file --repo $Repo $applyFlag
}
finally {
    Pop-Location
}
