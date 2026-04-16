param(
    [string]$Message = "",
    [switch]$DryRun,
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $display = "git " + ($Args -join " ")
    if ($DryRun) {
        Write-Host "[DryRun] $display" -ForegroundColor Yellow
        return
    }

    & git @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $display"
    }
}

try {
    $repoRoot = (& git rev-parse --show-toplevel).Trim()
    if (-not $repoRoot) {
        throw "Could not determine git repository root."
    }

    Set-Location $repoRoot
    Write-Step "Repository"
    Write-Host $repoRoot

    $statusLines = @(& git status --short)
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read git status."
    }

    if ($statusLines.Count -eq 0) {
        Write-Host "No local changes to publish." -ForegroundColor Green
        exit 0
    }

    Write-Step "Pending changes"
    $statusLines | ForEach-Object { Write-Host $_ }

    $branch = (& git branch --show-current).Trim()
    if (-not $branch) {
        throw "Could not determine the current branch."
    }

    $upstream = (& git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null).Trim()
    if ($LASTEXITCODE -ne 0) {
        $upstream = ""
    }

    if (-not $Message) {
        Write-Host ""
        $Message = Read-Host "Enter commit message"
    }

    $Message = $Message.Trim()
    if (-not $Message) {
        throw "Commit message cannot be empty."
    }

    Write-Step "Review"
    Write-Host "Branch : $branch"
    if ($upstream) {
        Write-Host "Upstream: $upstream"
    }
    else {
        Write-Host "Upstream: <none>"
    }
    Write-Host "Message: $Message"
    if ($DryRun) {
        Write-Host "Mode   : DryRun" -ForegroundColor Yellow
    }

    $confirm = Read-Host "Continue with stage -> commit -> push? (y/N)"
    if ($confirm.Trim().ToLower() -notin @("y", "yes")) {
        Write-Host "Cancelled." -ForegroundColor Yellow
        exit 1
    }

    Write-Step "Stage files"
    Invoke-Git -Args @("add", "-A")

    Write-Step "Commit"
    Invoke-Git -Args @("commit", "-m", $Message)

    Write-Step "Push"
    if ($upstream) {
        Invoke-Git -Args @("push")
    }
    else {
        Invoke-Git -Args @("push", "-u", "origin", $branch)
    }

    Write-Host ""
    if ($DryRun) {
        Write-Host "Dry run completed." -ForegroundColor Green
    }
    else {
        Write-Host "Publish completed successfully." -ForegroundColor Green
    }
}
catch {
    Write-Host ""
    Write-Host "Publish failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if (-not $NoPause) {
        Write-Host ""
        Read-Host "Press Enter to close"
    }
}
