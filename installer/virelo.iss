#define MyAppName "Virelo"
#define MyAppPublisher "Yusuf Qwareeq"
#define MyAppURL "https://github.com/qwareeq8/virelo"
#define MyAppExeName "Virelo.exe"

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

#ifndef PayloadArchitecture
  #error "PayloadArchitecture must be defined as x64 or arm64."
#endif

#if PayloadArchitecture == "x64"
  #define PayloadArchitecturesAllowed "x64compatible"
  #define PayloadArchitecturesInstallIn64BitMode "x64compatible"
  #define PayloadMinVersion "10.0.17763"
#elif PayloadArchitecture == "arm64"
  #define PayloadArchitecturesAllowed "arm64"
  #define PayloadArchitecturesInstallIn64BitMode "arm64"
  #define PayloadMinVersion "10.0.22000"
#else
  #error "Unsupported PayloadArchitecture. Use x64 or arm64."
#endif

#define PayloadDirectory AddBackslash(SourcePath) + "..\dist\" + PayloadArchitecture + "\Virelo"

#pragma message "VIRELO_EFFECTIVE_ARCHITECTURE=" + PayloadArchitecture
#pragma message "VIRELO_EFFECTIVE_ALLOWED=" + PayloadArchitecturesAllowed
#pragma message "VIRELO_EFFECTIVE_64BIT_MODE=" + PayloadArchitecturesInstallIn64BitMode
#pragma message "VIRELO_EFFECTIVE_MIN_VERSION=" + PayloadMinVersion
#pragma message "VIRELO_EFFECTIVE_PAYLOAD=" + PayloadDirectory

#if !FileExists(PayloadDirectory + "\Virelo.exe")
  #error "The architecture-qualified payload is missing Virelo.exe. Build dist/<architecture>/Virelo first."
#endif

[Setup]
AppId={{7B84D572-0B2B-4C1B-9B45-0F2CFAB58A31}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
OutputDir=dist
OutputBaseFilename={#MyAppName}Setup-{#MyAppVersion}-{#PayloadArchitecture}
OutputManifestFile={#MyAppName}Setup-{#MyAppVersion}-{#PayloadArchitecture}-manifest.txt
SetupIconFile={#SourcePath}\..\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile={#SourcePath}\..\branding\installer-wizard.bmp,{#SourcePath}\..\branding\installer-wizard_2x.bmp
WizardSmallImageFile={#SourcePath}\..\branding\installer-header.bmp,{#SourcePath}\..\branding\installer-header_2x.bmp
WizardImageAlphaFormat=none
ArchitecturesAllowed={#PayloadArchitecturesAllowed}
ArchitecturesInstallIn64BitMode={#PayloadArchitecturesInstallIn64BitMode}
MinVersion={#PayloadMinVersion}
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
AppMutex=Global\Virelo_Mutex
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} installer ({#PayloadArchitecture})

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[InstallDelete]
; Remove the prior application payload before copying a different architecture.
; User settings, logs, startup shortcuts, and Explorer recovery backups live in
; per-user locations and are intentionally outside this per-machine installer.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#MyAppExeName}"

[Files]
Source: "{#PayloadDirectory}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
; Inno Setup cannot recover the original user's token at uninstall time. This
; removes the shortcut for the account running Uninstall, which is the same
; profile for ordinary same-account UAC elevation. Over-the-shoulder elevation
; is documented as requiring manual cleanup in the original profile.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--remove-startup-shortcut"; Flags: runhidden runascurrentuser; RunOnceId: "RemoveCurrentUserStartupShortcut"
