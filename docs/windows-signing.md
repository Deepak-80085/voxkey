# Windows release signing

Tagged releases are allowed without signing, but the workflow publishes a prominent unsigned-release warning when these GitHub Actions secrets are absent:

- `WINDOWS_CERTIFICATE`: Base64-encoded PFX certificate.
- `WINDOWS_CERTIFICATE_PASSWORD`: Password for that PFX.

Encode the certificate on Windows:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes('voxkey.pfx')) | Set-Clipboard
```

Add both values under **Repository settings -> Secrets and variables -> Actions** when a signing certificate is available. When both are present, the release workflow signs and verifies `VoxKey.exe`, builds the installer, then signs and verifies the installer with an RFC 3161 timestamp. When either value is absent, the workflow still creates the release but leaves both artifacts unsigned and discloses that status in the release notes.

Unsigned releases may be blocked by Windows Smart App Control, SmartScreen, or enterprise policy. Never disable Windows security protections or add Defender exclusions solely to run an unsigned build.

Before creating a tag, verify the certificate subject represents the project owner or organization and that the certificate permits code signing. Never commit the PFX or password.
