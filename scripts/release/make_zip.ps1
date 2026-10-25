# Builds the Windows download: the repo as committed, uv.exe, and start.bat and terminal.bat at
# the top. It holds no Python and no libraries; start.bat installs them on the first start, from
# uv.lock. The release workflow (.github/workflows/release.yml) runs this on each version tag.
#
#   pwsh scripts/release/make_zip.ps1                     # from HEAD, with the uv on PATH
#   pwsh scripts/release/make_zip.ps1 -Ref (git write-tree)   # from what is staged, to try it
#
# The result is dist/anime-voice-collector-v<version>-windows.zip, with one folder inside.

param(
    # Commit or tree to package. Files not in it, even if present here, are left out.
    [string]$Ref = 'HEAD',
    # Must equal the version in pyproject.toml; the workflow passes the tag without its "v".
    [string]$Version,
    # uv.exe to ship; if omitted, the uv on PATH.
    [string]$Uv = (Get-Command uv -ErrorAction Stop).Source,
    [string]$Out = 'dist'
)

$ErrorActionPreference = 'Stop'
$repo = (git rev-parse --show-toplevel).Trim()
Set-Location $repo

$projectVersion = (git show "${Ref}:pyproject.toml" | Select-String -Pattern '^version = "(.+)"$').Matches[0].Groups[1].Value
if (-not $Version) { $Version = $projectVersion }
if ($Version -ne $projectVersion) {
    throw "Version $Version does not match pyproject.toml ($projectVersion)."
}

$name = "anime-voice-collector-v$Version-windows"
$stage = Join-Path $Out $name
$folder = Join-Path $stage 'anime-voice-collector'
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $folder | Out-Null

# git archive writes the files with the line endings .gitattributes gives them, so the .bat files
# get the CRLF that cmd.exe needs.
$tar = Join-Path $stage 'source.tar'
git archive --format=tar -o $tar $Ref
if ($LASTEXITCODE -ne 0) { throw "git archive $Ref failed." }
tar -xf $tar -C $folder
if ($LASTEXITCODE -ne 0) { throw 'Unpacking the archive failed.' }
Remove-Item $tar

Copy-Item (Join-Path $folder 'scripts/release/start.bat') $folder
Copy-Item (Join-Path $folder 'scripts/release/terminal.bat') $folder
Copy-Item $Uv (Join-Path $folder 'uv.exe')
$uvVersion = (& $Uv --version).Trim()

$zip = Join-Path $Out "$name.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $folder -DestinationPath $zip -CompressionLevel Optimal
Remove-Item -Recurse -Force $stage

$size = (Get-Item $zip).Length / 1MB
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
Write-Output ("{0}  {1:N1} MB  ({2})" -f $zip, $size, $uvVersion)
Write-Output "SHA-256 $hash"
