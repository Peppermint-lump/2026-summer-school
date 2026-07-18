param(
    [switch] $SkipSync,
    [string] $HostAddress = "127.0.0.1",
    [int] $Port = 12393
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$upstreamDir = Join-Path $repoRoot "third_party\Open-LLM-VTuber"
$configPath = Join-Path $upstreamDir "conf.yaml"
$templatePath = Join-Path $upstreamDir "config_templates\conf.default.yaml"
$localUv = Join-Path $repoRoot ".tools\uv\bin\uv.exe"
$uvCacheDir = Join-Path $repoRoot ".tools\uv-cache"
$uvToolDir = Join-Path $repoRoot ".tools\uv-tools"
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$venvPython = Join-Path $upstreamDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $upstreamDir)) {
    throw "Open-LLM-VTuber is missing at $upstreamDir"
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCommand) {
    $uv = $uvCommand.Source
}
elseif (Test-Path -LiteralPath $localUv) {
    $uv = $localUv
}
else {
    throw "uv is not available on PATH or at $localUv. Install uv before running the Open-LLM-VTuber dev server."
}

if (-not (Test-Path -LiteralPath $configPath)) {
    Copy-Item -LiteralPath $templatePath -Destination $configPath
}

$config = Get-Content -Raw -LiteralPath $configPath
$config = $config -replace "host:\s*'[^']*'", "host: '$HostAddress'"
$config = $config -replace "port:\s*\d+", "port: $Port"
$config = $config -replace "(?m)^(\s*mode_checkbox_group:\s*).*$", "`$1''"
$config = $config -replace "(?m)^(\s*sft_dropdown:\s*).*$", "`$1''"
Set-Content -NoNewline -Encoding utf8 -LiteralPath $configPath -Value $config

Push-Location $upstreamDir
try {
    $env:UV_CACHE_DIR = $uvCacheDir
    $env:UV_TOOL_DIR = $uvToolDir
    if ($pythonCommand) {
        $env:UV_PYTHON = $pythonCommand.Source
    }

    if (-not $SkipSync) {
        & $uv sync
    }

    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Virtual environment Python not found at $venvPython. Run without -SkipSync first."
    }

    & $venvPython run_server.py
}
finally {
    Pop-Location
}
