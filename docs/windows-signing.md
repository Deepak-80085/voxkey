# Windows release signing

Tagged releases are blocked unless both GitHub Actions secrets are configured:

- `WINDOWS_CERTIFICATE`: Base64-encoded PFX certificate.
- `WINDOWS_CERTIFICATE_PASSWORD`: Password for that PFX.

Encode the certificate on Windows:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes('voxkey.pfx')) | Set-Clipboard
```

Add both values under **Repository settings -> Secrets and variables -> Actions**.
The release workflow signs and verifies `VoxKey.exe`, builds the installer, then signs and verifies the installer with an RFC 3161 timestamp.

Before creating a tag, verify the certificate subject represents the project owner or organization and that the certificate permits code signing. Never commit the PFX or password.
