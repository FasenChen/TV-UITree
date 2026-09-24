[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$main = Join-Path $repoRoot 'main.py'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "未找到项目 Python：$python。请先创建 .venv 并安装 requirements.txt。"
}

if (-not (Test-Path -LiteralPath $main -PathType Leaf)) {
    throw "未找到项目入口：$main。"
}

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw '未找到 npx。请安装 Node.js 22.19 或更高版本后重试。'
}

Write-Host 'Starting MCP Inspector for tv-uitree...'
Write-Host "Python: $python"
Write-Host "Server: $main mcp"

Push-Location $repoRoot
try {
    & npx -y @modelcontextprotocol/inspector $python $main mcp
    if ($LASTEXITCODE -ne 0) {
        throw "MCP Inspector exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
