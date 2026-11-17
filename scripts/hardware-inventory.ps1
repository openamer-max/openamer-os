# Erfasst die echte Hardware dieses PCs mit Vendor/Device-IDs.
# Aufruf:  powershell -NoProfile -File hardware-inventory.ps1
# Ausgabe: CSV (Klasse,Name,InstanceId) auf stdout

Get-PnpDevice -PresentOnly |
    Where-Object { $_.InstanceId -match '^(PCI|USB|ACPI|BTH|SWD)' } |
    ForEach-Object {
        $parts = $_.InstanceId -split '\\'
        $short = if ($parts.Length -ge 2) { $parts[0] + '\' + $parts[1] } else { $parts[0] }
        [PSCustomObject]@{
            Klasse = $_.Class
            Name   = $_.FriendlyName
            Id     = $short
        }
    } |
    Sort-Object Klasse, Name -Unique |
    ConvertTo-Csv -NoTypeInformation
