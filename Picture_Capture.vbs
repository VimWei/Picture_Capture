' Picture Capture launcher.
' Runs run_windows.bat without a visible console window.
' The first run (no .venv yet) stays visible so uv setup progress can be seen.
' On failure it shows a message box and points at the launcher log.

Option Explicit

Dim shell, fso, env
Dim appDir, batPath, venvDir, q
Dim logDir, logPath, cmd, rc

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = fso.BuildPath(appDir, "run_windows.bat")
venvDir = fso.BuildPath(appDir, ".venv")
q = Chr(34)

logDir = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Picture_Capture"
If Not fso.FolderExists(logDir) Then
    fso.CreateFolder(logDir)
End If
logPath = fso.BuildPath(logDir, "launcher.log")

If Not fso.FolderExists(venvDir) Then
    ' First run: keep the console visible so uv can show setup progress.
    cmd = "cmd.exe /C " & q & q & batPath & q & q
    rc = shell.Run(cmd, 1, True)
Else
    ' Normal run: hide the console and capture output to the log file.
    Set env = shell.Environment("PROCESS")
    env("PC_HIDDEN") = "1"
    cmd = "cmd.exe /C " & q & q & batPath & q & " > " & q & logPath & q & " 2>&1" & q
    rc = shell.Run(cmd, 0, True)
End If

If rc <> 0 Then
    MsgBox "Picture Capture failed to start." & vbCrLf & vbCrLf & _
           "Exit code: " & rc & vbCrLf & _
           "Log file:  " & logPath & vbCrLf & vbCrLf & _
           "Recent log output:" & vbCrLf & TailOfFile(logPath, 30), _
           vbCritical, "Picture Capture"
End If

Function TailOfFile(path, maxLines)
    Dim stream, text, lines, i, start, result
    TailOfFile = ""
    If Not fso.FileExists(path) Then Exit Function
    On Error Resume Next
    Set stream = fso.OpenTextFile(path, 1, False)
    If Err.Number <> 0 Then
        Err.Clear
        On Error GoTo 0
        Exit Function
    End If
    text = stream.ReadAll
    stream.Close
    On Error GoTo 0
    lines = Split(Replace(text, vbCrLf, vbLf), vbLf)
    start = UBound(lines) - maxLines + 1
    If start < 0 Then start = 0
    result = ""
    For i = start To UBound(lines)
        If i > start Then result = result & vbCrLf
        result = result & lines(i)
    Next
    If Len(result) > 1800 Then result = "..." & Right(result, 1800)
    TailOfFile = result
End Function
