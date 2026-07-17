$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$CacheRoot = Join-Path $ProjectRoot ".cache"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

$env:PIP_CACHE_DIR = Join-Path $CacheRoot "pip"
$env:HF_HOME = Join-Path $CacheRoot "huggingface"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TORCH_HOME = Join-Path $CacheRoot "torch"
$env:XDG_CACHE_HOME = Join-Path $CacheRoot "xdg"
$env:TEMP = Join-Path $CacheRoot "temp"
$env:TMP = $env:TEMP

@(
    $env:HUGGINGFACE_HUB_CACHE,
    $env:TORCH_HOME,
    $env:XDG_CACHE_HOME,
    $env:TEMP
) | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $_ | Out-Null
}

Push-Location $ProjectRoot
try {
    & $VenvPython (Join-Path $ProjectRoot "tts_demo.py")
}
finally {
    Pop-Location
}
