Set ws = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

pyExe = FindPython("python.exe")
If pyExe = "" Then MsgBox "找不到 Python，请安装 Python 3" : WScript.Quit

ws.Run "cmd /k """ & pyExe & """ """ & scriptDir & "\gemini_imggen.py""", 1, False

Function FindPython(exeName)
    Dim paths, p, localApp
    FindPython = ""
    localApp = ws.ExpandEnvironmentStrings("%LOCALAPPDATA%")
    paths = Array( _
        localApp & "\Programs\Python\Python314\" & exeName, _
        localApp & "\Programs\Python\Python313\" & exeName, _
        localApp & "\Programs\Python\Python312\" & exeName, _
        "C:\Python314\" & exeName, _
        "C:\Python313\" & exeName, _
        "C:\Python312\" & exeName)
    For Each p In paths
        If fso.FileExists(p) Then FindPython = p : Exit Function
    Next
End Function
