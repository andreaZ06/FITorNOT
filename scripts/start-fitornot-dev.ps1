param(
  [string]$HostName = "127.0.0.1",
  [int]$FrontendPort = 3001,
  [int]$BackendPort = 8000
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackendDir = Join-Path $RepoRoot "review-pitfall-checker-v2"
$BackendUrl = "http://${HostName}:$BackendPort"
$ParentEnvPath = Join-Path (Split-Path (Split-Path $RepoRoot -Parent) -Parent) ".env"

function Import-DotEnvFile {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) {
    return
  }

  Get-Content -LiteralPath $Path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
      return
    }

    $separatorIndex = $line.IndexOf("=")
    if ($separatorIndex -lt 1) {
      return
    }

    $name = $line.Substring(0, $separatorIndex).Trim()
    $value = $line.Substring($separatorIndex + 1).Trim()

    if (
      ($value.StartsWith('"') -and $value.EndsWith('"')) -or
      ($value.StartsWith("'") -and $value.EndsWith("'"))
    ) {
      $value = $value.Substring(1, $value.Length - 2)
    }

    [Environment]::SetEnvironmentVariable($name, $value, "Process")
  }
}

function Assert-PortAvailable {
  param(
    [int]$Port,
    [string]$Label
  )

  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1

  if ($listener) {
    throw "$Label port $Port is already in use by process $($listener.OwningProcess). Stop that process or pass a different port."
  }
}

function New-FitOrNotJob {
  param(
    [string]$Name,
    [string]$WorkingDirectory,
    [string]$Command,
    [string[]]$Arguments
  )

  Start-Job -Name $Name -ScriptBlock {
    param(
      [string]$JobWorkingDirectory,
      [string]$JobCommand,
      [string[]]$JobArguments
    )

    Set-Location -LiteralPath $JobWorkingDirectory
    & $JobCommand @JobArguments
  } -ArgumentList $WorkingDirectory, $Command, $Arguments
}

function Test-HttpEndpoint {
  param([string]$Url)

  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
  } catch {
    return $false
  }
}

Import-DotEnvFile $ParentEnvPath
Import-DotEnvFile (Join-Path $RepoRoot ".env")

[Environment]::SetEnvironmentVariable("FITORNOT_API_BASE_URL", $BackendUrl, "Process")

if (-not $env:FITORNOT_ENABLE_BROWSER_AUTOMATION) {
  [Environment]::SetEnvironmentVariable("FITORNOT_ENABLE_BROWSER_AUTOMATION", "1", "Process")
}

if (
  -not $env:FITORNOT_BROWSER_CDP_URL -and
  (Test-HttpEndpoint "http://127.0.0.1:9222/json/version")
) {
  [Environment]::SetEnvironmentVariable("FITORNOT_BROWSER_CDP_URL", "http://127.0.0.1:9222", "Process")
}

if (-not $env:DEEPSEEK_API_KEY) {
  Write-Warning "DEEPSEEK_API_KEY is not set. The backend can start, but real decision generation may fail until the key is added to .env or your shell environment."
}

if (-not (Test-Path -LiteralPath (Join-Path $BackendDir "main.py"))) {
  throw "FITorNOT backend was not found at $BackendDir."
}

$pythonCommand = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
  throw "Python was not found on PATH. Install Python or start the backend manually."
}

Assert-PortAvailable -Port $FrontendPort -Label "Frontend"
Assert-PortAvailable -Port $BackendPort -Label "Backend"

$backendArguments = @(
  "-m",
  "uvicorn",
  "main:app",
  "--host",
  $HostName,
  "--port",
  "$BackendPort",
  "--reload"
)

$frontendArguments = @(
  "run",
  "dev",
  "--",
  "--hostname",
  $HostName,
  "--port",
  "$FrontendPort"
)

Write-Host "Starting FITorNOT local stack..."
Write-Host "Backend:  $BackendUrl"
Write-Host "Frontend: http://${HostName}:$FrontendPort/zh/fitornot"
Write-Host "Proxy:    FITORNOT_API_BASE_URL=$env:FITORNOT_API_BASE_URL"
Write-Host "Browser:  FITORNOT_ENABLE_BROWSER_AUTOMATION=$env:FITORNOT_ENABLE_BROWSER_AUTOMATION"
if ($env:FITORNOT_BROWSER_CDP_URL) {
  Write-Host "CDP:      FITORNOT_BROWSER_CDP_URL=$env:FITORNOT_BROWSER_CDP_URL"
}
Write-Host "Press Ctrl+C to stop both services."

$backendJob = New-FitOrNotJob `
  -Name "fitornot-backend" `
  -WorkingDirectory $BackendDir `
  -Command $pythonCommand.Source `
  -Arguments $backendArguments

$frontendJob = New-FitOrNotJob `
  -Name "fitornot-frontend" `
  -WorkingDirectory $RepoRoot `
  -Command "npm" `
  -Arguments $frontendArguments

$jobs = @($backendJob, $frontendJob)

try {
  while ($true) {
    foreach ($job in $jobs) {
      Receive-Job -Job $job

      if ($job.State -in @("Failed", "Stopped", "Completed")) {
        $reason = if ($job.ChildJobs[0].JobStateInfo.Reason) {
          $job.ChildJobs[0].JobStateInfo.Reason.Message
        } else {
          "The job exited with state $($job.State)."
        }

        throw "$($job.Name) stopped. $reason"
      }
    }

    Start-Sleep -Seconds 1
  }
} finally {
  foreach ($job in $jobs) {
    Stop-Job -Job $job -ErrorAction SilentlyContinue
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
  }
}
