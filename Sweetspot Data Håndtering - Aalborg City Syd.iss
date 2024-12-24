; Inno Setup Compiler script

#define MyAppName "Sweetspot Data Håndtering - Aalborg City Syd"
#define MyAppVersion "1.5"
#define MyAppPublisher "Jonas"
#define MyAppExeName "Sweetspot Data Håndtering.exe"

[Setup]
AppId={{96BBEE9C-8252-4C9B-AA7E-B1AB017653FE}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Fjern arkitekturbegrænsninger for at tillade installation på både x86 og x64 systemer, herunder ARM-baserede systemer
; ArchitecturesAllowed=x64
; ArchitecturesInstallIn64BitMode=x64
DefaultDirName={localappdata}\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=C:\Users\jonas\Desktop\NFB-Datobog\License.txt
InfoBeforeFile=C:\Users\jonas\Desktop\NFB-Datobog\info_before.txt
InfoAfterFile=C:\Users\jonas\Desktop\NFB-Datobog\info_after.txt
PrivilegesRequired=lowest
OutputDir=C:\Installers
OutputBaseFilename=SweetspotSetup_v1.5
SetupIconFile=C:\Users\jonas\Desktop\NFB-Datobog\sweetspot_logo.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
WindowShowCaption=yes
WindowResizable=yes
WindowStartMaximized=yes
WindowVisible=yes
Uninstallable=yes
AppContact={#MyAppPublisher}
AppComments=Installeret af {#MyAppPublisher}

[Languages]
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Kopier hele mappen 'Sweetspot Data Håndtering' fra dist-mappen
Source: "C:\Users\jonas\Desktop\NFB-Datobog\dist\Sweetspot Data Håndtering\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\sweetspot_logo.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\sweetspot_logo.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}\*"
