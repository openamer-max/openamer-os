# Rendert Konsolen-Abbilder (kein Fenster noetig): Consolas, dunkler Hintergrund,
# Titelzeile wie ein Terminal. Der Text ist exakt der uebergebene — damit ist die
# Antwort im Trainingssatz belegbar.
param(
  [Parameter(Mandatory=$true)][string]$Cases,
  [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$list = Get-Content -Raw -Encoding UTF8 $Cases | ConvertFrom-Json
$made = 0

foreach ($c in $list) {
  $sizes = @(13, 14, 15, 16, 18)
  $fs = $sizes[$made % $sizes.Count]
  $font = New-Object System.Drawing.Font("Consolas", $fs, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
  $titleFont = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)

  $lines = @($c.lines)
  $lineH = [int]([math]::Ceiling($fs * 1.55))
  $width = 980
  $height = 40 + ($lines.Count + 2) * $lineH

  $bmp = New-Object System.Drawing.Bitmap($width, $height)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality

  # Hintergrund + Titelzeile
  $g.Clear([System.Drawing.Color]::FromArgb(12, 12, 12))
  $titleBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(32, 32, 32))
  $g.FillRectangle($titleBrush, 0, 0, $width, 30)
  $g.DrawString(("Eingabeaufforderung - " + $c.id), $titleFont, (New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(220, 220, 220))), 10, 7)

  # Prompt + Zeilen
  $y = 38
  $prompt = "C:\Users\amer7>" + $(if ($made % 2 -eq 0) { " " } else { " " })
  $g.DrawString($prompt, $font, (New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(200, 200, 200))), 10, $y)
  $y += $lineH
  foreach ($l in $lines) {
    $col = [System.Drawing.Color]::FromArgb(230, 230, 230)
    if ($l -match "FEHLER|fehlgeschlagen|fehlend|Error") { $col = [System.Drawing.Color]::FromArgb(255, 120, 120) }
    elseif ($l -match "ok$|ERFOLGREICH|bereit|erreichbar|gefunden") { $col = [System.Drawing.Color]::FromArgb(120, 230, 140) }
    elseif ($l -match "^(===|---)") { $col = [System.Drawing.Color]::FromArgb(140, 170, 255) }
    $g.DrawString($l, $font, (New-Object System.Drawing.SolidBrush($col)), 10, $y)
    $y += $lineH
  }
  $g.DrawString(("PS " + (Get-Location)), $font, (New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(120, 120, 120))), 10, $y)

  $out = Join-Path $OutDir ($c.id + ".png")
  $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose(); $font.Dispose(); $titleFont.Dispose()
  $made++
}
Write-Output ("GERENDERT: " + $made + " von " + @($list).Count)
