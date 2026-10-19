param([int]$Port = 8532)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv-decision/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { & (Join-Path $PSScriptRoot 'setup-decision.ps1') }
& $taskPython -m src.decision_server --port $Port
if ($LASTEXITCODE -ne 0) { throw '服务启动失败；端口被占用时可通过-Port指定其他端口。' }
