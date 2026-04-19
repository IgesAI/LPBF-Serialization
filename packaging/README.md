# Packaging LPBF Serializer for Windows

## Prerequisites

- Windows 10/11 x64
- QuantAM 6.1.0.1 installed (target runtime)
- [uv](https://docs.astral.sh/uv/) on PATH
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (for the installer step)

## Build the one-folder bundle

From the repository root:

```powershell
uv sync
uv run pyinstaller packaging/lpbf-serializer.spec
```

This produces `dist/LPBFSerializer/LPBFSerializer.exe` along with every
runtime dependency (VTK, Qt, trimesh data files, etc.) beside it.

## Build the Windows installer

After the bundle exists:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
```

The installer is written to `dist-installer/LPBFSerializer-0.1.0-setup.exe`.

At install time the installer checks for `Renishaw QuantAM 6.1.0.1` at its
canonical path and aborts with an explicit error if it is missing; there
is no silent install.

## Sanity test after install

1. Launch **LPBF Serializer** from the Start menu.
2. Confirm the status bar reports `QuantAM: 6.1.0.1`.
3. Import a sample STL (for example, one from
   `C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1\Samples\Demo Parts\`).
4. Click **Save Build**. If UIA IDs for this QuantAM version have not been
   captured yet, the app will raise `QuantAMExportFailedError`. In that
   case, follow
   [`docs/quantam-automation-findings.md`](../docs/quantam-automation-findings.md)
   to capture them.
