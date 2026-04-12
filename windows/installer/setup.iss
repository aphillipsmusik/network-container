; Inno Setup script for LLM Cluster Node
; Build with Inno Setup 6+ on Windows

#define AppName "LLM Cluster Node"
#define AppVersion "1.0.0"
#define AppPublisher "aphillipsmusik"
#define AppURL "https://github.com/aphillipsmusik/network-container"
#define AppExeName "LLMCluster.exe"
#define RpcServerExe "llama-rpc-server.exe"
#define LlamaServerExe "llama-server.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\LLMCluster
DefaultGroupName={#AppName}
AllowNoIcons=yes
; Require admin so we can open firewall ports
PrivilegesRequired=admin
OutputDir=dist
OutputBaseFilename=LLMCluster-Setup
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardResizable=no
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Distributed LLM cluster node for Windows

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked
Name: "startupentry"; Description: "Start LLM Cluster automatically with Windows"; Flags: checked

[Files]
; Main GUI application (built by PyInstaller)
Source: "..\..\dist\LLMCluster.exe"; DestDir: "{app}"; Flags: ignoreversion

; llama.cpp binaries (downloaded by GitHub Actions)
Source: "..\..\dist\bin\{#RpcServerExe}";  DestDir: "{app}\bin"; Flags: ignoreversion
Source: "..\..\dist\bin\{#LlamaServerExe}"; DestDir: "{app}\bin"; Flags: ignoreversion

; Any DLLs required by llama.cpp (CUDA runtime, etc.)
Source: "..\..\dist\bin\*.dll"; DestDir: "{app}\bin"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}";        Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Auto-start entry (mirrors what the app itself sets, ensures it survives reinstalls)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run";
  ValueType: string; ValueName: "LLM Cluster"; ValueData: """{app}\{#AppExeName}""";
  Flags: uninsdeletevalue; Tasks: startupentry

[Run]
; Launch after install
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Kill the running process before uninstalling
Filename: "taskkill"; Parameters: "/F /IM {#AppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
; Remove config dir
Type: filesandordirs; Name: "{userappdata}\LLMCluster"

[Code]
// Check if Docker Desktop is present (not required, but show a notice)
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ErrCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Open firewall ports via netsh
    Exec('netsh', 'advfirewall firewall add rule name="LLM Cluster RPC" dir=in action=allow protocol=TCP localport=50052', '', SW_HIDE, ewWaitUntilTerminated, ErrCode);
    Exec('netsh', 'advfirewall firewall add rule name="LLM Cluster API" dir=in action=allow protocol=TCP localport=8080', '', SW_HIDE, ewWaitUntilTerminated, ErrCode);
    Exec('netsh', 'advfirewall firewall add rule name="LLM Cluster Mgmt" dir=in action=allow protocol=TCP localport=8888', '', SW_HIDE, ewWaitUntilTerminated, ErrCode);
    Exec('netsh', 'advfirewall firewall add rule name="LLM Cluster mDNS" dir=in action=allow protocol=UDP localport=5353', '', SW_HIDE, ewWaitUntilTerminated, ErrCode);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ErrCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Exec('netsh', 'advfirewall firewall delete rule name="LLM Cluster RPC"', '', SW_HIDE, ewWaitUntilTerminated, ErrCode);
    Exec('netsh', 'advfirewall firewall delete rule name="LLM Cluster API"', '', SW_HIDE, ewWaitUntilTerminated, ErrCode);
    Exec('netsh', 'advfirewall firewall delete rule name="LLM Cluster Mgmt"', '', SW_HIDE, ewWaitUntilTerminated, ErrCode);
    Exec('netsh', 'advfirewall firewall delete rule name="LLM Cluster mDNS"', '', SW_HIDE, ewWaitUntilTerminated, ErrCode);
  end;
end;
