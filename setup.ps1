$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    $taskBase = Join-Path $env:USERPROFILE 'miniconda3/python.exe'
    if (Test-Path -LiteralPath $taskBase) {
        & $taskBase -m venv (Join-Path $PSScriptRoot '.venv')
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.13 -m venv (Join-Path $PSScriptRoot '.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $PSScriptRoot '.venv')
    } else {
        throw '需要先安装 Python 3.13，再运行 setup.ps1。'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python 环境创建失败。' }
}
& $taskPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络和 Python 版本。' }
& $taskPython -m pip check
if ($LASTEXITCODE -ne 0) { throw '依赖检查未通过。' }
Write-Host '环境准备完成。运行 start.cmd 即可打开应用。'
