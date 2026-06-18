param(
    [int]$Port = 9222
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$profileDir = Join-Path $scriptRoot '.browser-profile'
$markerPath = Join-Path $profileDir 'cdp-url.txt'
$cdpUrl = "http://127.0.0.1:$Port"

$candidateBrowsers = @(
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\Application\msedge.exe')
)

$browserPath = $candidateBrowsers | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $browserPath) {
    throw 'No supported Chrome or Edge executable was found on this machine.'
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
Set-Content -LiteralPath $markerPath -Value $cdpUrl -Encoding Ascii

$startUrls = @(
    'https://www.jd.com/',
    'https://www.taobao.com/',
    'https://www.xiaohongshu.com/'
)

$arguments = @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$profileDir",
    '--no-first-run',
    '--disable-features=AutomationControlled',
    '--lang=zh-CN'
) + $startUrls

Start-Process -FilePath $browserPath -ArgumentList $arguments

Write-Output "FITorNOT browser launched."
Write-Output "CDP URL: $cdpUrl"
Write-Output "Profile: $profileDir"
