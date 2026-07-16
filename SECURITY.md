# Security policy

## Supported version

Only the latest released VoxKey version receives fixes.

## Reporting a vulnerability

Do not publish security-sensitive reproduction details in a public issue. Contact the repository owner privately through GitHub, including affected version, Windows version, reproduction steps, and impact. You should receive an acknowledgement within seven days.

## Trust boundary

VoxKey is intentionally local-first, but it sends keyboard input and temporarily uses the Windows clipboard to paste polished text. Review the source and verify published installer checksums before installing. Existing releases may be unsigned; future tagged releases are blocked unless the application and installer are Authenticode-signed.
