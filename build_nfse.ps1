param(
    [switch]$SkipClean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-InsideRoot {
    param(
        [Parameter(Mandatory = $true)][string]$PathToCheck,
        [Parameter(Mandatory = $true)][string]$Root
    )

    $resolvedRoot = [System.IO.Path]::GetFullPath($Root)
    $resolvedPath = [System.IO.Path]::GetFullPath($PathToCheck)
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Caminho fora do projeto: $resolvedPath"
    }
}

function Remove-DirectorySafe {
    param(
        [Parameter(Mandatory = $true)][string]$TargetPath
    )

    for ($attempt = 1; $attempt -le 6; $attempt++) {
        if (-not (Test-Path $TargetPath)) {
            return
        }

        try {
            Get-ChildItem -LiteralPath $TargetPath -Recurse -Force -ErrorAction SilentlyContinue |
                ForEach-Object {
                    if ($_.Attributes -band [System.IO.FileAttributes]::ReadOnly) {
                        $_.Attributes = [System.IO.FileAttributes]::Normal
                    }
                }

            Remove-Item -LiteralPath $TargetPath -Recurse -Force -ErrorAction Stop
            return
        } catch {
            Start-Sleep -Milliseconds (500 * $attempt)
        }
    }

    if (Test-Path $TargetPath) {
        throw "Nao foi possivel remover '$TargetPath'. Feche o executavel e tente novamente."
    }
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distPath = Join-Path $projectRoot "dist"
$buildPath = Join-Path $projectRoot "build"
$distFallbackPath = Join-Path $projectRoot "dist_build"
$buildFallbackPath = Join-Path $projectRoot "build_build"
$specPath = Join-Path $projectRoot "NFSE_Automacao.spec"
$distPathForBuild = $distPath
$buildPathForBuild = $buildPath

Assert-InsideRoot -PathToCheck $distPath -Root $projectRoot
Assert-InsideRoot -PathToCheck $buildPath -Root $projectRoot
Assert-InsideRoot -PathToCheck $distFallbackPath -Root $projectRoot
Assert-InsideRoot -PathToCheck $buildFallbackPath -Root $projectRoot

if (-not $SkipClean) {
    if (Test-Path $distPath) {
        try {
            Remove-DirectorySafe -TargetPath $distPath
        } catch {
            Write-Warning "Nao foi possivel limpar '$distPath'. Usando fallback em '$distFallbackPath'."
            $distPathForBuild = $distFallbackPath
        }
    }
    if (Test-Path $buildPath) {
        try {
            Remove-DirectorySafe -TargetPath $buildPath
        } catch {
            Write-Warning "Nao foi possivel limpar '$buildPath'. Usando fallback em '$buildFallbackPath'."
            $buildPathForBuild = $buildFallbackPath
        }
    }

    if ($distPathForBuild -eq $distFallbackPath -and (Test-Path $distFallbackPath)) {
        Remove-DirectorySafe -TargetPath $distFallbackPath
    }
    if ($buildPathForBuild -eq $buildFallbackPath -and (Test-Path $buildFallbackPath)) {
        Remove-DirectorySafe -TargetPath $buildFallbackPath
    }
}

$distAppDir = Join-Path $distPathForBuild "NFSE_Automacao"
$distExe = Join-Path $distAppDir "NFSE_Automacao.exe"
$nestedExe = Join-Path $distAppDir "_internal\\NFSE_Automacao.exe"

$pythonExe = Join-Path $projectRoot ".venv\\Scripts\\python.exe"
if (Test-Path $pythonExe) {
    $command = $pythonExe
    $args = @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $distPathForBuild, "--workpath", $buildPathForBuild, $specPath)
} else {
    $command = "py"
    $args = @("-3", "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $distPathForBuild, "--workpath", $buildPathForBuild, $specPath)
}

Write-Host "Compilando com:" $command ($args -join " ")
& $command @args

if (-not (Test-Path $distAppDir)) {
    throw "Build concluido sem pasta final: $distAppDir"
}

if (-not (Test-Path $distExe) -and (Test-Path $nestedExe)) {
    Copy-Item -LiteralPath $nestedExe -Destination $distExe -Force
}

if (Test-Path $nestedExe) {
    Remove-Item -LiteralPath $nestedExe -Force
}

if (-not (Test-Path $distExe)) {
    throw "Executavel final nao encontrado: $distExe"
}

if (-not (Test-Path (Join-Path $distAppDir "python312.dll"))) {
    throw "python312.dll nao encontrado ao lado do executavel final."
}

Write-Host ""
Write-Host "Build OK."
Write-Host "Execute:" $distExe
