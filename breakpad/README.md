# breakpad

`dump-windbg.bat` opens a crash dump (e.g. Breakpad's minidump) in WinDbg with the program's PDB
files and shows the exception's call stack (`.ecxr; k`):

```bat
dump-windbg.bat <dump file> [<PDB folder>]
```

- The PDB folder defaults to the dump file's folder: put the build's `.pdb` files next to the dump.
- WinDbg's folder is `WINDBG_PATH`, by default the Windows Kits' x86 one
  (`C:\Program Files (x86)\Windows Kits\10\Debuggers\x86`).
