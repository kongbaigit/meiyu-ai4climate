param([int]$Port = 8513)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
}
& $taskPython -m streamlit run (Join-Path $PSScriptRoot 'app.py') --server.address 127.0.0.1 --server.port $Port --browser.gatherUsageStats false
if ($LASTEXITCODE -ne 0) { throw '应用启动失败。查看上方错误；端口被占用时可通过 -Port 指定其他端口。' }
