# export_all.ps1 -Root <drawing folder> -Out <tsv folder> [-Pattern <regex on file name>]
# Runs CtExport3 on each drawing -> <Out>/<name>.tsv (layer<TAB>kind<TAB>x,y ...; blocks as extents box + name).
param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Out, [string]$Pattern = '-DR-E-(2\d\d\d|3\d\d\d)\.dwg$')
$ErrorActionPreference = 'Continue'
$s = $PSScriptRoot; $root = $Root; $out = $Out; New-Item -ItemType Directory -Force $out | Out-Null
$app = [Runtime.InteropServices.Marshal]::GetActiveObject('Icad.Application')
$files = Get-ChildItem -Recurse $root -Include *.dwg | Where-Object { $_.Name -match $Pattern }
$loaded = $false
foreach ($f in $files) {
  $base = [IO.Path]::GetFileNameWithoutExtension($f.Name)
  $tsv = "$out\$base.tsv"
  if (Test-Path $tsv) { continue }
  $already = $null
  foreach ($d in $app.Documents) { if ($d.Name -ieq $f.Name) { $already = $d } }
  try {
    if ($already) { $doc = $already } else { $doc = $app.Documents.Open($f.FullName, $true) }
    $doc.Activate(); Start-Sleep 2
    if (-not $loaded) { $doc.SendCommand("(command `"NETLOAD`" `"$($s -replace '\\','/')/CtExport3.dll`")`n"); Start-Sleep 2; $loaded = $true }
    $doc.SendCommand("CTEXPORT3`n$tsv`n")
    $t = 0; while (-not (Test-Path $tsv) -and $t -lt 120) { Start-Sleep 1; $t++ }
    Start-Sleep 1
    "$base ok $((Get-Item $tsv -ErrorAction SilentlyContinue).Length)"
    if (-not $already) { $doc.Close($false) }
  } catch { "$base FAIL $($_.Exception.Message)" }
}
"DONE"
