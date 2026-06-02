# Publica a versao atual no GitHub Releases (cria a release + sobe os 3 arquivos
# que o auto-update usa). Le a versao do electron/package.json e usa o token ja
# salvo no Git Credential Manager (mesmo do git push) — nao precisa configurar nada.
#
# Uso:  pwsh -File publicar-release.ps1   (ou clicar com botao direito > Executar)
# Pre-requisito: ter rodado o build (CONSTRUIR_INSTALADOR.bat) gerando electron\dist.
$ErrorActionPreference = 'Stop'
$repo = "snapzin/CONX_NFSE_AUTOMA-O"

# --- versao ---
$pkg = Get-Content (Join-Path $PSScriptRoot "electron\package.json") -Raw | ConvertFrom-Json
$ver = $pkg.version
$tag = "v$ver"
"Publicando $tag ..."

# --- token (do Git Credential Manager) ---
$sig = @"
using System;using System.Runtime.InteropServices;
public class Cred{
[StructLayout(LayoutKind.Sequential)]public struct CREDENTIAL{public uint Flags;public uint Type;public IntPtr TargetName;public IntPtr Comment;public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;public uint CredentialBlobSize;public IntPtr CredentialBlob;public uint Persist;public uint AttributeCount;public IntPtr Attributes;public IntPtr TargetAlias;public IntPtr UserName;}
[DllImport("advapi32.dll",SetLastError=true,CharSet=CharSet.Unicode)]public static extern bool CredRead(string t,uint y,uint f,out IntPtr c);
public static string ReadB64(string t){IntPtr p;if(!CredRead(t,1,0,out p))return null;var c=(CREDENTIAL)Marshal.PtrToStructure(p,typeof(CREDENTIAL));byte[] b=new byte[c.CredentialBlobSize];Marshal.Copy(c.CredentialBlob,b,0,(int)c.CredentialBlobSize);return Convert.ToBase64String(b);}}
"@
Add-Type -TypeDefinition $sig
$bytes = [Convert]::FromBase64String([Cred]::ReadB64("git:https://github.com"))
$tok = $null
foreach ($c in @([Text.Encoding]::Unicode.GetString($bytes), [Text.Encoding]::UTF8.GetString($bytes)) | ForEach-Object { ($_ -replace "`0","").Trim() } | Select-Object -Unique) {
  try { Invoke-RestMethod "https://api.github.com/user" -Headers @{Authorization="token $c";"User-Agent"="conx";"Accept"="application/vnd.github+json"} -TimeoutSec 20 | Out-Null; $tok = $c; break } catch {}
}
if (-not $tok) { "ERRO: nao consegui o token do GitHub (rode 'git push' uma vez para salvar a credencial)."; exit 1 }
$h = @{ Authorization = "token $tok"; "User-Agent" = "conx"; "Accept" = "application/vnd.github+json" }

# --- cria (ou reutiliza) a release ---
try {
  $body = @{ tag_name=$tag; name=$tag; body="NFSe Automacao $tag"; draft=$false; prerelease=$false } | ConvertTo-Json
  $rel = Invoke-RestMethod "https://api.github.com/repos/$repo/releases" -Method Post -Headers $h -Body $body -ContentType 'application/json' -TimeoutSec 30
  "Release criada: $($rel.html_url)"
} catch {
  $rel = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/tags/$tag" -Headers $h -TimeoutSec 30
  "Release reutilizada: $($rel.html_url)"
}
$relId = $rel.id
foreach ($a in $rel.assets) { try { Invoke-RestMethod $a.url -Method Delete -Headers $h -TimeoutSec 30 | Out-Null } catch {} }

# --- sobe os arquivos (artifactName ja gera nomes hifenizados) ---
$dist = Join-Path $PSScriptRoot "electron\dist"
$exe = "NFSe-Automacao-Setup-$ver.exe"
$itens = @(
  @{ file = $exe;              ct = "application/octet-stream" },
  @{ file = "$exe.blockmap";   ct = "application/octet-stream" },
  @{ file = "latest.yml";      ct = "text/yaml" }
)
foreach ($i in $itens) {
  $path = Join-Path $dist $i.file
  if (-not (Test-Path $path)) { "FALTA em dist: $($i.file)"; continue }
  $name = [uri]::EscapeDataString($i.file)
  "Enviando $($i.file) ..."
  Invoke-RestMethod "https://uploads.github.com/repos/$repo/releases/$relId/assets?name=$name" -Method Post -Headers $h -InFile $path -ContentType $i.ct -TimeoutSec 900 | Out-Null
  "  OK"
}
"=== PUBLICADO: $($rel.html_url) ==="
