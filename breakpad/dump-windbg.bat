@rem Usage: dump-windbg.bat <dump file> [<PDB folder>]
@rem The PDB folder defaults to the dump file's one; WinDbg's folder is WINDBG_PATH.

@if not defined WINDBG_PATH set "WINDBG_PATH=C:\Program Files (x86)\Windows Kits\10\Debuggers\x86"

@set "DUMP_FILE=%~1"
@set "PDB_PATH=%~2"
@if not defined PDB_PATH set "PDB_PATH=%~dp1."

"%WINDBG_PATH%\windbg.exe" -y "%PDB_PATH%" -i "%PDB_PATH%" -z "%DUMP_FILE%" -sflags 0x40 -c ".ecxr;k"
