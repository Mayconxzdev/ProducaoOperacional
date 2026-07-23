#ifndef MyAppVersion
  #define MyAppVersion "2.4.0"
#endif
#ifndef MySourceDir
  #define MySourceDir "..\dist\Producao_Operacional"
#endif
#ifndef MyOutputDir
  #define MyOutputDir "..\dist"
#endif
#ifndef MyOutputBase
  #define MyOutputBase "Producao_Operacional_Setup_v" + MyAppVersion
#endif
#ifndef MyAppIcon
  #define MyAppIcon "..\assets\producao_operacional.ico"
#endif
#ifndef NASRootPrimary
  #define NASRootPrimary "\\SERVIDOR\Compartilhamento\ProducaoOperacional"
#endif

[Setup]
AppId={{0F8F6AD4-8D5D-4E7C-9EED-7A3B8709D5B3}
AppName=Produção Operacional
AppVersion={#MyAppVersion}
AppPublisher=Mayconxzdev
DefaultDirName={localappdata}\ProducaoOperacional
DefaultGroupName=Produção Operacional
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBase}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\Producao_Operacional.exe
SetupLogging=yes
SetupIconFile={#MyAppIcon}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"
Name: "roleoffice"; Description: "Modo Escritório"; GroupDescription: "Perfil desta estação:"; Flags: exclusive checkedonce
Name: "roletv"; Description: "Modo TV/Foco"; GroupDescription: "Perfil desta estação:"; Flags: exclusive
Name: "roledemo"; Description: "Modo Demonstração (local, sem NAS)"; GroupDescription: "Perfil desta estação:"; Flags: exclusive
Name: "opimportintegrator"; Description: "Ativar integração automática de novas OPs neste computador"; GroupDescription: "Automação opcional:"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\config\settings.json"; DestDir: "{app}\config"; DestName: "settings.json"; Flags: onlyifdoesntexist
Source: "..\config\settings.example.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\install_op_discovery_task.ps1"; DestDir: "{app}\automation"; Flags: ignoreversion
Source: "..\scripts\remove_op_discovery_task.ps1"; DestDir: "{app}\automation"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\Produção Operacional"; Filename: "{app}\Producao_Operacional.exe"; Tasks: desktopicon
Name: "{autodesktop}\Produção Operacional — Demonstração"; Filename: "{app}\Producao_Operacional.exe"; Parameters: "--demo"
Name: "{autoprograms}\Produção Operacional\Produção Operacional"; Filename: "{app}\Producao_Operacional.exe"
Name: "{autoprograms}\Produção Operacional\Produção Operacional — Demonstração"; Filename: "{app}\Producao_Operacional.exe"; Parameters: "--demo"
Name: "{autoprograms}\Produção Operacional\Desinstalar"; Filename: "{uninstallexe}"
Name: "{userstartup}\Produção Operacional TV"; Filename: "{app}\Producao_Operacional.exe"; Parameters: "--tv-kiosk"; Tasks: roletv

[Run]
Filename: "{app}\Producao_Operacional.exe"; Description: "Abrir Produção Operacional"; Flags: nowait postinstall skipifsilent unchecked

[Code]
var
  NASAvailabilityChecked: Boolean;

function ConfigureRole(const Arguments, FailureMessage: string): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{app}\Producao_Operacional.exe'), Arguments, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
  if not Result then
    MsgBox(FailureMessage + #13#10 + 'Código: ' + IntToStr(ResultCode), mbCriticalError, MB_OK);
end;

function ConfigureOpImportTask(): Boolean;
var
  ResultCode: Integer;
  Arguments: string;
begin
  Arguments := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\automation\install_op_discovery_task.ps1') +
    '" -AppExecutable "' + ExpandConstant('{app}\Producao_Operacional.exe') +
    '" -ConfigPath "' + ExpandConstant('{app}\config\settings.json') + '" -EnableIntegration';
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Arguments, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
  if not Result then
    MsgBox('Falha ao configurar a integração automática de OPs.' + #13#10 + 'Código: ' + IntToStr(ResultCode), mbCriticalError, MB_OK);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectTasks) and (not WizardIsTaskSelected('roledemo')) and (not NASAvailabilityChecked) then
  begin
    NASAvailabilityChecked := True;
    if not DirExists('{#NASRootPrimary}') then
      Result := MsgBox('O NAS configurado não está acessível.' + #13#10 + 'A instalação pode continuar, mas ficará somente leitura até a conexão voltar.' + #13#10 + #13#10 + 'Continuar?', mbConfirmation, MB_YESNO) = IDYES;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('roleoffice') then
    begin
      DeleteFile(ExpandConstant('{userstartup}\Produção Operacional TV.lnk'));
      if not ConfigureRole('--configure-role office', 'Falha ao configurar o modo Escritório.') then
        RaiseException('Falha ao configurar a estação.');
    end;
    if WizardIsTaskSelected('roletv') then
    begin
      if not ConfigureRole('--configure-role tv', 'Falha ao configurar o modo TV/Foco.') then
        RaiseException('Falha ao configurar a estação.');
    end;
    if WizardIsTaskSelected('roledemo') then
    begin
      DeleteFile(ExpandConstant('{userstartup}\Produção Operacional TV.lnk'));
      if not ConfigureRole('--configure-role demo', 'Falha ao configurar o modo Demonstração.') then
        RaiseException('Falha ao configurar a estação.');
    end;
    if WizardIsTaskSelected('opimportintegrator') then
    begin
      if not ConfigureOpImportTask() then
        RaiseException('Falha ao configurar a integração automática de OPs.');
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
    Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\automation\remove_op_discovery_task.ps1') + '"',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
