# QuantAM Automation Findings (Phase 0)

Investigated: 2026-04-19
Host: Windows 10.0.26200 (x64)
QuantAM versions installed on host:

- `C:\Program Files\Renishaw\Renishaw QuantAM 5.0.0.135`
- `C:\Program Files\Renishaw\Renishaw QuantAM 5.3.0.7105`
- `C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1` (target)

## 1. What was inspected

### 1.1 Install layout (QuantAM 6.1.0.1)

The install is a mixed-native + managed .NET desktop app. Notable components:

| Component                      | Type    | Purpose (inferred)                                   |
| ------------------------------ | ------- | ---------------------------------------------------- |
| `Renishaw QuantAM.exe`         | Native  | Application entry point.                             |
| `QuantAMAPI.dll`               | Native  | C++ API surface (no public C header shipped).        |
| `QuantAMAPIImpl.dll` + `.pta`  | Native  | API implementation and precompiled type archive.     |
| `QuantAM.ViewModels.dll`       | Managed | WPF view-models; contains UI bindings and commands.  |
| `QuantAM.UILibrary.dll`        | Managed | WPF controls; targets for UIA automation.            |
| `BuildFileReader/Writer.dll`   | Native  | `.mtt` I/O.                                          |
| `BuildFileValidator[New].dll`  | Native  | `.mtt` schema/parameter validation.                  |
| `Machines.Quantam.dll`         | Native  | AM400/400Q/500Q machine definitions.                 |
| `sqlite3.dll`                  | Native  | Internal persistence.                                |
| `TempMTT/`, `MappedData/`      | Dirs    | Runtime scratch areas for the current build.         |
| `Samples/Demo Parts/*.stl`     | Assets  | Shipped sample parts (used by our integration tests).|

### 1.2 Managed vs native verification

```powershell
[System.Reflection.AssemblyName]::GetAssemblyName("QuantAMAPI.dll")
# -> BadImageFormatException  (native)

[System.Reflection.AssemblyName]::GetAssemblyName("QuantAM.ViewModels.dll")
# -> QuantAM.ViewModels, Version=1.0.9102.12983, Culture=neutral  (managed)
```

### 1.3 Command-line surface

`Renishaw QuantAM.exe /?` does **not** print usage; the process launches the
GUI regardless of arguments. No public CLI export mode was discovered.

### 1.4 `.mtt` format

Per published references (Dyndrite, ANSYS), an `.mtt` is a ZIP archive
containing the STL geometry plus a machine parameter file. We will treat
`.mtt` as a ZIP for post-export verification (manifest inspection + SHA-256),
but we will **not** author `.mtt` bytes ourselves in v1 - only QuantAM writes
them. `libSLM` is intentionally excluded per product decision.

### 1.5 API logging

The install ships an `API_Log/` directory, suggesting QuantAM writes a log
whenever its internal API is exercised. This will be useful as a post-export
signal but is not a documented contract and must not be relied upon as a
single source of truth.

## 2. What was ruled out

| Candidate path                        | Status  | Reason                                                     |
| ------------------------------------- | ------- | ---------------------------------------------------------- |
| Direct `.mtt` authoring via `libSLM`  | Ruled out | Product decision: QuantAM-only for v1.                    |
| `pythonnet` loading `QuantAMAPI.dll`  | Ruled out | DLL is native (`BadImageFormatException`); no managed API.|
| `ctypes` loading `QuantAMAPI.dll`     | Ruled out | No public C header; exported symbols are undocumented.    |
| COM `Renishaw.*` ProgIDs              | Ruled out | No `Renishaw.*` ProgIDs registered under `HKCR\CLSID`.    |
| `QuantAM.exe` CLI export              | Ruled out | No documented switches; `/?` launches GUI.                |

## 3. Chosen automation path for v1

**UI Automation (UIA) via `pywinauto` (backend `"uia"`) + post-export
`.mtt` manifest verification.**

Rationale:

1. It is the only path that does not depend on undocumented internals.
2. UIA is stable across patch releases because WPF automation IDs are
   typically stamped by the `QuantAM.UILibrary.dll` view definitions.
3. Every export is verified: after QuantAM reports success, our client opens
   the produced `.mtt` as a ZIP, reads its manifest, confirms every expected
   STL is present, hashes the file, and only then signals success upstream.
4. If QuantAM is not installed, not licensed, not launchable, or does not
   produce a verifiable `.mtt`, the client raises a typed exception. The
   calling build transaction rolls back. No partial state is written.

### 3.1 Required automation IDs (to be captured)

Deferred to Phase 5 because they require an authenticated QuantAM session.
Phase 5 will:

1. Launch QuantAM under `pywinauto` with a known test project.
2. Enumerate the UIA tree and record the `automation_id` / `control_type`
   pairs for: **New Build**, **Add Part**, **Save Build As...**, **Export**,
   and the machine-selection dialog for AM400/400Q.
3. Persist these as module-level constants in
   `lpbf_serializer/quantam/uia_client.py` with the QuantAM build number
   they were captured against.

The Phase 5 implementation must refuse to run against a QuantAM version
other than the one used to capture the IDs, unless an operator explicitly
acknowledges the version skew. No silent fallback to "try a similar ID".

## 4. Risks and mitigations

| Risk                                                              | Mitigation                                                                  |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------- |
| QuantAM upgrades rename or remove automation IDs.                 | Pin captured IDs with version; fail-fast on mismatch; re-capture procedure. |
| UIA operations race with QuantAM's async layout.                  | Use `wait('ready')` / `wait('exists')` with bounded timeouts; no sleeps.    |
| `.mtt` produced but semantically invalid.                         | Verify ZIP manifest, entry names, required machine file, SHA-256 stamp.    |
| License pop-ups or modal dialogs interrupt automation.            | Treat any unexpected modal as a hard error; raise `QuantAMUnexpectedDialog`.|
| Concurrent QuantAM instance interferes.                           | `QuantAMClient.health_check()` enforces single instance via `psutil`.      |

## 5. Contract summary

The rest of the system depends only on this contract (see
`lpbf_serializer/quantam/client.py`):

```python
class QuantAMClient(Protocol):
    def health_check(self) -> QuantAMInfo: ...
    def export_build(self, request: ExportRequest) -> ExportResult: ...
    def verify_mtt(self, path: Path) -> MttManifest: ...
```

If the UIA path later becomes inadequate and Renishaw provides an SDK, the
adapter behind this `Protocol` changes; nothing else does.
