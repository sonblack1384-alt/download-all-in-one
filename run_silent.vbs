' Chạy app.py ngầm, không hiện cửa sổ đen (console).
' Dùng cho: để file này vào thư mục Startup của Windows để tự chạy khi đăng nhập.
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "pythonw app.py", 0, False
