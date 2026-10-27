; Inno Setup script for the Windows installer: a wizard that installs LENS for the current user
; (no administrator) into %LOCALAPPDATA%\Programs\LENS, with a Start menu entry, an optional
; desktop shortcut, .lens files opening in LENS with an icon of their own, the example
; worksheets, and an uninstaller under Settings -> Apps. Running a newer installer updates LENS
; in place, closing a running LENS first.
;
; Build the program first (`pyinstaller packaging/lens.spec`, which leaves dist\lens), then
;   iscc /DAppVersion=0.3.7 packaging\lens.iss
; which writes dist\lens-install-wizard.exe. The build workflow does both and renames the installer
; lens-<version>-windows-x64-install-wizard.exe.

#ifndef AppVersion
  #define AppVersion "0+dev"
#endif
#define Root ".."

[Setup]
; Never change AppId: it is how a new installer finds the LENS it updates.
AppId={{7EC3065B-DE09-44E2-9AF3-D0540AE0FEB2}
AppName=LENS
AppVersion={#AppVersion}
AppVerName=LENS {#AppVersion}
AppPublisher=InverseInertia
AppPublisherURL=https://github.com/inverseinertia/laconic-ens
AppSupportURL=https://github.com/inverseinertia/laconic-ens/issues
AppUpdatesURL=https://github.com/inverseinertia/laconic-ens/releases
; Per user, like install-linux.sh: {autopf} is then %LOCALAPPDATA%\Programs.
PrivilegesRequired=lowest
DefaultDirName={autopf}\LENS
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
; An update replaces files of a LENS that may be running (its server has no window).
CloseApplications=force
RestartApplications=no
SetupIconFile={#Root}\packaging\icon.ico
UninstallDisplayIcon={app}\lens.exe
UninstallDisplayName=LENS
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir={#Root}\dist
OutputBaseFilename=lens-install-wizard

[Tasks]
Name: "assoc"; Description: "Open .lens files in LENS"; GroupDescription: "File types:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; The bundled libraries of the LENS being updated: files a newer build no longer has must not linger.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Root}\dist\lens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\packaging\file-icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\laconic\examples\*.lens"; DestDir: "{app}\examples"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\LENS"; Filename: "{app}\lens.exe"; Comment: "Laconic engineering notation worksheet"
Name: "{autoprograms}\LENS example worksheets"; Filename: "{app}\examples"
Name: "{autodesktop}\LENS"; Filename: "{app}\lens.exe"; Tasks: desktopicon

[Registry]
; The same keys `lens --register-files` writes (laconic/fileassoc.py), so either replaces the other.
Root: HKCU; Subkey: "Software\Classes\.lens"; ValueType: string; ValueName: ""; ValueData: "LaconicLens.Worksheet"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\.lens"; ValueType: string; ValueName: "Content Type"; ValueData: "text/plain"; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\LaconicLens.Worksheet"; ValueType: string; ValueName: ""; ValueData: "LENS worksheet"; Flags: uninsdeletekey; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\LaconicLens.Worksheet\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\file-icon.ico"""; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\LaconicLens.Worksheet\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\lens.exe"" --window ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\lens.exe"; Description: "{cm:LaunchProgram,LENS}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The file icon an earlier `lens --register-files` copied out (laconic/fileassoc.py). Settings in
; %APPDATA%\laconic are kept.
Type: filesandordirs; Name: "{localappdata}\laconic-lens"
