; Inno Setup script for LPBF Serializer
; Build with:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
; Requires the PyInstaller one-folder build in dist\LPBFSerializer\

#define AppName      "LPBF Serializer"
#define AppVersion   "0.1.0"
#define AppPublisher "LPBF Serializer Team"
#define AppExe       "LPBFSerializer.exe"

[Setup]
AppId={{8FFA0E91-5D58-4E3F-9CDF-9F7A7F8A1E02}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\LPBFSerializer
DefaultGroupName=LPBF Serializer
DisableProgramGroupPage=yes
OutputDir=..\dist-installer
OutputBaseFilename=LPBFSerializer-{#AppVersion}-setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}

[Files]
Source: "..\dist\LPBFSerializer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Code]
const
  ExpectedQuantAmExe =
    'C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1\Renishaw QuantAM.exe';

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not FileExists(ExpectedQuantAmExe) then
  begin
    MsgBox(
      'LPBF Serializer requires Renishaw QuantAM 6.1.0.1 to be installed at:' #13#10
      + ExpectedQuantAmExe + #13#10 #13#10
      + 'Install QuantAM 6.1.0.1 first, then re-run this installer.',
      mbCriticalError, MB_OK);
    Result := False;
  end;
end;
