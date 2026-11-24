; Inno Setup script for AeroDent standalone edition.
#define AppName "AeroDent"
#define AppPublisher "AeroDent"
#define AppExeName "AeroDent.exe"
#define SourceDir "..\dist\AeroDent"
#define OutputDir "..\dist"

[Setup]
AppId={{D4A5E080-1A24-4B2F-9A3C-1C6D3F2A77D9}
AppName={#AppName}
AppVersion=1.0.0
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\AeroDent
DefaultGroupName=AeroDent
OutputDir={#OutputDir}
OutputBaseFilename=AeroDent-Setup
SetupIconFile=..\web\icons\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AeroDent"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\AeroDent"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch AeroDent"; Flags: nowait postinstall skipifsilent
