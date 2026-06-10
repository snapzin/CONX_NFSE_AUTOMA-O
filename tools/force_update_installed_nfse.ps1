param(
    [string]$InstallRoot = "C:\Users\conxc\AppData\Local\Programs\NFSe Automacao",
    [switch]$WaitForExit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$sourceBackend = Join-Path $projectRoot "dist\server"
$sourceAsar = Join-Path $projectRoot "dist\app.asar"
$installRoot = $InstallRoot
$targetBackend = Join-Path $installRoot "resources\backend"
$targetBackendVercel = Join-Path $installRoot "resources\backend-vercel"
$targetAsar = Join-Path $installRoot "resources\app.asar"
$logPath = Join-Path $projectRoot "dist\installed-update.log"

"[$(Get-Date -Format o)] Atualizador iniciado. InstallRoot=$installRoot" | Out-File -FilePath $logPath -Encoding UTF8

function Assert-PathStartsWith {
    param(
        [Parameter(Mandatory = $true)][string]$PathToCheck,
        [Parameter(Mandatory = $true)][string]$ExpectedRoot
    )
    $full = [System.IO.Path]::GetFullPath($PathToCheck)
    $root = [System.IO.Path]::GetFullPath($ExpectedRoot)
    if (-not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Caminho inesperado: $full"
    }
}

Assert-PathStartsWith -PathToCheck $sourceBackend -ExpectedRoot $projectRoot
Assert-PathStartsWith -PathToCheck $sourceAsar -ExpectedRoot $projectRoot
Assert-PathStartsWith -PathToCheck $targetBackend -ExpectedRoot $installRoot
Assert-PathStartsWith -PathToCheck $targetBackendVercel -ExpectedRoot $installRoot
Assert-PathStartsWith -PathToCheck $targetAsar -ExpectedRoot $installRoot

if (-not (Test-Path -LiteralPath (Join-Path $sourceBackend "server.exe"))) {
    throw "Backend novo nao encontrado: $sourceBackend"
}
if (-not (Test-Path -LiteralPath $sourceAsar)) {
    throw "app.asar novo nao encontrado: $sourceAsar"
}
if (-not (Test-Path -LiteralPath $targetBackend)) {
    throw "Backend instalado nao encontrado: $targetBackend"
}

Get-Process | Where-Object {
    $_.ProcessName -eq "NFSe Automacao" -or $_.ProcessName -eq "server"
} | ForEach-Object {
    "Encerrando processo: $($_.ProcessName) PID=$($_.Id)" | Add-Content -Path $logPath
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

if ($WaitForExit) {
    "Aguardando processos fecharem..." | Add-Content -Path $logPath
    while (Get-Process | Where-Object { $_.ProcessName -eq "NFSe Automacao" -or $_.ProcessName -eq "server" }) {
        Start-Sleep -Seconds 5
    }
} else {
    Start-Sleep -Seconds 2
}

$stamp = Get-Date -Format "yyyyMMddHHmmss"
$backupDir = Join-Path $installRoot ("backup-before-license-fix-" + $stamp)
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

if (Test-Path -LiteralPath $targetAsar) {
    Copy-Item -LiteralPath $targetAsar -Destination (Join-Path $backupDir "app.asar") -Force
}
if (Test-Path -LiteralPath (Join-Path $targetBackend "server.exe")) {
    Copy-Item -LiteralPath (Join-Path $targetBackend "server.exe") -Destination (Join-Path $backupDir "server.exe") -Force
}
if (Test-Path -LiteralPath (Join-Path $targetBackend "_internal\license.py")) {
    Copy-Item -LiteralPath (Join-Path $targetBackend "_internal\license.py") -Destination (Join-Path $backupDir "license.py") -Force
}

$configBackup = Join-Path $env:TEMP ("nfse-config-" + $stamp + ".py")
if (Test-Path -LiteralPath (Join-Path $targetBackend "config.py")) {
    Copy-Item -LiteralPath (Join-Path $targetBackend "config.py") -Destination $configBackup -Force
}

Copy-Item -LiteralPath $sourceAsar -Destination $targetAsar -Force

if (Test-Path -LiteralPath $targetBackendVercel) {
    Remove-Item -LiteralPath $targetBackendVercel -Recurse -Force
}
Copy-Item -LiteralPath $sourceBackend -Destination $targetBackendVercel -Recurse -Force

if (Test-Path -LiteralPath $configBackup) {
    Copy-Item -LiteralPath $configBackup -Destination (Join-Path $targetBackendVercel "config.py") -Force
}

try {
    Copy-Item -LiteralPath (Join-Path $sourceBackend "server.exe") -Destination (Join-Path $targetBackend "server.exe") -Force
    Copy-Item -LiteralPath (Join-Path $sourceBackend "_internal") -Destination $targetBackend -Recurse -Force
} catch {
    "Backend padrao travado; backend-vercel foi atualizado. Erro: $($_.Exception.Message)" | Add-Content -Path $logPath
}

if (Test-Path -LiteralPath $configBackup) {
    Copy-Item -LiteralPath $configBackup -Destination (Join-Path $targetBackend "config.py") -Force
}

foreach ($name in @("license.key", "license.grace")) {
    $path = Join-Path $targetBackend $name
    if (Test-Path -LiteralPath $path) {
        Move-Item -LiteralPath $path -Destination (Join-Path $backupDir ($name + ".disabled")) -Force
    }
}

$exe = Join-Path $installRoot "NFSe Automacao.exe"
if (Test-Path -LiteralPath $exe) {
    Start-Process -FilePath $exe -WorkingDirectory $installRoot
}

Write-Host "Atualizacao aplicada."
Write-Host "Backup:" $backupDir
"[$(Get-Date -Format o)] Atualizacao aplicada. Backup=$backupDir" | Add-Content -Path $logPath
