# Folder updater for itsplk PS5 Payloads Mirror

Folder updater for itsplk PS5 Payloads Mirror is the solution to keep your console offline and update useful payloads from a desired folder on your PC/Mac. Payloads are collected using <https://itsplk.github.io/ps5-payloads-mirror>.

## Features

- **Local payload inventory** — scans the selected application folder for `.elf` files.
- **Version and checksum checks** — calculates SHA-256 checksums and compares local files with the online payload catalog.
- **Update status at a glance** — shows payload names, filenames, local and server versions, checksums, timestamps, and status.
- **Download on demand** — offers eligible downloads through the GUI instead of silently downloading the control app during startup.
- **Download verification** — verifies downloaded content and handles supported ZIP extraction safely.
- **Persistent state and history** — records local payload state in `appdata/local-state.json` and keeps application logs and configuration under `appdata/`.
- **Automatic rescans** — periodically reconciles the local folder with the saved state and catalog.
- **Pre-release control** — lets you mark a row as `MANUAL` using the Pre-release checkbox.

## How it works

1. Place the application in the folder you want to monitor.
2. Launch it to scan local `.elf` files and compare them with the online catalog.
3. Review the status shown for each payload. When a download is offered, confirm it in the GUI to start.
4. The application verifies downloaded content and refreshes the inventory after the operation.

## Build from source (Windows, macOS, and Linux)

Build the application separately on each target operating system. **PyInstaller is not a cross-compiler**: a Windows build must be produced on Windows, a macOS build on macOS, and a Linux build on Linux. See the [PyInstaller documentation](https://pyinstaller.org/en/stable/usage.html#supporting-multiple-operating-systems).

The commands below use the v1.9.5 output name. Change `v1.9.5` in the `--name` value to match the version being built. Run these commands from the project directory containing `main.py` and `requirements.txt`.

### Windows (PowerShell)

Install Python, then run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --clean --onefile --noconsole --optimize 2 --collect-data customtkinter --hidden-import customtkinter --exclude-module unittest --exclude-module test --exclude-module tkinter.test --exclude-module idlelib --exclude-module pydoc_data --exclude-module pytest --exclude-module IPython --exclude-module notebook --name "Folder updater for itsplk PS5 Payloads Mirror v1.9.5" main.py
```

Output: `dist\Folder updater for itsplk PS5 Payloads Mirror v1.9.5.exe`.

If PowerShell blocks environment activation, use Command Prompt activation instead: `.venv\Scripts\activate.bat`.

### macOS (Terminal)

Use a Python installation with working Tcl/Tk support. The current installers from [python.org](https://www.python.org/download/mac/tcltk/) include Tcl/Tk. Check it by running `python3 -m tkinter`; a small test window should open.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --clean --onefile --windowed --optimize 2 --collect-data customtkinter --hidden-import customtkinter --exclude-module unittest --exclude-module test --exclude-module tkinter.test --exclude-module idlelib --exclude-module pydoc_data --exclude-module pytest --exclude-module IPython --exclude-module notebook --name "Folder updater for itsplk PS5 Payloads Mirror v1.9.5" main.py
```

PyInstaller's `--windowed` option creates a macOS `.app` bundle. The exact output is under `dist/`; verify the produced bundle on the macOS versions and CPU architectures you intend to support. Apple Silicon and Intel builds may require different Python environments or target architectures.

### Linux (Terminal; Debian/Ubuntu example)

Install Python, venv support, and Tkinter if they are not already available:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-tk
```

Then build the executable:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --clean --onefile --optimize 2 --collect-data customtkinter --hidden-import customtkinter --exclude-module unittest --exclude-module test --exclude-module tkinter.test --exclude-module idlelib --exclude-module pydoc_data --exclude-module pytest --exclude-module IPython --exclude-module notebook --name "Folder updater for itsplk PS5 Payloads Mirror v1.9.5" main.py
```

Output: `dist/Folder updater for itsplk PS5 Payloads Mirror v1.9.5` (a native Linux executable, with no `.exe` extension). Build on a Linux distribution compatible with the oldest system you intend to support, then test the binary on that system.

### Before distributing

- Run the built application on the target OS; a successful package build alone does not confirm that every OS-specific interaction works.
- On macOS, verify application launch and security-signing/notarization requirements for your distribution method.
- On Linux, ensure Tkinter and required system libraries are available on the target machine.
- The Python source remains runnable directly after installing `requirements.txt`, provided Python and Tcl/Tk are installed.

## Payload catalog

The application uses the public catalog maintained by the project:

<https://itsplk.github.io/ps5-payloads-mirror/payloads.json>

