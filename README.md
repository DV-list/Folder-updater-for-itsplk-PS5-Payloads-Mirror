# Folder updater for itsplk PS5 Payloads Mirror

Folder updater for itsPLK PS5 Payloads Mirror is a simple tool for tracking PS5 payload files in a local folder on your PC or Mac, checking for updates, and keeping them up to date. It helps you keep your PS5 offline while managing and updating useful payloads on your computer. Payloads are sourced from [itsPLK PS5 Payloads Mirror](https://itsplk.github.io/ps5-payloads-mirror/).
<br>

<img width="1817" height="930" alt="app" src="https://github.com/user-attachments/assets/864ce1fc-a5df-462c-95b2-a353adbfed1e" />

## Features

- **Local payload inventory** — scans the selected application folder for `.elf` files.
- **Version and checksum checks** — calculates SHA-256 checksums and compares local files with the online payload catalog.
- **Update status at a glance** — shows payload names, filenames, local and server versions, checksums, timestamps, and status.
- **Download on demand** — offers eligible downloads through the GUI instead of silently downloading the control app during startup.
- **Download verification** — verifies downloaded content and handles supported ZIP extraction safely.
- **Automatic rescans** — periodically reconciles the local folder with the saved state and catalog.
- **Manual control** — lets you mark a row as `MANUAL` using the Pre-release checkbox for aplha, beta payloads, downloaded manually, not listed on <https://itsplk.github.io/ps5-payloads-mirror>.
- **ps5upload control app support** - lets you download and update a control app for <https://github.com/phantomptr/ps5upload>.

## How it works

1. Place the application in the folder you want to monitor.
2. Launch it to scan local `.elf` files and compare them with the online catalog.
3. Review the status shown for each payload. When a download is offered, confirm it in the GUI to start.
4. The application verifies downloaded content and refreshes the inventory after the operation.

For module boundaries, testing conventions, and GUI sizing rules, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Claude Sonnet 5.5 static review of the code
<details>
<summary>Verdict: CLEAN for malicious behavior (source only), with integrity-design weaknesses</summary>
<br>
https://github.com/DV-list/Folder-updater-for-itsplk-PS5-Payloads-Mirror/blob/12d209db5d5d2a964644c1eeac5d15bd2da508b6/security-review-folder-updater-1.9.12.md
</details>

## Build from source
<details>
<summary>Windows, macOS, and Linux</summary>
<br>
Build the application separately on each target operating system. **PyInstaller is not a cross-compiler**: a Windows build must be produced on Windows, a macOS build on macOS, and a Linux build on Linux. See the [PyInstaller documentation](https://pyinstaller.org/en/stable/usage.html#supporting-multiple-operating-systems).
The commands read the version from `app/version.py` and use it in the build name. Run them from the project directory containing `main.py` and `requirements.txt`.

### Windows (PowerShell)

Install Python, then run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
$APP_VERSION = python -c "from app.version import APP_VERSION; print(APP_VERSION)"
python -m PyInstaller --clean --onefile --noconsole --optimize 2 --collect-data customtkinter --hidden-import customtkinter --exclude-module unittest --exclude-module test --exclude-module tkinter.test --exclude-module idlelib --exclude-module pydoc_data --exclude-module pytest --exclude-module IPython --exclude-module notebook --name "Folder updater for itsplk PS5 Payloads Mirror v$APP_VERSION" main.py
```

Output: `dist\Folder updater for itsplk PS5 Payloads Mirror v{APP_VERSION}.exe`.

If PowerShell blocks environment activation, use Command Prompt activation instead: `.venv\Scripts\activate.bat`.

### macOS (Terminal)

Use a Python installation with working Tcl/Tk support. The current installers from [python.org](https://www.python.org/download/mac/tcltk/) include Tcl/Tk. Check it by running `python3 -m tkinter`; a small test window should open.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
APP_VERSION="$(python -c 'from app.version import APP_VERSION; print(APP_VERSION)')"
python -m PyInstaller --clean --onefile --windowed --optimize 2 --collect-data customtkinter --hidden-import customtkinter --exclude-module unittest --exclude-module test --exclude-module tkinter.test --exclude-module idlelib --exclude-module pydoc_data --exclude-module pytest --exclude-module IPython --exclude-module notebook --name "Folder updater for itsplk PS5 Payloads Mirror v${APP_VERSION}" main.py
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
APP_VERSION="$(python -c 'from app.version import APP_VERSION; print(APP_VERSION)')"
python -m PyInstaller --clean --onefile --optimize 2 --collect-data customtkinter --hidden-import customtkinter --exclude-module unittest --exclude-module test --exclude-module tkinter.test --exclude-module idlelib --exclude-module pydoc_data --exclude-module pytest --exclude-module IPython --exclude-module notebook --name "Folder updater for itsplk PS5 Payloads Mirror v${APP_VERSION}" main.py
```

Output: `dist/Folder updater for itsplk PS5 Payloads Mirror v{APP_VERSION}` (a native Linux executable, with no `.exe` extension). Build on a Linux distribution compatible with the oldest system you intend to support, then test the binary on that system.
</details>

## Payload catalog

The application uses the public catalog maintained by **itsplk** project:

<https://itsplk.github.io/ps5-payloads-mirror/payloads.json>
