param(
    [int]$Port = 8765,
    [switch]$Open
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

$arguments = @('run', '--locked', 'app.py', '--host', '127.0.0.1', '--port', $Port)
if ($Open) {
    $arguments += '--open'
}

Write-Host "Starting Cognitive Memory Demo on http://127.0.0.1:$Port"
uv @arguments
exit $LASTEXITCODE
