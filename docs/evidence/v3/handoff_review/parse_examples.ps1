param([string]$Blocks)
$items = Get-Content -LiteralPath $Blocks -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($item in $items) {
    $parseTokens = $null
    $parseErrors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseInput($item.code, [ref]$parseTokens, [ref]$parseErrors)
    if ($parseErrors.Count -gt 0) { throw "PowerShell parse error" }
}
Write-Output "PowerShell blocks parsed"
