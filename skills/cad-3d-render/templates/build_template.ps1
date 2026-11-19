# TEMPLATE - copy next to the project's 3D Models folder, rename (e.g. build_<bldg>.ps1), fill the DATA block.
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File build_<bldg>.ps1 -OutFile "C:\...\<bldg>_3D.dwg"
# Full worked example: ..\examples\17B\build17b.ps1
param([Parameter(Mandatory=$true)][string]$OutFile)
. "$env:USERPROFILE\.claude\skills\cad-3d-render\scripts\progecad3d_lib.ps1"

New-Model -Layers ([ordered]@{
  'A-SLAB'=8; 'A-SITE-RAMP'=9; 'S-COLS'=5; 'S-RAFTER'=5; 'A-WALL-CMU'=254; 'A-WALL-CLAD'=151;
  'A-WALL-MESH'=7; 'A-DOOR'=30; 'A-GLAZ-LOUVRE'=140; 'A-ROOF'=152; 'A-GENM'=6; 'A-ANNO'=2;
  'E-LITE-FIXT'=1; 'E-LITE-ROD'=8; 'E-LITE-SWCH'=3; 'E-POWR-DB'=4 }) -WallLayers @('A-WALL-CMU','A-WALL-CLAD')

# ================= DATA (all mm, local origin = first grid / grid A) =================
$L = 72000; $W = 10000                      # building length (X) and width (Y) between outer grids
$gx = @(0,6000,12000)                       # grid X positions from the plan
$wallT = 200; $baseH = 1200                 # perimeter wall thickness, masonry base height
$roofTop = 5960; $roofHiY = 11550
Set-MonoRoof -HighY $roofHiY -TopZ $roofTop -Slope 0.05  # from sections: RFL, slope, high edge incl. overhang
$roofLoY = -2000; $sheet = 100; $rafterD = 450
$fixtures = @()                             # @(x,y) from INS lines of the lighting DWG
$mountH = 4500                              # luminaire mounting height from the drawing note (H=...)
# ================================================================================

Box 0 0 -150 $L $W 0 'A-SLAB' | Out-Null
$roofS = Box -300 $roofLoY ($roofTop-$sheet) ($L+300) $roofHiY $roofTop 'A-ROOF'; Tilt $roofS
foreach($x in $gx){
  $xc=[math]::Min([math]::Max($x,150),$L-150)
  $rf = Box ($xc-100) $roofLoY ($roofTop-$sheet-$rafterD) ($xc+100) $roofHiY ($roofTop-$sheet) 'S-RAFTER'; Tilt $rf
  foreach($yc in @(100,($W-100))){ $c = Box ($xc-150) ($yc-100) 0 ($xc+150) ($yc+100) 7000 'S-COLS'; CutAboveRoof $c ($sheet+$rafterD) }
}
foreach($wy in @(@(0,$wallT),@(($W-$wallT),$W))){
  Box 0 $wy[0] 0 $L $wy[1] $baseH 'A-WALL-CMU' | Out-Null
  $c = Box 0 $wy[0] $baseH $L $wy[1] 7000 'A-WALL-CLAD'; CutAboveRoof $c $sheet
}
# Openings AFTER all walls exist:  Opening x1 y1 z1 x2 y2 z2 'A-DOOR' 60
foreach($f in $fixtures){
  $x=$f[0]; $y=$f[1]
  Box ($x-40) ($y-600) $mountH ($x+40) ($y+600) ($mountH+90) 'E-LITE-FIXT' | Out-Null    # 1200 batten along Y - check symbol orientation!
  $rod = Box ($x-6) ($y-6) ($mountH+90) ($x+6) ($y+6) 7000 'E-LITE-ROD'; CutAboveRoof $rod $sheet
}
Save-Model $OutFile
