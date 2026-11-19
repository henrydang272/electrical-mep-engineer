# Open each source DWG READ-ONLY and write a DXF copy into the scratch folder (source untouched).
# Closes only documents it opened.
param([string]$ListFile, [string]$OutDir)
$app = [Runtime.InteropServices.Marshal]::GetActiveObject('Icad.Application')
foreach ($f in Get-Content $ListFile) {
  if (-not $f.Trim()) { continue }
  $name = [IO.Path]::GetFileNameWithoutExtension($f); $out = Join-Path $OutDir ($name.Substring(0, [math]::Min(40, $name.Length)) + '.dxf')
  if (Test-Path $out) { "skip $name"; continue }
  $t0 = Get-Date
  try {
    $mine = $true; $doc = $null
    foreach ($d in $app.Documents) { if ($d.FullName -eq $f) { $doc = $d; $mine = $false } }
    if (-not $mine) { "SKIP (open by user) $name"; continue }
    $doc = $app.Documents.Open($f, $true)
    $doc.SaveAs($out)
    $doc.Close($false)
    "$name -> dxf $([int]((Get-Date) - $t0).TotalSeconds) s"
  } catch { "ERR $name : $_"; try { if ($doc) { $doc.Close($false) } } catch {} }
}
