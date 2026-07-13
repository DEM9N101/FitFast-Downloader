; Inno Setup script for FitFast Downloader
; Builds a small, no-admin installer that unpacks the app into the user's
; profile and creates Start Menu + optional desktop shortcuts. The stealth
; browser is downloaded automatically the first time the app runs.

#define MyAppName "FitFast Downloader"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "FitFast"
#define MyAppExeName "FitFast.exe"
#define MyAppURL "https://github.com/DEM9N101/FitFast-Downloader"

[Setup]
AppId={{170ECF36-6E15-4DC6-B210-D255D3C8DA49}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\FitFast
DefaultGroupName=FitFast Downloader
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\installer_out
OutputBaseFilename=FitFast-Setup-v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\FitFast\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\FitFast Downloader"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall FitFast Downloader"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FitFast Downloader"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch FitFast Downloader now"; Flags: nowait postinstall skipifsilent

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nThe first time you open FitFast, it downloads a stealth browser once (a few hundred MB). That is normal and only happens once.
