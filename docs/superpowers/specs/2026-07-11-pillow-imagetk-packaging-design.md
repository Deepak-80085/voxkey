# Pillow ImageTk Packaging Design

## Goal
Prevent SimpleSpeech’s Windows status overlay from crashing because Pillow’s Tk integration is missing from a frozen PyInstaller build.

## Evidence and root cause
The installed executable at `%LOCALAPPDATA%\Programs\SimpleSpeech\SimpleSpeech.exe` lacks both `PIL\ImageTk.py` and `PIL\_imagingtk.cp312-win_amd64.pyd`. The error screenshot shows the failure occurs in `PIL.ImageTk.PhotoImage()` while SimpleSpeech draws its overlay. The source build configuration declares only `pystray` and `PIL.Image` as hidden imports, leaving the `ImageTk` module and native bridge to indirect PyInstaller discovery.

The current local `E:\simplespeech\dist\SimpleSpeech` output happens to contain `_imagingtk`, but the installed release does not. Packaging must be explicit and tested against the frozen output.

## Design
1. Update `SimpleSpeech.spec` to explicitly include `PIL.ImageTk` and `PIL._imagingtk` as hidden imports.
2. Extend the existing packaging test to assert those explicit dependencies exist in the spec. This catches accidental removal of the declarations before a release build.
3. Build the application with the project virtual environment, then inspect the generated `dist\SimpleSpeech\_internal\PIL` folder to verify that both `ImageTk.py` and `_imagingtk*.pyd` are actually included.
4. Build the Inno Setup installer and install it over the current per-user installation. Verify the installed folder contains the same two assets.
5. Record the release fix in `CHANGELOG.md` as a new patch version.

## Error handling and compatibility
No application runtime behavior changes. The existing overlay renderer continues using Pillow and Tk. The release artifact gains the dependency it already requires.

## Acceptance criteria
- `SimpleSpeech.spec` explicitly references `PIL.ImageTk` and `PIL._imagingtk`.
- `tests/test_packaging.py` fails if either reference is absent.
- A clean PyInstaller build includes `ImageTk.py` and `_imagingtk*.pyd` under `dist\SimpleSpeech\_internal\PIL`.
- The rebuilt installer installs those files under `%LOCALAPPDATA%\Programs\SimpleSpeech\_internal\PIL`.
- Existing packaging and runtime tests pass.
