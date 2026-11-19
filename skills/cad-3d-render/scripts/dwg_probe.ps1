# Open a DWG in progeCAD (COM "Icad.Application") and summarise what is inside.
# usage: powershell -NoProfile -ExecutionPolicy Bypass -File dwg_probe.ps1 "C:\full\path\file.dwg"
# Prints: entity counts by type|layer|block name (model space), then the content of every
# block whose name looks like a Revit/arch background (*rvt*, *M3-A*, xref-like) so you can
# see where walls / doors / windows live.
# NOTE: opens the drawing READ-ONLY in intent - never call Save on a source drawing.
param([Parameter(Mandatory=$true)][string]$File, [int]$Top = 60)
$ErrorActionPreference = 'Stop'
try { $app = [Runtime.InteropServices.Marshal]::GetActiveObject('Icad.Application') }
catch { $app = New-Object -ComObject Icad.Application }
$app.Visible = $true
$doc = $null
foreach ($d in $app.Documents) { if ($d.FullName -eq $File) { $doc = $d } }
if (-not $doc) { $doc = $app.Documents.Open($File) }
"DOC: $($doc.Name)   modelspace entities: $($doc.ModelSpace.Count)"
$h = @{}
foreach ($e in $doc.ModelSpace) {
  $k = $e.EntityName + '|' + $e.Layer
  if ($e.EntityName -eq 'BlockInsert') { $k += '|' + $e.Name }
  $h[$k] = 1 + $h[$k]
}
$h.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First $Top | ForEach-Object { "{0,6}  {1}" -f $_.Value, $_.Key }

$bgNames = @()
foreach ($e in $doc.ModelSpace) { if ($e.EntityName -eq 'BlockInsert' -and $e.Name -match 'rvt|M3-A|xref|ARCH|BACKGROUND') { $bgNames += $e.Name } }
foreach ($bn in ($bgNames | Select-Object -Unique)) {
  $blk = $doc.Blocks.Item($bn); $b = @{}
  foreach ($e in $blk) { $k = $e.EntityName + '|' + $e.Layer; if ($e.EntityName -eq 'BlockInsert') { $k += '|' + $e.Name }; $b[$k] = 1 + $b[$k] }
  ""; "BACKGROUND BLOCK: $bn  ($($blk.Count) entities)"
  $b.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First $Top | ForEach-Object { "{0,6}  {1}" -f $_.Value, $_.Key }
}
