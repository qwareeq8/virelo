#define MyAppName "Virelo"
#define MyAppPublisher "Yusuf Qwareeq"
#define MyAppURL "https://github.com/yusufqwareeq/virelo"
#define MyAppExeName "Virelo.exe"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

[Setup]
AppId={{7B84D572-0B2B-4C1B-9B45-0F2CFAB58A31}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
OutputDir=dist
OutputBaseFilename={#MyAppName}Setup
SetupIconFile={#SourcePath}\..\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile={#SourcePath}\..\branding\installer-wizard.bmp,{#SourcePath}\..\branding\installer-wizard_2x.bmp
WizardSmallImageFile={#SourcePath}\..\branding\installer-header.bmp,{#SourcePath}\..\branding\installer-header_2x.bmp
WizardImageAlphaFormat=none
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#SourcePath}\.\..\dist\Virelo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
