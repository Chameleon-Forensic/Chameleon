
# 🛡️ BitGuard

**Hash-verified remote forensic imaging tool with chunk-level self-healing and automatic chain-of-custody reporting.**

BitGuard solves a problem most acquisition tools ignore: proving — cryptographically and on paper — that a remotely acquired image is byte-for-byte identical to its source, without expensive licensed tooling or a fragile manual pipeline.

<!-- 📸 REPLACE THIS LINE WITH A SCREENSHOT OR GIF OF THE APP -->
<!-- ![BitGuard screenshot](docs/screenshot.png) -->

---

## Why BitGuard?

| | `dd` + `netcat` | EnCase / FTK Imager | **BitGuard** |
|---|---|---|---|
| Automatic hash verification | ❌ | ✅ | ✅ |
| Self-healing on corruption | ❌ | ❌ (restart from scratch) | ✅ **(only the bad chunk is re-sent)** |
| Chain-of-custody report | ❌ | Partial | ✅ (JSON + TXT + HTML) |
| Post-acquisition re-verification | ❌ | ❌ | ✅ |
| Built-in encryption | ❌ | Varies | ✅ TLS 1.3 |
| Cost | Free | $$$$ licensed | Free |
| Setup | CLI, manual | Heavy install | Single `.py` / `.exe` |

## ✨ Key Features

- 🔐 **Chunk-level self-healing transfer** — every 4MB chunk is individually SHA-256 hashed. If a chunk fails verification on arrival, only *that chunk* is automatically re-requested (up to 3 rounds) — no need to restart a multi-hour transfer over a single corrupted chunk.
- 🔁 **Post-acquisition re-verification** — re-hash an already-acquired image at any point (e.g. before a court hearing) and prove it hasn't been altered. Every check is automatically logged into the original report's audit trail.
- 🔒 **TLS 1.3 encryption** — bundled self-signed certificate, zero external dependencies (no `openssl` install required).
- 📋 **Automatic chain-of-custody reporting** — every transfer produces a machine-readable `.json`, a human-readable `.txt`, and a styled `.html` report (printable to PDF).
- 💽 **Write-blocked acquisition** — sources are always opened read-only; OS-reported write-protection status is logged.
- 📦 **Multiple formats** — RAW/DD, gzip, and simplified E01-style / AFF4-style containers.
- 🖥️ **Cross-platform** — same codebase runs on Windows and Linux; disk discovery via `lsblk` or PowerShell automatically.

## 🖼️ Screenshots

<!-- Add 2-4 screenshots here once you have them, e.g.: -->
<!--
| Client — Connect | Progress & Verification |
|---|---|
| ![connect](docs/connect.png) | ![progress](docs/progress.png) |
-->

## 🚀 Getting Started

### Requirements
- Python 3.9+
- No external dependencies for core functionality (uses only the standard library)

### Run it
```bash
python forensic_gui.py
```

Run the same script on both machines:
- **Server tab** on the machine you want to image *from*
- **Client tab** on the machine you want to save the image *to*

### Build a standalone .exe (Windows)
```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name BitGuard forensic_gui.py
```

## 🏗️ How It Works

```
 SERVER (source)                          CLIENT (destination)
 ─────────────────                        ─────────────────────
 Reads source in                          Browses remote disks/
 4MB chunks, hashes                       files, selects source
 each one as it goes    ──── TLS ────►    Verifies each chunk's
 Sends chunk + hash                       hash on arrival
                                           │
                        ◄── resend? ───    Mismatch? → requests
                                           only that chunk again
                                           │
                                           Atomic rename + chmod
                                           read-only + JSON/TXT/
                                           HTML report generated
```

## 🔬 Engineering Decisions & Honest Limitations

This project deliberately documents what it does *not* claim to do:

- **E01 / AFF4 formats** are simplified custom containers (embedded metadata + compression + hash), built with Python's standard library only. They are **not byte-compatible** with EnCase/FTK's official EWF reader or the official AFF4 RDF spec.
- **TLS** provides encryption against passive network eavesdropping, not full PKI authentication (the bundled certificate is self-signed and shared across installs by design, since both endpoints are machines the operator already controls).
- **RAM imaging** was attempted and removed — both Windows (since Vista) and modern Linux kernels (`CONFIG_STRICT_DEVMEM`) block direct physical memory access from user space. Rather than fake a "working" feature, this was cut in favor of the acquisition paths that are genuinely reliable.

## 🎓 Background

Built as a digital forensics coursework project. The goal was to explore what a *minimal but genuinely trustworthy* acquisition tool looks like — and along the way, to catch and fix a real integrity bug in an early SSH-based acquisition mode that could have silently reported unverified data as "verified." That experience shaped the project's current emphasis on independently-computed, source-side hashing for every verification claim it makes.


## 🙋 Author

Built by Mehmet Emin Yeter — [[LinkedIn](https://www.linkedin.com/in/mehmeteminyeter/)]

Zehra Nur Kolsuz - [[LinkedIn](https://www.linkedin.com/in/zehrakolsuz)]

Mehmet Alperen Şengül - [[LinkedIn](https://www.linkedin.com/in/mehmetalperen/)]
