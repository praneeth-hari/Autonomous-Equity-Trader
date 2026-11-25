# check_all.ps1 - the project's pre-push gate. Runs every check in order and stops at the first failure.
#
#   powershell -ExecutionPolicy Bypass -File .\check_all.ps1
#
# Order: secret scan, lint, dependency audit, environment check, Python tests, web build, web tests, browser tests.
# The same steps run on GitHub for every push (see .github/workflows/tests.yml).

Set-Location $PSScriptRoot
$py = if (Test-Path '.\.venv\Scripts\python.exe') { '.\.venv\Scripts\python.exe' } else { 'python' }

function Step([string]$Name, [scriptblock]$Run) {
    Write-Host ""
    Write-Host "== $Name" -ForegroundColor Cyan
    & $Run
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Name" -ForegroundColor Red
        exit 1
    }
}

Step 'Secret scan'       { & $py -m src.ops.secret_scan }
Step 'Lint (real-bug rules)' { & $py -m ruff check }
Step 'Dependency audit'     { & $py -m pip_audit --progress-spinner off }
if (Get-Command gitleaks -ErrorAction SilentlyContinue) {
    Step 'gitleaks'         { gitleaks detect --no-banner --config .gitleaks.toml }
} else {
    Write-Host "(gitleaks is not installed, so only the built-in secret scan ran. GitHub runs gitleaks on every push.)" -ForegroundColor DarkYellow
}
Step 'Environment check' { & $py -m src.ops.envcheck }
Step 'Python tests'      { & $py -m pytest -q -p no:cacheprovider }
Push-Location web
Step 'Web build'         { npm run build }
Step 'Web tests'         { npm test }
Step 'Browser tests'     { npm run e2e }
Pop-Location

Write-Host ""
Write-Host "ALL CHECKS PASSED" -ForegroundColor Green
