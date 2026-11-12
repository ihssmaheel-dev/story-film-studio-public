param([Parameter(ValueFromRemainingArguments=$true)][string[]]$StudioArgs)
$studioRoot = $PSScriptRoot
$studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $studioPython)) {
    throw 'Local environment missing. Run tools/setup_studio.py with an available Python 3.12 interpreter first.'
}
& $studioPython -B -X utf8 (Join-Path $studioRoot 'tools\studio.py') @StudioArgs
exit $LASTEXITCODE
