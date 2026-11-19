# Dump geometry of an OPEN progeCAD drawing to a pipe-separated text file, in LOCAL mm
# coordinates (origin = the grid intersection you choose, e.g. first grid / grid A).
#
# usage: powershell -NoProfile -ExecutionPolicy Bypass -File dwg_extract.ps1 `
#          -DocLike "*E-2000*" -OriginX -269754.4 -OriginY 151936.9 -Out C:\...\dump.txt `
#          [-Block "PRJ-...rvt-1-LIGHTING LAYOUT FOR 17B"] [-Layers "A-WALL,A-FLOR"]
#
# Lines written:
#   INS|layer|blockName|x|y|rotDeg|xScale          model-space block inserts (fixtures, doors, grid bubbles...)
#   GRID|x1|y1|x2|y2                               lines on layers matching *GRID*
#   TXT|layer|text|x|y                             MText/Text (room names, ISW, DB tags, levels)
#   BL|layer|x1|y1|x2|y2                           lines inside -Block (filtered by -Layers if given)
#   BB|layer|blockName|x|y|rotDeg|xs|ys            inserts inside -Block (doors, windows, louvres, curtain panels)
#   BP|layer|x,y x,y ...                           LW polylines inside -Block
# Find the origin first: run once with -OriginX 0 -OriginY 0 and read the GRID lines.
param(
  [Parameter(Mandatory=$true)][string]$DocLike,
  [double]$OriginX = 0, [double]$OriginY = 0,
  [Parameter(Mandatory=$true)][string]$Out,
  [string]$Block = '', [string]$Layers = ''
)
$ErrorActionPreference = 'Stop'
$app = [Runtime.InteropServices.Marshal]::GetActiveObject('Icad.Application')
$doc = $null; foreach ($d in $app.Documents) { if ($d.Name -like $DocLike) { $doc = $d } }
if (-not $doc) { throw "No open document matches $DocLike" }
$R = { param($v) [math]::Round([double]$v, 1) }
# IMPORTANT: progeCAD COM points are objects -> use .X/.Y, never [0]/[1]
$o = New-Object System.Collections.Generic.List[string]
foreach ($e in $doc.ModelSpace) {
  switch ($e.EntityName) {
    'BlockInsert' { $p = $e.InsertionPoint; $o.Add("INS|$($e.Layer)|$($e.Name)|$(& $R ($p.X-$OriginX))|$(& $R ($p.Y-$OriginY))|$(& $R ($e.Rotation*180/[math]::PI))|$($e.XScaleFactor)") }
    'Line' { if ($e.Layer -like '*GRID*') { $a = $e.StartPoint; $b = $e.EndPoint; $o.Add("GRID|$(& $R ($a.X-$OriginX))|$(& $R ($a.Y-$OriginY))|$(& $R ($b.X-$OriginX))|$(& $R ($b.Y-$OriginY))") } }
    { $_ -in 'Mtext','Text' } { $p = $e.InsertionPoint; $o.Add("TXT|$($e.Layer)|$(($e.TextString -replace '\s+',' '))|$(& $R ($p.X-$OriginX))|$(& $R ($p.Y-$OriginY))") }
  }
}
if ($Block) {
  $lay = @(); if ($Layers) { $lay = $Layers.Split(',') | ForEach-Object { $_.Trim() } }
  foreach ($e in $doc.Blocks.Item($Block)) {
    if ($lay.Count -and ($e.Layer -notin $lay) -and $e.EntityName -eq 'Line') { continue }
    switch ($e.EntityName) {
      'Line' { $a = $e.StartPoint; $b = $e.EndPoint; $o.Add("BL|$($e.Layer)|$(& $R ($a.X-$OriginX))|$(& $R ($a.Y-$OriginY))|$(& $R ($b.X-$OriginX))|$(& $R ($b.Y-$OriginY))") }
      'BlockInsert' { $p = $e.InsertionPoint; $o.Add("BB|$($e.Layer)|$($e.Name)|$(& $R ($p.X-$OriginX))|$(& $R ($p.Y-$OriginY))|$(& $R ($e.Rotation*180/[math]::PI))|$($e.XScaleFactor)|$($e.YScaleFactor)") }
      'LightWeightPolyline' { $s = @(); foreach ($q in $e.Coordinates) { $s += "$(& $R ($q.X-$OriginX)),$(& $R ($q.Y-$OriginY))" }; $o.Add("BP|$($e.Layer)|$($s -join ' ')") }
    }
  }
}
[IO.File]::WriteAllLines($Out, $o)
"wrote $($o.Count) lines to $Out"
