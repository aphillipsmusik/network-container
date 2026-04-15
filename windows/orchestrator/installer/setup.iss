; Inno Setup script – LLM Cluster Orchestrator Installer
; Builds: LLMCluster-Orchestrator-Setup.exe

#define AppName      "LLM Cluster Orchestrator"
#define AppVersion   "1.0.0"
#define AppPublisher "LLM Cluster Contributors"
#define AppURL       "https://github.com/aphillipsmusik/network-container"
#define AppExeName   "LLMClusterOrchestrator.exe"
#define ServiceExe   "llama-server.exe"

[Setup]
AppId={{E8A1C3F2-7D94-4B5E-9A06-2F1D83CB4712}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={autopf}\LLMCluster
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputBaseFilename=LLMCluster-Orchestrator-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\bin\{#AppExeName}
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";   Description: "{cm:CreateDesktopIcon}";   GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart";     Description: "Start orchestrator when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Main GUI executable (PyInstaller one-file build)
Source: "..\..\dist\LLMClusterOrchestrator.exe"; DestDir: "{app}\bin"; Flags: ignoreversion

; llama-server binary + CUDA / Vulkan DLLs (pre-downloaded by CI)
Source: "..\..\dist\bin\llama-server.exe";        DestDir: "{app}\bin"; Flags: ignoreversion
Source: "..\..\dist\bin\*.dll";                   DestDir: "{app}\bin"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}";        Filename: "{app}\bin\{#AppExeName}"
Name: "{group}\Uninstall";         Filename: "{uninstallexe}"
Name: "{commondesktop}\LLM Cluster Orchestrator"; Filename: "{app}\bin\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Auto-start entry (optional, created only when task selected)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "LLMClusterOrchestrator"; \
  ValueData: """{app}\bin\{#AppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\bin\{#AppExeName}"; Description: "Launch Orchestrator"; \
  Flags: nowait postinstall skipifsilent

[Code]
procedure OpenFirewallPort(Port: Integer; Protocol: String; RuleName: String);
var
  ResultCode: Integer;
begin
  Exec(
    'netsh',
    'advfirewall firewall add rule name="' + RuleName + '"' +
    ' dir=in action=allow protocol=' + Protocol +
    ' localport=' + IntToStr(Port),
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
end;

procedure DeleteFirewallRule(RuleName: String);
var
  ResultCode: Integer;
begin
  Exec(
    'netsh',
    'advfirewall firewall delete rule name="' + RuleName + '"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { Inference API }
    OpenFirewallPort(8080, 'TCP', 'LLMCluster Orchestrator - Inference API');
    { Management API }
    OpenFirewallPort(8888, 'TCP', 'LLMCluster Orchestrator - Management API');
    { mDNS }
    OpenFirewallPort(5353, 'UDP', 'LLMCluster mDNS');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DeleteFirewallRule('LLMCluster Orchestrator - Inference API');
    DeleteFirewallRule('LLMCluster Orchestrator - Management API');
    DeleteFirewallRule('LLMCluster mDNS');
  end;
end;
