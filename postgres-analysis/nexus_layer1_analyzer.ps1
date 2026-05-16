# Nexus Decision Provenance Engine - Layer 1 Analyzer
# Focus: MVCC, WAL, and Storage subsystems
# Analysis Window: 2 years from today

param(
    [string]$RepoPath = "postgres",
    [int]$AnalysisYears = 2,
    [int]$MinDPRs = 25
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Configuration
$TODAY = Get-Date
$CUTOFF_DATE = $TODAY.AddYears(-$AnalysisYears)
$CUTOFF_DATE_STR = $CUTOFF_DATE.ToString("yyyy-MM-dd")

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "NEXUS LAYER 1 - DECISION PROVENANCE ENGINE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Repository: PostgreSQL" -ForegroundColor White
Write-Host "Analysis Window: $AnalysisYears years (since $CUTOFF_DATE_STR)" -ForegroundColor White
Write-Host "Focus Areas: MVCC, WAL, Storage" -ForegroundColor White
Write-Host "Minimum DPRs: $MinDPRs" -ForegroundColor White
Write-Host ""

# Key directories to analyze
$FOCUS_DIRS = @(
    "src/backend/storage",
    "src/backend/access/heap",
    "src/backend/access/transam",
    "src/backend/access/rmgrdesc",
    "src/backend/commands",
    "src/include/storage",
    "src/include/access"
)

# Change to repo directory
Set-Location $RepoPath

Write-Host "STEP 1: Repository File Scan" -ForegroundColor Yellow
Write-Host "Indexing files in focus areas..." -ForegroundColor Gray

$allFiles = @()
foreach ($dir in $FOCUS_DIRS) {
    if (Test-Path $dir) {
        $files = Get-ChildItem -Path $dir -Recurse -File -Include *.c,*.h,README*,TODO*,HISTORY* -ErrorAction SilentlyContinue
        $allFiles += $files
        Write-Host "  $dir : $($files.Count) files" -ForegroundColor Gray
    }
}

Write-Host "STEP 1 COMPLETE - $($allFiles.Count) files indexed" -ForegroundColor Green
Write-Host ""

Write-Host "STEP 2: Git History Analysis" -ForegroundColor Yellow
Write-Host "Analyzing commits since $CUTOFF_DATE_STR..." -ForegroundColor Gray

# Get commits in the analysis window for focus areas
$commitLog = @()
foreach ($dir in $FOCUS_DIRS) {
    if (Test-Path $dir) {
        $commits = git log --since="$CUTOFF_DATE_STR" --pretty=format:"%H|%an|%ad|%s" --date=short -- $dir 2>$null
        if ($commits) {
            $commitLog += $commits
        }
    }
}

$uniqueCommits = $commitLog | Select-Object -Unique
Write-Host "STEP 2 COMPLETE - $($uniqueCommits.Count) commits analyzed" -ForegroundColor Green
Write-Host ""

Write-Host "STEP 3: Extracting Key Design Files" -ForegroundColor Yellow
Write-Host "Reading critical files with design decisions..." -ForegroundColor Gray

# Output file paths for analysis
$outputDir = "../output"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$keyFiles = @(
    "src/backend/storage/buffer/README",
    "src/backend/storage/page/README",
    "src/backend/access/heap/README.HOT",
    "src/backend/access/transam/README",
    "src/include/storage/bufmgr.h",
    "src/include/access/heapam.h",
    "src/include/access/xlog.h"
)

$designContent = @{}
foreach ($file in $keyFiles) {
    if (Test-Path $file) {
        $content = Get-Content $file -Raw -ErrorAction SilentlyContinue
        if ($content) {
            $designContent[$file] = $content
            Write-Host "  Read: $file ($($content.Length) bytes)" -ForegroundColor Gray
        }
    }
}

Write-Host "STEP 3 COMPLETE - $($designContent.Count) design files extracted" -ForegroundColor Green
Write-Host ""

# Export data for manual analysis
$analysisData = @{
    repository = "https://github.com/postgres/postgres"
    analysis_window = "$AnalysisYears years"
    cutoff_date = $CUTOFF_DATE_STR
    analysis_timestamp = $TODAY.ToString("yyyy-MM-dd HH:mm:ss")
    focus_areas = @("MVCC", "WAL", "Storage")
    files_indexed = $allFiles.Count
    commits_analyzed = $uniqueCommits.Count
    file_list = $allFiles | ForEach-Object { $_.FullName.Replace((Get-Location).Path + "\", "") }
    commit_summary = $uniqueCommits | Select-Object -First 50
    design_files = $designContent.Keys
}

$analysisData | ConvertTo-Json -Depth 10 | Out-File "$outputDir/analysis_metadata.json" -Encoding UTF8

Write-Host "Analysis metadata saved to: $outputDir/analysis_metadata.json" -ForegroundColor Cyan
Write-Host ""
Write-Host "Ready for manual DPR extraction phase..." -ForegroundColor Yellow

# Made with Bob
