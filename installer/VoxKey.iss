; Build with: ISCC installer\VoxKey.iss
#define MyAppName "VoxKey"
#define MyAppVersion "2.0.3-test"
#define MyAppPublisher "Deepak"
#define MyAppURL "https://github.com/Deepak-80085/voxkey"
#define MyAppExeName "VoxKey.exe"

[Setup]
AppId={{A9C7D4C8-BEC9-4AF0-843A-42C580A5DF8B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\release
OutputBaseFilename=VoxKey-Setup-{#MyAppVersion}
SetupIconFile=..\asset\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\VoxKey\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\VoxKey"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\VoxKey"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch VoxKey"; Flags: nowait postinstall skipifsilent
