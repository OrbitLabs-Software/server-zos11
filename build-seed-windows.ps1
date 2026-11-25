# zOS Server 2.0 - erzeugt unter Windows das Seed-ISO "zos-seed.iso"
# (Autoinstall-Konfiguration + zOS-Paket). Ohne WSL und ohne Zusatzprogramme:
# nutzt nur tar und IMAPI, beides ist in Windows 10/11 enthalten.
$ErrorActionPreference = 'Stop'
$here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$build = Join-Path $here 'build'
$seed  = Join-Path $build 'seed'
if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory $seed -Force | Out-Null

# 1) zOS-Paket packen und als Text einbetten
$tgz = Join-Path $build 'zos.tgz'
tar -czf $tgz -C $here shell core install.sh
if ($LASTEXITCODE) { throw 'tar ist fehlgeschlagen' }
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($tgz))

# 2) Autoinstall-Konfiguration (Benutzer und Festplatte waehlst du im Installer selbst)
$ud = @"
#cloud-config
autoinstall:
  version: 1
  locale: de_DE.UTF-8
  keyboard: {layout: de}
  identity: {hostname: zos, username: admin}
  ssh: {install-server: true}
  interactive-sections: [identity, storage]
  late-commands:
    - "mkdir -p /target/opt/zos-src"
    - "echo $b64 | base64 -d | tar -xzf - -C /target/opt/zos-src"
    - "curtin in-target --target=/target -- bash /opt/zos-src/install.sh"
"@
$ud = $ud -replace "`r`n", "`n"
$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText((Join-Path $seed 'user-data'), $ud + "`n", $utf8)
[IO.File]::WriteAllText((Join-Path $seed 'meta-data'), "instance-id: zos-seed`n", $utf8)

# 3) ISO mit dem Namen CIDATA schreiben (IMAPI ist Teil von Windows)
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class IsoWriter {
  public static void Write(string path, object stream, int blockSize, int totalBlocks) {
    IStream s = (IStream)stream;
    byte[] buf = new byte[blockSize];
    IntPtr p = Marshal.AllocHGlobal(4);
    try {
      using (FileStream o = File.Create(path)) {
        for (int i = 0; i < totalBlocks; i++) {
          s.Read(buf, blockSize, p);
          o.Write(buf, 0, blockSize);
        }
      }
    } finally { Marshal.FreeHGlobal(p); }
  }
}
'@
$fsi = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
$fsi.FileSystemsToCreate = 3
$fsi.VolumeName = 'CIDATA'
$fsi.Root.AddTree($seed, $false)
$res = $fsi.CreateResultImage()
$iso = Join-Path $build 'zos-seed.iso'
[IsoWriter]::Write($iso, $res.ImageStream, $res.BlockSize, $res.TotalBlocks)

Write-Host ''
Write-Host "Fertig: $iso"
Write-Host 'Naechster Schritt: Ubuntu-Server-ISO und dieses Seed-ISO als zwei DVD-Laufwerke in die VM einbinden.'
