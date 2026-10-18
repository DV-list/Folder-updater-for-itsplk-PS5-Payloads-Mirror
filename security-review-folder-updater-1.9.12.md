> # Static Security Review: Folder updater for itsplk PS5 Payloads Mirror v1.9.12
>
> ## Verdict: CLEAN for malicious behavior (source only), with integrity-design weaknesses
>
> **Confidence:** high that no malicious code exists in the reviewed source. Medium overall, because of the scope limits below.
>
> **Scope:** the archive is `Folder-updater-…-1_9_12.zip` (SHA-256 `c2ba60a34a8ab4159c04582c2871218bceb6de85defafb821282abb50cdf38a1`). Its comment field is `765633be9d21bf8650b672e9a8d28b68c7a7b6f3`, which matches the pinned commit. `app/version.py:3` says `1.9.12`.
>
> **Reasoning:**
>
> | Check | Result |
> |---|---|
> | Obfuscation or dynamic execution | No `base64`, `eval`, `exec`, `compile`, `marshal`, `pickle` or `__import__` in `app/`, `main.py` or the workflow. No lines over 400 characters except one config string (`user_config.py:8`). |
> | Reverse shell, persistence, privilege escalation | No raw-socket use beyond `getaddrinfo` DNS checks. No `winreg`, startup, scheduled-task or service code. |
> | Data collection or exfiltration | Only two outbound request types (see below). Neither reads or sends user data beyond a User-Agent string containing the app version. No `os.environ`, `getenv`, clipboard, credential or browser-data access. No system fingerprinting beyond `sys.frozen` and `sys.executable`. |
> | Execution of downloaded content | The only `subprocess.Popen` calls are `explorer.exe` (`gui.py:531,534`), with a path constrained to the app directory (`gui.py:530`). Downloaded files are never launched. |
> | Hardcoded secrets or IPs | None found. The only IP literal is the `198.18.0.0/15` range (see finding 4). |
>
> ## Findings
>
> | # | Severity | file:line | Snippet / fact | Behavior | Risk |
> |---|---|---|---|---|---|
> | 1 | **Medium** | `ps5upload_control_app_dl.py:406,456,464,237,286`; `application.py:259-260` | `digest = hashlib.sha256()` is fed from the download. `asset_checksum` is returned, then compared to the staged and final copies. | The control-app asset is "verified" only against a hash of itself. The code comment at `application.py:259` says the catalog checksum belongs to the ELF, not this asset. | No integrity check against a trusted value. Safety rests on TLS, GitHub and the catalog. A compromised upstream release or catalog delivers arbitrary files. The tool never runs them, but the user presumably will. `README.md:11,21` ("Download verification") overstates this path. |
> | 2 | **Medium** | `payload_catalog.py:119-120,149`; `updater.py:100,106,112` | The ELF URL (`source_direct`) and checksum come from the same `payloads.json`. | Checksum and URL share one trust root, with no signature. | Compromise of `itsplk.github.io/ps5-payloads-mirror` yields an arbitrary ELF plus a matching checksum. This is an inherent design limit, not a bug. |
> | 3 | Low | `updater.py:323-330` | Checks cover scheme, hostname, credentials and port only. | `source_direct` may be any public HTTPS host. | Widens finding 2 beyond GitHub hosts. |
> | 4 | Low | `updater.py:355-358,364`; `ps5upload_control_app_dl.py:384-388,389` | `198.18.0.0/15` is accepted for any host. GitHub-owned hosts may resolve to non-public IPs. | Weakens the SSRF filter. Validation resolves DNS at `updater.py:336` and `ps5upload_control_app_dl.py:373`, then urllib resolves again at `updater.py:199` and `ps5upload_control_app_dl.py:414`. | Small DNS-rebinding window. Exploiting it requires control of the catalog or DNS. |
> | 5 | Low | `payload_catalog.py:59`; `ps5upload_control_app_dl.py:495,40` | `response.read()` has no size cap. Downloads are capped at 512 MiB (`updater.py:36`, `ps5upload_control_app_dl.py:39`). ZIP limits are 4×512 MiB declared size and 10,000 members. | Resource-exhaustion limits are partial. | A hostile catalog host could cause memory or disk exhaustion. |
> | 6 | Low | `application.py:427-441`; `gui.py:239,366-388`; `RELEASE_NOTES.md` bullet 1 | The UPDATE button calls `ensure_client()` with no separate confirm dialog. Confirms exist only for download rows (`gui.py:496,510`). | A control-app download and replace runs on one UPDATE click. `needs_update` returns True when the installed version is unknown (`ps5upload_control_app_dl.py:100`). | User-initiated but not individually confirmed. It differs from `README.md:20`. Replacement moves the old folder to `_OLD` (`:273-279`), so it is non-destructive. |
> | 7 | Low | `ps5upload_control_app_dl.py:102-112,264-278` | Any folder whose name starts with `ps5upload` or equals `Payload` is moved to `_OLD`. | Matching is by name only. | An unrelated user folder could be relocated. It is moved, not deleted. |
> | 8 | Low | `build-windows.yml:40,43,106,122,129,57-59`; `requirements.txt:2` | Actions are pinned to mutable tags, including third-party `softprops/action-gh-release@v2` with `contents: write` (`:118-119`). `pyinstaller` is unpinned. `customtkinter>=5.2.2,<6.0` is a range with no hashes. | The build is not reproducible, and there is no signing or provenance. | Standard supply-chain exposure. Tag-triggered release is gated at `:115`. |
> | 9 | Info | `payload_catalog.py:20` | `USER_AGENT = "Folder-updater/1.9.10"` is hardcoded and stale. | Cosmetic. | None. |
>
> **Positive controls (facts):**
>
> - HTTPS only, with TLS validation left at urllib defaults.
> - Every redirect hop is re-validated (`updater.py:190-210`, `ps5upload_control_app_dl.py:409-429`).
> - Filenames must be plain `.elf` names (`updater.py:376-383`).
> - ZIP path-traversal and symlink checks are present (`ps5upload_control_app_dl.py:487-505`).
> - Existing files are moved to `_OLD` rather than deleted (`updater.py:123,130`).
> - The only `rmtree` calls target the staged or newly installed folder (`ps5upload_control_app_dl.py:294,313`).
>
> ## External domains and what is sent
>
> | Domain | Where in code | Trigger | Data sent |
> |---|---|---|---|
> | `itsplk.github.io/ps5-payloads-mirror/payloads.json` | `config.py:14`, `payload_catalog.py:39-47` | Startup and UPDATE | HTTP GET with `User-Agent: Folder-updater/1.9.10`. Nothing else. |
> | `source_direct` host from the catalog (runtime value) | `updater.py:176-252`, `downloader.py:53-68` | A confirmed download or UPDATE | GET with `Folder-updater/<version>` User-Agent. **Not statically enumerable.** Redirect targets are also runtime values. |
> | Control-app URL, derived from `source_direct` plus the platform suffix | `ps5upload_control_app_dl.py:61,399-472` | UPDATE or a confirmed download row | GET with `Folder-updater-ps5upload-control-app/<version>` User-Agent. |
> | `github.com/itsPLK/ps5-payloads-mirror` | `config.py:13`, `gui.py:222` | Link click | Opens in the default browser. |
> | `github.com/phantomptr/ps5upload/releases` | `user_config.py:8` | **Config comment text only. Never contacted.** | None. |
>
> **Local writes:**
>
> - `appdata/application.log`
> - `appdata/local-state.json`
> - `appdata/config.ini`
> - `_OLD/`
> - Temporary files in the app folder
>
> Logs contain filenames, URLs without query strings, and checksums.
>
> ## Not analyzed
>
> | Item | Why |
> |---|---|
> | Released binaries (`.exe`, `.app` zip, Linux zip) | Not provided. I did not compare them to this source. |
> | Transitive dependencies (`customtkinter` and its dependencies, PyInstaller) | Source not provided. |
> | Live `payloads.json` contents and `source_direct` targets | Runtime data, not in the archive. |
> | Downloaded ps5upload control app | Not in the archive. |
> | `gui.py` (1051 lines) and `reconciler.py` (195 lines) | **Not read line by line.** Whole-file pattern scans found no network, exec or file-operation hits beyond those listed, and I read the specific GUI sections cited. Logic bugs there are not ruled out. |
> | `tests/` | Pattern-scanned only. The CI step `python -m unittest discover` executes them. Their only hits are mocked `urlopen` and `getaddrinfo` patches (`test_payload_catalog.py:37`, `test_redirect_security.py:29-38`). |
>
> ## Hypothesis (unverified)
>
> Earlier search snippets showed releases v1.9.5 and v1.9.11 as "released by DV-list", and v1.9.4 as "Add files via upload". `build-windows.yml:129` would normally publish as a bot. The release assets may therefore have been uploaded manually rather than built by this workflow. I could not verify this.
>
> ## Recommended actions
>
> 1. Treat the repository and the release binaries as separate trust decisions. Build from this source yourself, or compare hashes with the release assets.
> 2. For finding 1, verify the downloaded control-app archive manually against upstream release checksums before running it. Alternatively set `Enabled = false` under `[ps5upload-control-app-dl]` in `appdata/config.ini`.
> 3. Keep `DownloadOnlyWhenPS5UploadCurrent = true` (the default).
> 4. **Risk:** UPDATE moves files in the app folder. Back up first (replace the placeholders):
>
> ```bash
> # Linux/macOS
> cp -a "XX_APP_FOLDER_XX" "XX_BACKUP_FOLDER_XX"
> ```
>
> ```powershell
> # Windows
> Copy-Item -Recurse "XX_APP_FOLDER_XX" "XX_BACKUP_FOLDER_XX"
> ```
>
> 5. If you want the binaries checked, upload the specific release asset and I can do limited static analysis (strings, imports, embedded PyInstaller archive listing). It will not prove the binary matches this source.
