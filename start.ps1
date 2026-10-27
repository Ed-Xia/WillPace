$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create the .venv environment and install back/requirements.txt first. See 部署与启动说明.md.'
}
& $python (Join-Path $PSScriptRoot 'back\server_main.py')
exit $LASTEXITCODE
