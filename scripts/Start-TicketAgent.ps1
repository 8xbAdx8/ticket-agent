param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('offline', 'live')]
    [string]$Mode,
    [switch]$CheckOnly,
    [switch]$NoBrowser,
    [string]$RuntimeRoot,
    [int]$Port
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
# A double-click may inherit an older desktop environment. Refresh only the Key,
# without displaying it or storing it in any file.
if ($Mode -eq 'live' -and $env:TICKET_DISABLE_LOCAL_SECRETS -ne '1' -and [string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
    $env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')
}
if ($Mode -eq 'live' -and $env:TICKET_DISABLE_LOCAL_SECRETS -ne '1') {
    foreach ($name in @('DASHSCOPE_API_KEY','DASHSCOPE_BASE_URL','DASHSCOPE_MODEL','DEEPSEEK_MODEL','DEEPSEEK_BASE_URL',
            'LANGCHAIN_API_KEY','LANGCHAIN_ENDPOINT','LANGCHAIN_PROJECT','LANGCHAIN_WORKSPACE_ID',
            'LANGSMITH_API_KEY','LANGSMITH_ENDPOINT','LANGSMITH_PROJECT','LANGSMITH_WORKSPACE_ID')) {
        if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name,'Process'))) {
            $configuredValue = [Environment]::GetEnvironmentVariable($name,'User')
            if (-not [string]::IsNullOrWhiteSpace($configuredValue)) {
                [Environment]::SetEnvironmentVariable($name,$configuredValue,'Process')
            }
        }
    }
    Remove-Variable configuredValue -ErrorAction SilentlyContinue
}
$pythonPath = $null
$foundCandidate = $false
$moduleCheck = if ($Mode -eq 'live') { 'streamlit,pandas,langchain,langchain_deepseek,langchain_openai,httpx' } else { 'streamlit,pandas' }
$probe = "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(n) for n in '$moduleCheck'.split(',')) else 1)"
foreach ($folder in @('.venv-v35', '.venv-deepseek', '.venv-v3', '.venv')) {
    $candidate = Join-Path $projectRoot "$folder\Scripts\python.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $foundCandidate = $true
        try {
            & $candidate -c $probe *> $null
            if ($LASTEXITCODE -eq 0) { $pythonPath = $candidate; break }
        } catch { }
    }
}
if (-not $pythonPath) {
    if ($foundCandidate) { Write-Host 'Python environments were found but none has the required dependencies.' }
    else { Write-Host 'Python environment not found.' }
    Write-Host 'Run these commands in the project directory:'
    Write-Host 'py -3.12 -m venv .venv-v35'
    Write-Host '.\.venv-v35\Scripts\python.exe -m pip install -r requirements-v35-lock.txt'
    exit 1
}
Set-Location -LiteralPath $projectRoot
$launchArgs = @((Join-Path $PSScriptRoot 'launch_app.py'), '--mode', $Mode)
if ($CheckOnly) { $launchArgs += '--check-only' }
if ($NoBrowser) { $launchArgs += '--no-browser' }
if ($RuntimeRoot) { $launchArgs += @('--runtime-root', $RuntimeRoot) }
if ($Port) { $launchArgs += @('--port', "$Port") }
& $pythonPath @launchArgs
exit $LASTEXITCODE
