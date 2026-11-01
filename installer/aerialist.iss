; Inno Setup script: per-user installer (no admin needed) with Start menu shortcut
; and "Open with" registration for PDFs. Built by the GitHub workflow.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{7C1B6E52-3E0B-4C8B-9B8E-5D2B1D0BE11E}
AppName=Benelli Aerialist
AppVersion={#AppVersion}
AppPublisher=Benelli Aerialist
DefaultDirName={localappdata}\Programs\Benelli Aerialist
UsePreviousAppDir=no
; Updates go straight into the existing folder: no folder page, no "folder exists" question.
DisableDirPage=auto
DirExistsWarning=no
DefaultGroupName=Benelli Aerialist
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=BenelliAerialist-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\BenelliAerialist.exe
SetupIconFile=aerialist.ico
; The licence page shows on a first install; updates skip it (see [Code]).
LicenseFile=..\LICENSE
ChangesAssociations=yes
CloseApplications=yes

[Files]
Source: "..\dist\BenelliAerialist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Benelli Aerialist"; Filename: "{app}\BenelliAerialist.exe"
Name: "{autodesktop}\Benelli Aerialist"; Filename: "{app}\BenelliAerialist.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Registry]
; A ProgID for PDFs opened with Benelli Aerialist
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.pdf"; ValueType: string; ValueData: "PDF Document"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.pdf\DefaultIcon"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.pdf\shell\open\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" ""%L"""
; List Benelli Aerialist under "Open with" for .pdf (does not take over the default app)
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "BenelliAerialist.pdf"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\BenelliAerialist.exe\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\BenelliAerialist.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Benelli Aerialist"
Root: HKA; Subkey: "Software\Classes\Applications\BenelliAerialist.exe\shell\open\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" ""%L"""
; Let Windows list Benelli Aerialist on its Default apps page (Settings > Apps > Default apps)
Root: HKA; Subkey: "Software\BenelliAerialist"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\BenelliAerialist\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Benelli Aerialist"
Root: HKA; Subkey: "Software\BenelliAerialist\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "View, sign, fill in and edit PDFs"
Root: HKA; Subkey: "Software\BenelliAerialist\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\BenelliAerialist\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "BenelliAerialist.pdf"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Benelli Aerialist"; ValueData: "Software\BenelliAerialist\Capabilities"; Flags: uninsdeletevalue

; Right-click in File Explorer (Windows 11: under "Show more options"). Explorer starts the app once per
; selected file; the first copy collects the rest. Pictures and PDFs get a Convert submenu (its entries live
; under BenelliAerialist.ConvertImage / .ConvertPdf); Office and text files get Convert to PDF.
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\1pdf"; ValueType: string; ValueName: "MUIVerb"; ValueData: "To PDF"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\1pdf"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\1pdf"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\1pdf\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\2png"; ValueType: string; ValueName: "MUIVerb"; ValueData: "To PNG picture"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\2png"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\2png"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\2png\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-png ""%L"""
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\3jpg"; ValueType: string; ValueName: "MUIVerb"; ValueData: "To JPG picture"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\3jpg"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\3jpg"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertImage\shell\3jpg\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-jpg ""%L"""
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\1word"; ValueType: string; ValueName: "MUIVerb"; ValueData: "To Word document"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\1word"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\1word"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\1word\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-word ""%L"""
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\2png"; ValueType: string; ValueName: "MUIVerb"; ValueData: "To PNG pictures (one per page)"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\2png"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\2png"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\2png\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-png ""%L"""
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\3jpg"; ValueType: string; ValueName: "MUIVerb"; ValueData: "To JPG pictures (one per page)"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\3jpg"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\3jpg"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\BenelliAerialist.ConvertPdf\shell\3jpg\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-jpg ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BenelliAerialist.Open"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Open in Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BenelliAerialist.Open"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BenelliAerialist.Open\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "ExtendedSubCommandsKey"; ValueData: "BenelliAerialist.ConvertPdf"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "ExtendedSubCommandsKey"; ValueData: "BenelliAerialist.ConvertImage"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "ExtendedSubCommandsKey"; ValueData: "BenelliAerialist.ConvertImage"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "ExtendedSubCommandsKey"; ValueData: "BenelliAerialist.ConvertImage"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "ExtendedSubCommandsKey"; ValueData: "BenelliAerialist.ConvertImage"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "ExtendedSubCommandsKey"; ValueData: "BenelliAerialist.ConvertImage"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "ExtendedSubCommandsKey"; ValueData: "BenelliAerialist.ConvertImage"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "ExtendedSubCommandsKey"; ValueData: "BenelliAerialist.ConvertImage"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "ExtendedSubCommandsKey"; ValueData: "BenelliAerialist.ConvertImage"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.doc\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docm\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docm\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docm\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docm\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docm\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docm\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docm\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docm\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dot\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dot\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dot\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dot\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dot\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dot\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dot\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dot\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dotx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dotx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dotx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dotx\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dotx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dotx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dotx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.dotx\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.wpd\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.wpd\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.wpd\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.wpd\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.wpd\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.wpd\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.wpd\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.wpd\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xls\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsx\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsm\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsm\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsm\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsm\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsm\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsm\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsm\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsm\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsb\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsb\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsb\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsb\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsb\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsb\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsb\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.xlsb\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.csv\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ods\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppt\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptm\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptm\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptm\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptm\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptm\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptm\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptm\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptm\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pps\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pps\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pps\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pps\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pps\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pps\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pps\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pps\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppsx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppsx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppsx\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppsx\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppsx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppsx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppsx\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ppsx\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odp\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.txt\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.text\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.text\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.text\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.text\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.text\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.text\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.text\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.text\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.log\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.log\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.log\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.log\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.log\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.log\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.log\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.log\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convert to PDF with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\BenelliAerialist.Convert"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\BenelliAerialist.Convert\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --convert-pdf ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Merge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\BenelliAerialist.Merge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\BenelliAerialist.Merge\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --merge ""%L"""

Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Resize pictures with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\BenelliAerialist.Resize\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --resize ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Resize pictures with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\BenelliAerialist.Resize\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --resize ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Resize pictures with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\BenelliAerialist.Resize\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --resize ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Resize pictures with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\BenelliAerialist.Resize\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --resize ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Resize pictures with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\BenelliAerialist.Resize\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --resize ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Resize pictures with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tif\shell\BenelliAerialist.Resize\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --resize ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Resize pictures with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tiff\shell\BenelliAerialist.Resize\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --resize ""%L"""
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Resize pictures with Benelli Aerialist"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\BenelliAerialist.exe"",0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Resize"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\BenelliAerialist.Resize\command"; ValueType: string; ValueData: """{app}\BenelliAerialist.exe"" --resize ""%L"""

[Run]
Filename: "{app}\BenelliAerialist.exe"; Description: "Open Benelli Aerialist now"; Flags: nowait postinstall skipifsilent

[Code]
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = wpLicense) and RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{7C1B6E52-3E0B-4C8B-9B8E-5D2B1D0BE11E}_is1');
end;
