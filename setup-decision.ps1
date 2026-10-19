$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskEnvironment = Join-Path $PSScriptRoot '.venv-decision'
$taskPython = Join-Path $taskEnvironment 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv $taskEnvironment }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv $taskEnvironment }
    else { throw '请先安装Python 3.11或更新版本，并允许终端找到Python。' }
    if ($LASTEXITCODE -ne 0) { throw '创建Python环境失败。' }
}
& $taskPython -c 'import sys; assert sys.version_info >= (3, 11), "需要Python 3.11或更新版本"'
if ($LASTEXITCODE -ne 0) { throw 'Python版本不满足要求。' }
& $taskPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-decision.txt')
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络后重试。' }
Write-Output '搬货决策运行环境已准备好。'
