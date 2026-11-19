# Reusable progeCAD (IntelliCAD COM) 3D-solid helpers. Dot-source it from a build script:
#   . "$env:USERPROFILE\.claude\skills\cad-3d-render\scripts\progecad3d_lib.ps1"
#   New-Model -Layers ([ordered]@{ 'A-SLAB'=8; 'E-LITE-FIXT'=1 })
#   Set-MonoRoof -HighY 11550 -TopZ 5960 -Slope 0.05      # optional, mono-pitch roof falling to -Y
#   Box 0 0 -150 72000 10000 0 'A-SLAB'
#   ...
#   Save-Model "C:\...\Model_3D.dwg"
# Units: mm. Model coords: X along the long grid, Y across, Z up, FFL = 0.
#
# Hard-won rules baked in here (do not "simplify" them away):
#  * every numeric param is [double]  - PowerShell passes bare -400 as a STRING and "a"+"b" concatenates
#  * points are made with $lib.CreatePoint(x,y,z) - never PowerShell arrays
#  * GetBoundingBox() does NOT work through this COM -> wall extents are recorded by Box itself
#  * Boolean(2, cutter) leaves an EMPTY solid on layer 0 per cut -> Save-Model deletes them
#  * variable names are case-insensitive: never name a variable $N/$S if $n/$s exists
#  * Color: set colours on layers (Layer.Color.ColorIndex), entity .Color throws

$ErrorActionPreference = 'Stop'
try { $script:app = [Runtime.InteropServices.Marshal]::GetActiveObject('Icad.Application') }
catch { $script:app = New-Object -ComObject Icad.Application }   # starts progeCAD if it is closed
$script:app.Visible = $true
$script:lib = $script:app.Library
$script:count = @{}; $script:wallExt = @(); $script:wallLayers = @('A-WALL-CMU','A-WALL-CLAD','A-WALL')
$script:roof = $null

function P([double]$x,[double]$y,[double]$z){ $script:lib.CreatePoint($x,$y,$z) }

function New-Model([System.Collections.IDictionary]$Layers, [string[]]$WallLayers){
  $script:doc = $script:app.Documents.Add(); $script:ms = $script:doc.ModelSpace
  foreach($k in $Layers.Keys){ $l = $script:doc.Layers.Add($k); try { $l.Color.ColorIndex = $Layers[$k] } catch {} }
  if($WallLayers){ $script:wallLayers = $WallLayers }
  try { $script:doc.SetVariable('INSUNITS',4) } catch {}
}

function Box([double]$x1,[double]$y1,[double]$z1,[double]$x2,[double]$y2,[double]$z2,[string]$layer){
  $lx=[math]::Abs($x2-$x1); $ly=[math]::Abs($y2-$y1); $lz=[math]::Abs($z2-$z1)
  if($lx -lt 1 -or $ly -lt 1 -or $lz -lt 1){ return $null }
  $b = $script:ms.AddBox((P (($x1+$x2)/2) (($y1+$y2)/2) (($z1+$z2)/2)), $lx, $ly, $lz)
  $b.Layer = $layer; $script:count[$layer] = 1 + $script:count[$layer]
  if($layer -in $script:wallLayers){
    $script:wallExt += ,@($b,[math]::Min($x1,$x2),[math]::Min($y1,$y2),[math]::Min($z1,$z2),[math]::Max($x1,$x2),[math]::Max($y1,$y2),[math]::Max($z1,$z2))
  }
  return $b
}

function Cut($solid,[double]$x1,[double]$y1,[double]$z1,[double]$x2,[double]$y2,[double]$z2){
  $c = $script:ms.AddBox((P (($x1+$x2)/2) (($y1+$y2)/2) (($z1+$z2)/2)), [math]::Abs($x2-$x1), [math]::Abs($y2-$y1), [math]::Abs($z2-$z1))
  $solid.Boolean(2, $c)   # 2 = subtraction
}

# ---- mono-pitch roof: top surface z(y) = TopZ - (HighY - y)*Slope (falls towards -Y) ----
function Set-MonoRoof([double]$HighY,[double]$TopZ,[double]$Slope){ $script:roof = @{ HighY=$HighY; TopZ=$TopZ; Slope=$Slope; Alpha=[math]::Atan($Slope) } }
function RoofTopZ([double]$y){ $r=$script:roof; $r.TopZ - ($r.HighY - $y)*$r.Slope }
# rotate a flat-built solid about the roof hinge (X axis through y=HighY, z=TopZ)
# progeCAD Rotate3D ALWAYS turns about an axis through the ORIGIN (the points only give the direction),
# so Rot3D moves the pivot to the origin, rotates, moves back.
function Tilt($s){ $r=$script:roof; Rot3D $s (P 0 $r.HighY $r.TopZ) 1 0 0 $r.Alpha }
# rotate solid $s by $ang (radians, right-hand rule) about axis direction (ax,ay,az) through point $pivot
function Rot3D($s,$pivot,[double]$ax,[double]$ay,[double]$az,[double]$ang){
  $o = P 0 0 0
  $s.Move($pivot,$o); $s.Rotate3D($o,(P ($ax*1000) ($ay*1000) ($az*1000)),$ang); $s.Move($o,$pivot)
}
# remove everything above a plane parallel to the roof, $Drop mm below the roof top surface
function CutAboveRoof($s,[double]$Drop,[double]$XMin=-5000,[double]$XMax=200000){
  $r=$script:roof
  $c = $script:ms.AddBox((P (($XMin+$XMax)/2) ($r.HighY-15000) ($r.TopZ - $Drop + 2000)), ($XMax-$XMin), 60000, 4000)
  Tilt $c; $s.Boolean(2,$c)
}

# ---- opening through any recorded wall solid + optional panel (door leaf, shutter, louvre) ----
function Opening([double]$x1,[double]$y1,[double]$z1,[double]$x2,[double]$y2,[double]$z2,[string]$panelLayer,[double]$panelThk){
  foreach($we in $script:wallExt){
    if($x1 -lt $we[4] -and $x2 -gt $we[1] -and $y1 -lt $we[5] -and $y2 -gt $we[2] -and $z1 -lt $we[6] -and $z2 -gt $we[3]){ Cut $we[0] $x1 $y1 $z1 $x2 $y2 $z2 }
  }
  if($panelLayer){
    if(($x2-$x1) -gt ($y2-$y1)){ $ym=($y1+$y2)/2; Box $x1 ($ym-$panelThk/2) $z1 $x2 ($ym+$panelThk/2) $z2 $panelLayer | Out-Null }
    else { $xm=($x1+$x2)/2; Box ($xm-$panelThk/2) $y1 $z1 ($xm+$panelThk/2) $y2 $z2 $panelLayer | Out-Null }
  }
}

function Add-Label([string]$text,[double]$x,[double]$y,[double]$z,[double]$h,[string]$layer){ $t=$script:ms.AddText($text,(P $x $y $z),$h); $t.Layer=$layer }

function Save-Model([string]$OutFile){
  # delete empty cutter remnants left on layer 0 by Boolean()
  $del=@(); foreach($e in $script:ms){ if($e.Layer -eq '0' -and $e.EntityName -eq '3dSolid'){ $del+=$e } }
  foreach($e in $del){ $e.Delete() }
  $script:doc.SaveAs($OutFile)
  "saved $OutFile  (removed $($del.Count) empty cutters, $($script:ms.Count) entities)"
  $script:count.GetEnumerator() | Sort-Object Name | ForEach-Object { "{0,-18} {1}" -f $_.Name,$_.Value }
}
