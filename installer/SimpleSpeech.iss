; Build with: ISCC installer\SimpleSpeech.iss
#define MyAppName "SimpleSpeech"
#define MyAppVersion "1.0.2"
#define MyAppPublisher "Deepak"
#define MyAppURL "https://github.com/Deepak-80085/simplespeech"
#define MyAppExeName "SimpleSpeech.exe"

[Setup]
AppId={{3E4567F6-0A13-4F53-AE91-C135AE8E869B}
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
OutputBaseFilename=SimpleSpeech-Setup-{#MyAppVersion}
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
Source: "..\dist\SimpleSpeech\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SimpleSpeech"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\SimpleSpeech"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch SimpleSpeech"; Flags: nowait postinstall skipifsilent
