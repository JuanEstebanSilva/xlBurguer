; Script de Inno Setup para Carnicería San Diego POS & Gestión Comercial
; Genera un instalador independiente profesional para Windows (x64)

#define MyAppName "Carnicería San Diego"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "HUNZAIA SAS BIC"
#define MyAppURL "https://sandiego.hunzaia.co"
#define MyAppExeName "CarniceriaSanDiego.exe"

[Setup]
AppId={{E57D5D18-7F45-4B81-9C49-E774619EFA73}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Carniceria San Diego
DefaultGroupName=Carnicería San Diego
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Instalador_Carniceria_SanDiego_v1.0
SetupIconFile=..\imgs\icono.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=admin
UninstallDisplayIcon={app}\icono.ico
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription="Sistema POS y Punto de Venta - Carnicería San Diego"
VersionInfoProductVersion={#MyAppVersion}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Archivos empaquetados desde la carpeta dist generada por PyInstaller
; Se excluye sandiego.db para NUNCA sobreescribir la base de datos real del cliente en actualizaciones
Source: "..\dist\CarniceriaSanDiego\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "sandiego.db,*.log,backups\*"
; Garantizar que icono.ico esté siempre disponible tanto en la raíz de {app} como en {app}\imgs para accesos directos
Source: "..\imgs\icono.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\imgs\icono.ico"; DestDir: "{app}\imgs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; AppUserModelID: "carniceria.sandiego.pos.1.0"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; Tasks: desktopicon; AppUserModelID: "carniceria.sandiego.pos.1.0"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    MsgBox('Carnicería San Diego ha sido desinstalada correctamente del sistema.' + #13#10 + #13#10 +
           'NOTA DE SEGURIDAD:' + #13#10 +
           'Por protección de sus datos comerciales, su base de datos histórica y ventas se han conservado intactas en:' + #13#10 +
           ExpandConstant('{userappdata}\CarniceriaSanDiego'), mbInformation, MB_OK);
  end;
end;
