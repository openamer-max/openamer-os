# Erzeugt echte Konsolen-Screenshots mit bekanntem Inhalt.
# Aufruf: powershell -File vision_capture.ps1 -Cases cases.json -OutDir <dir>
param(
  [Parameter(Mandatory=$true)][string]$Cases,
  [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$list = Get-Content -Raw -Encoding UTF8 $Cases | ConvertFrom-Json
$made = 0; $failed = @()

foreach ($c in $list) {
  $bat = Join-Path $env:TEMP ("vc_" + $c.id + ".bat")
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.AppendLine("@echo off")
  [void]$sb.AppendLine("title " + $c.id)
  [void]$sb.AppendLine("chcp 65001 >nul 2>&1")
  [void]$sb.AppendLine("mode con: cols=92 lines=" + ([int]$c.lines.Count + 4))
  foreach ($l in $c.lines) { [void]$sb.AppendLine("echo " + $l) }
  [void]$sb.AppendLine("ping -n 30 127.0.0.1 >nul")
  [System.IO.File]::WriteAllText($bat, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))

  $p = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$bat`"" -PassThru -WindowStyle Normal
  $h = [IntPtr]::Zero
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 150
    $p.Refresh()
    if ($p.MainWindowHandle -ne 0) { $h = $p.MainWindowHandle; break }
  }
  if ($h -eq [IntPtr]::Zero) { $failed += "$($c.id):kein Fenster"; Stop-Process -Id $p.Id -Force -EA SilentlyContinue; continue }

  [void][W]::ShowWindow($h, 9)
  Start-Sleep -Milliseconds 400
  [void][W]::SetForegroundWindow($h)
  Start-Sleep -Milliseconds 500

  $r = New-Object W+RECT
  [void][W]::GetWindowRect($h, [ref]$r)
  $w = $r.Right - $r.Left; $hh = $r.Bottom - $r.Top
  if ($w -lt 200 -or $hh -lt 100) { $failed += "$($c.id):Fenstergroesse ${w}x${hh}"; Stop-Process -Id $p.Id -Force -EA SilentlyContinue; continue }

  $bmp = New-Object System.Drawing.Bitmap($w, $hh)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
  $out = Join-Path $OutDir ($c.id + ".png")
  $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Stop-Process -Id $p.Id -Force -EA SilentlyContinue
  Remove-Item $bat -Force -EA SilentlyContinue
  $made++
  Start-Sleep -Milliseconds 200
  if (($made % 10) -eq 0) { Write-Output ("  " + $made + " Bilder") }
}
Write-Output ("FERTIG: " + $made + " von " + @($list).Count)
if ($failed.Count -gt 0) { Write-Output ("FEHLER: " + ($failed -join ", ")) }
