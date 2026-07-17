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
    $env:PIP_CACHE_DIR,
    $env:HUGGINGFACE_HUB_CACHE,
    $env:TORCH_HOME,
    $env:XDG_CACHE_HOME,
    $env:TEMP
) | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $_ | Out-Null
}

if (-not (Test-Path $VenvPython)) {
    throw "未找到 E 盘虚拟环境：$VenvPython"
}

Write-Host "依赖安装目录：$ProjectRoot\.venv"
Write-Host "下载及模型缓存：$CacheRoot"
& $VenvPython -m pip install --requirement (Join-Path $ProjectRoot "requirements.txt")
