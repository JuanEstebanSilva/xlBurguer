; Script de Inno Setup para XL Burguer POS & Gestion Comercial
; Genera un instalador independiente profesional para Windows (x64)

#define MyAppName "XL Burguer"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "XL Burguer"
#define MyAppURL "https://xlburguer.com"
#define MyAppExeName "XLBurguer.exe"

[Setup]
AppId={{C72D3F59-5431-4F26-8BE2-0A5E2E6DF9B2}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\XL Burguer
DefaultGroupName=XL Burguer
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Instalador_XLBurguer_v1.0
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
VersionInfoDescription="Sistema POS y Punto de Venta - XL Burguer"
VersionInfoProductVersion={#MyAppVersion}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Archivos empaquetados desde la carpeta dist generada por PyInstaller
; Se excluye xlburguer.db para NUNCA sobreescribir la base de datos real del cliente en actualizaciones
Source: "..\dist\XLBurguer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "xlburguer.db,*.log,backups\*"
; Garantizar que icono.ico este siempre disponible tanto en la raiz de {app} como en {app}\imgs para accesos directos
Source: "..\imgs\icono.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\imgs\icono.ico"; DestDir: "{app}\imgs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; AppUserModelID: "xlburguer.pos.1.0"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; Tasks: desktopicon; AppUserModelID: "xlburguer.pos.1.0"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    MsgBox('XL Burguer ha sido desinstalada correctamente del sistema.' + #13#10 + #13#10 +
           'NOTA DE SEGURIDAD:' + #13#10 +
           'Por proteccion de sus datos comerciales, su base de datos historica y recetas se han conservado intactas en:' + #13#10 +
           ExpandConstant('{userappdata}\XLBurguer'), mbInformation, MB_OK);
  end;
end;

