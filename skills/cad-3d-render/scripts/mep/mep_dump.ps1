# Batch dump of MEP/ARC drawings (READ-ONLY). For each file: model-space entities + content of
# Revit link blocks inserted in model space. Coordinates in drawing units (mm), block content
# transformed by the insert (assumed scale 1 / rotation 0 - Revit links are inserted at 0,0).
# Closes ONLY the documents it opened.
param([string]$ListFile, [string]$OutDir)
$app = [Runtime.InteropServices.Marshal]::GetActiveObject('Icad.Application')
$R = { param($v) [math]::Round([double]$v, 3) }
function Dump($ents, $tag, $dx, $dy, $o, [ref]$depth) {
  foreach ($e in $ents) {
    $L = $e.Layer
    switch ($e.EntityName) {
      'BlockInsert' { $p = $e.InsertionPoint; $o.Add("I|$tag|$L|$($e.Name)|$(& $R ($p.X+$dx))|$(& $R ($p.Y+$dy))|$(& $R ($p.Z))|$([math]::Round($e.Rotation*180/[math]::PI,1))|$([math]::Round($e.XScaleFactor,3))|$([math]::Round($e.YScaleFactor,3))") }
      'Line' { $a = $e.StartPoint; $b = $e.EndPoint; $o.Add("L|$tag|$L|$(& $R ($a.X+$dx))|$(& $R ($a.Y+$dy))|$(& $R ($b.X+$dx))|$(& $R ($b.Y+$dy))") }
      'LightWeightPolyline' { $s = @(); foreach ($q in $e.Coordinates) { $s += "$(& $R ($q.X+$dx)),$(& $R ($q.Y+$dy))" }; $o.Add("P|$tag|$L|$([int]$e.Closed)|$($s -join ' ')") }
      'Circle' { $c = $e.Center; $o.Add("C|$tag|$L|$(& $R ($c.X+$dx))|$(& $R ($c.Y+$dy))|$(& $R $e.Radius)") }
      'Arc' { $c = $e.Center; $o.Add("A|$tag|$L|$(& $R ($c.X+$dx))|$(& $R ($c.Y+$dy))|$(& $R $e.Radius)|$([math]::Round($e.StartAngle,3))|$([math]::Round($e.EndAngle,3))") }
      { $_ -in 'Mtext','Text' } { $p = $e.InsertionPoint; $o.Add("T|$tag|$L|$(($e.TextString -replace '\s+',' ' -replace '\|','/'))|$(& $R ($p.X+$dx))|$(& $R ($p.Y+$dy))|$([math]::Round($e.Height,0))") }
    }
  }
}
foreach ($f in Get-Content $ListFile) {
  if (-not $f.Trim()) { continue }
  $name = [IO.Path]::GetFileNameWithoutExtension($f); $out = Join-Path $OutDir ($name.Substring(0, [math]::Min(40, $name.Length)) + '.txt')
  if (Test-Path $out) { "skip $name"; continue }
  $t0 = Get-Date
  try {
    $doc = $null; $mine = $true
    foreach ($d in $app.Documents) { if ($d.FullName -eq $f) { $doc = $d; $mine = $false } }   # already open by the user: read only, never close
    if (-not $doc) { $doc = $app.Documents.Open($f, $true) }
    $o = New-Object Collections.Generic.List[string]
    Dump $doc.ModelSpace 'MS' 0 0 $o ([ref]0)
    $seen = @{}
    foreach ($e in @($doc.ModelSpace)) {
      if ($e.EntityName -eq 'BlockInsert' -and $e.Name -match 'rvt' -and -not $seen.ContainsKey($e.Name)) {
        $seen[$e.Name] = 1; $p = $e.InsertionPoint
        $o.Add("B|$($e.Name)|$(& $R $p.X)|$(& $R $p.Y)|$($e.Rotation)|$($e.XScaleFactor)")
        Dump $doc.Blocks.Item($e.Name) ('RVT:' + $e.Name) $p.X $p.Y $o ([ref]0)
      }
    }
    [IO.File]::WriteAllLines($out, $o)
    if ($mine) { $doc.Close($false) }
    "$name : $($o.Count) lines, $([int]((Get-Date) - $t0).TotalSeconds) s"
  } catch { "ERR $name : $_"; try { if ($mine -and $doc) { $doc.Close($false) } } catch {} }
}
