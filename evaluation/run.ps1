param([ValidateSet("local","deployed","both")][string]$Target = "local")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
if (!(Test-Path $python)) { throw "Project virtual environment not found." }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$targets = if ($Target -eq "both") { @("local","deployed") } else { @($Target) }
foreach ($name in $targets) {
    $out = Join-Path $PSScriptRoot "results\$name"
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    $results = [System.Collections.Generic.List[object]]::new()
    function Add-Result($test,$status,$seconds,$details) {
        $results.Add([pscustomobject]@{test=$test;status=$status;duration_seconds=[math]::Round($seconds,3);details=$details})
    }
    Write-Host "`n========== DOOM EVALUATION: $name ==========" -ForegroundColor Cyan
    $timer = [Diagnostics.Stopwatch]::StartNew()
    & $python -m compileall -q src
    $timer.Stop()
    Add-Result "compileall" $(if($LASTEXITCODE -eq 0){"PASS"}else{"FAIL"}) $timer.Elapsed.TotalSeconds "Python source compilation"
    if ($LASTEXITCODE -ne 0) { throw "Compilation failed." }
    $timer.Restart()
    & $python -m pytest -q --tb=short
    $pytestExit = $LASTEXITCODE
    $timer.Stop()
    Add-Result "pytest" $(if($pytestExit -eq 0){"PASS"}else{"FAIL"}) $timer.Elapsed.TotalSeconds "Existing automated test suite"
    $timer.Restart()
    git diff --check
    $gitExit = $LASTEXITCODE
    $timer.Stop()
    Add-Result "git_diff_check" $(if($gitExit -eq 0){"PASS"}else{"FAIL"}) $timer.Elapsed.TotalSeconds "Whitespace and patch validation"
    $timer.Restart()
    & $python -c "from src.tools.registry import TOOLS; from src.tools.mcp_server import registered_mcp_tool_names; names=registered_mcp_tool_names(); assert len(TOOLS)==26 and len(names)==26 and set(names)==set(TOOLS); print('Registered MCP tools:',len(names))"
    $mcpExit = $LASTEXITCODE
    $timer.Stop()
    Add-Result "mcp_registry" $(if($mcpExit -eq 0){"PASS"}else{"FAIL"}) $timer.Elapsed.TotalSeconds "MCP registration count and registry consistency"
    $file = Join-Path $out "evaluation_$stamp"
    $results | Export-Csv "$file.csv" -NoTypeInformation -Encoding UTF8
    $results | ConvertTo-Json -Depth 5 | Set-Content "$file.json" -Encoding UTF8
    $passed = @($results | Where-Object status -eq "PASS").Count
    $failed = @($results | Where-Object status -eq "FAIL").Count
    $lines = @("# DOOM Evaluation Report","", "- Target: $name","- Timestamp: $stamp","- Passed checks: $passed","- Failed checks: $failed","", "| Check | Status | Duration (s) | Details |","|---|---:|---:|---|")
    foreach ($r in $results) { $lines += "| $($r.test) | $($r.status) | $($r.duration_seconds) | $($r.details) |" }
    $lines | Set-Content "$file.md" -Encoding UTF8
    Write-Host "`nResults: $passed passed, $failed failed" -ForegroundColor $(if($failed){"Red"}else{"Green"})
    Write-Host "Reports: $file.json | .csv | .md"
    if ($pytestExit -ne 0 -or $gitExit -ne 0 -or $mcpExit -ne 0) { throw "Evaluation failed. Inspect the generated reports." }
}
