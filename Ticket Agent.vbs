Option Explicit
Dim fs, sh, here, root, pythonw, entry, mode, command, waitForSetup, rc
Set fs = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
here = fs.GetParentFolderName(WScript.ScriptFullName)
root = here
If Not fs.FileExists(fs.BuildPath(root, "bootstrap\desktop_setup.py")) Then
    root = fs.GetParentFolderName(here)
End If
pythonw = fs.BuildPath(root, "bootstrap\pythonw.exe")
entry = fs.BuildPath(root, "bootstrap\desktop_setup.py")
If Not fs.FileExists(pythonw) Or Not fs.FileExists(entry) Then
    MsgBox "Please extract the full Ticket Agent ZIP to an empty folder, then open Ticket Agent.vbs.", 16, "Ticket Agent"
    WScript.Quit 2
End If
mode = ""
waitForSetup = False
If WScript.Arguments.Count = 1 Then
    Select Case LCase(WScript.Arguments(0))
        Case "live": mode = " --live"
        Case "shortcuts": mode = " --shortcuts"
        Case "prepare-only"
            mode = " --prepare-only"
            waitForSetup = True
    End Select
End If
sh.CurrentDirectory = root
command = """" & pythonw & """ -I -B """ & entry & """" & mode
rc = sh.Run(command, 1, waitForSetup)
WScript.Quit rc

