param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('offline', 'live')]
    [string]$Mode,
    [switch]$CheckOnly,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
# A double-click may inherit an older desktop environment. Refresh only the Key,
# without displaying it or storing it in any file.
if ($Mode -eq 'live' -and [string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
    $env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')
}
$pythonPath = $null
foreach ($folder in @('.venv-v35', '.venv-deepseek', '.venv-v3', '.venv')) {
    $candidate = Join-Path $projectRoot "$folder\Scripts\python.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $pythonPath = $candidate
        break
    }
}
if (-not $pythonPath) {
    Write-Host 'Python environment not found. Run these commands in the project directory:'
    Write-Host 'py -3.12 -m venv .venv-deepseek'
    Write-Host '.\.venv-deepseek\Scripts\python.exe -m pip install -r requirements-deepseek-lock.txt'
    exit 1
}
Set-Location -LiteralPath $projectRoot
$launchArgs = @((Join-Path $PSScriptRoot 'launch_app.py'), '--mode', $Mode)
if ($CheckOnly) { $launchArgs += '--check-only' }
if ($NoBrowser) { $launchArgs += '--no-browser' }
& $pythonPath @launchArgs
exit $LASTEXITCODE
