; Instalador do GNRE.Flow (Inno Setup 6). Gerar com: build_windows.ps1
#define AppName "GNRE.Flow"
#define AppVersion "1.0.3"

[Setup]
AppId={{6B1B6C0E-6E3A-4C57-9B5B-5F0A3B7E2D11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=GNRE.Flow
; Instala so para o usuario atual (nao pede senha de administrador); o usuario
; pode escolher "para todos" na tela de privilegios.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=GNRE.Flow-Setup
SetupIconFile=gnreflow.ico
UninstallDisplayIcon={app}\GNRE.Flow.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\dist\GNRE.Flow\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\GNRE.Flow.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\GNRE.Flow.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GNRE.Flow.exe"; Description: "Abrir o GNRE.Flow agora"; Flags: nowait postinstall skipifsilent

; Os dados do usuario (banco, certificado criptografado, tabela de aliquotas) ficam em
; %APPDATA%\GNRE.Flow e NAO sao apagados ao desinstalar nem ao atualizar.
