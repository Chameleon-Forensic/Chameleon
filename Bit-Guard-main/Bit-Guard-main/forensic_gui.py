#!/usr/bin/env python3
"""
BitGuard - Forensic Remote Imaging Tool (GUI Application)
----------------------------------------------------------------
Flow:
  1) SERVER side: no need to pre-select a source. Just start
     listening; it can be stopped at any time with "Stop Server".
  2) CLIENT side: "Connect & Select Source" connects to the server
     and opens a remote file/disk browser window. The connection can
     be cancelled at any time with "Cancel / Disconnect".
  3) Once the client selects a file, folder, or disk, the server
     streams it (folders are automatically packaged as a tar archive).
  4) Transfer + SHA-256 verification + exclusive lock + atomic rename
     + read-only protection + chain-of-custody report all still apply.
"""

import base64
import gzip
import hashlib
import json
import math
import os
import platform
import re
import socket
import ssl
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import zipfile
import zlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

APP_NAME = "BitGuard"
APP_TAGLINE = "Forensic Remote Imaging Tool"

# Embedded 64x64 app icon (base64 PNG) so the script is fully self-contained
# and does not depend on an external image file at runtime.
ICON_B64 = (
    "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"
    "LH28/D82Y6RPIr1tEAAAAABJRU5ErkJggg=="
)

def resource_path(relative_path):
    """Resolve a bundled resource whether run as a script or as a
    PyInstaller-frozen .exe (which unpacks files into _MEIPASS)."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB

# Two full color palettes -- current theme is applied to the COLOR_*
# names below via apply_theme(). Widgets read these module-level names
# at construction time, so switching themes rebuilds the UI so every
# widget picks up the new values.
THEMES = {
    "dark": {
        "BG": "#14141f", "PANEL": "#1f1f30", "ACCENT": "#8b5cf6", "ACCENT2": "#22d3ee",
        "TEXT": "#f4f4f6", "MUTED": "#a5a5c0", "OK": "#10e090", "ERR": "#ff4d6d",
        "WARN": "#ffb020", "LOG_BG": "#0c0c14",
    },
    "light": {
        "BG": "#f3f4f8", "PANEL": "#ffffff", "ACCENT": "#7c3aed", "ACCENT2": "#0891b2",
        "TEXT": "#1f2430", "MUTED": "#666b80", "OK": "#128a4e", "ERR": "#c0273d",
        "WARN": "#b7690a", "LOG_BG": "#eef0f5",
    },
}

CURRENT_THEME = "dark"
COLOR_BG = THEMES[CURRENT_THEME]["BG"]
COLOR_PANEL = THEMES[CURRENT_THEME]["PANEL"]
COLOR_ACCENT = THEMES[CURRENT_THEME]["ACCENT"]
COLOR_ACCENT2 = THEMES[CURRENT_THEME]["ACCENT2"]
COLOR_TEXT = THEMES[CURRENT_THEME]["TEXT"]
COLOR_MUTED = THEMES[CURRENT_THEME]["MUTED"]
COLOR_OK = THEMES[CURRENT_THEME]["OK"]
COLOR_ERR = THEMES[CURRENT_THEME]["ERR"]
COLOR_WARN = THEMES[CURRENT_THEME]["WARN"]
COLOR_LOG_BG = THEMES[CURRENT_THEME]["LOG_BG"]


def apply_theme(name):
    """Switches the active color palette. Callers must rebuild any
    already-constructed widgets afterwards for the new colors to show."""
    global CURRENT_THEME, COLOR_BG, COLOR_PANEL, COLOR_ACCENT, COLOR_ACCENT2
    global COLOR_TEXT, COLOR_MUTED, COLOR_OK, COLOR_ERR, COLOR_WARN, COLOR_LOG_BG
    t = THEMES[name]
    CURRENT_THEME = name
    COLOR_BG = t["BG"]
    COLOR_PANEL = t["PANEL"]
    COLOR_ACCENT = t["ACCENT"]
    COLOR_ACCENT2 = t["ACCENT2"]
    COLOR_TEXT = t["TEXT"]
    COLOR_MUTED = t["MUTED"]
    COLOR_OK = t["OK"]
    COLOR_ERR = t["ERR"]
    COLOR_WARN = t["WARN"]
    COLOR_LOG_BG = t["LOG_BG"]


def ts():
    return time.strftime("%H:%M:%S")


def human_size(num_bytes):
    if num_bytes is None:
        return "-"
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def human_speed(num_bytes, seconds):
    if seconds <= 0:
        return "-"
    return human_size(num_bytes / seconds) + "/s"


# ----------------------------------------------------------------------
# Network protocol helpers (newline-delimited JSON messages)
# ----------------------------------------------------------------------
class StopRequested(Exception):
    """Raised internally when the user cancels/stops an operation."""
    pass


def send_json(sock, obj):
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))


def recv_line(sock, stop_check=None):
    """
    Reads a newline-terminated message. If the socket has a timeout set,
    a socket.timeout is treated as "no data yet" and retried, UNLESS
    stop_check() returns True, in which case StopRequested is raised so
    the caller can cleanly abort a blocked read.
    """
    buf = b""
    while True:
        try:
            b = sock.recv(1)
        except socket.timeout:
            if stop_check is not None and stop_check():
                raise StopRequested()
            continue
        if not b or b == b"\n":
            break
        buf += b
    return buf.decode("utf-8")


def recv_json(sock, stop_check=None):
    line = recv_line(sock, stop_check)
    if not line:
        return None
    return json.loads(line)


def recv_exact(sock, n, stop_check=None):
    """Reads exactly n bytes, retrying on socket.timeout (so Cancel can
    interrupt cleanly via stop_check) and raising if the connection
    closes before n bytes arrive."""
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except socket.timeout:
            if stop_check is not None and stop_check():
                raise StopRequested()
            continue
        if not chunk:
            raise ConnectionError("Connection closed before all expected data arrived.")
        buf += chunk
    return buf


# A bundled, pre-generated self-signed TLS certificate + private key
# (RSA-2048, 10-year validity, CN=BitGuard-Local). Embedding it removes
# any runtime dependency on an external 'openssl' binary being present
# on the user's machine (which is often missing on Windows and was the
# cause of TLS silently falling back to unencrypted). Because the same
# certificate is shared by every copy of this app, it does NOT provide
# per-installation identity/authentication -- it only encrypts the
# transfer against passive network eavesdropping, which is the goal
# here (both ends are machines the operator already controls).
_EMBEDDED_TLS_CERT_B64 = (
    "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSURFekNDQWZ1Z0F3SUJBZ0lVUU13UnlhRkszRnY4RnBrWXUxQkNyUjdv"
    "cjVBd0RRWUpLb1pJaHZjTkFRRUwKQlFBd0dURVhNQlVHQTFVRUF3d09RbWwwUjNWaGNtUXRURzlqWVd3d0hoY05Nall3TnpJ"
    "NU1qSTBOVEUxV2hjTgpNell3TnpJMk1qSTBOVEUxV2pBWk1SY3dGUVlEVlFRRERBNUNhWFJIZFdGeVpDMU1iMk5oYkRDQ0FT"
    "SXdEUVlKCktvWklodmNOQVFFQkJRQURnZ0VQQURDQ0FRb0NnZ0VCQUxidU1GUzhXZ2hBR0FrRDVvQ21UNUJuTWNXSE9xWVoK"
    "K0Jhd0ZwTVJJRmlpTmtGRTM2N091c3BFbjIwc1lEaE12dlJQQjhHR1grUktBaTRBWHRBb2RmbllQVXdHK1N5VQp3Vmk4TFNP"
    "OThHbnY3SVhyNmxOWU1ZSGZTSDBYVjlPenRhUXgzcUQ2SzhlZHF4d1Jmb01WcERMYzJoYXVlSHIrClFjOVRMZE5oQkZoQTRO"
    "ZUtYSzRuNjAwQlNZemF5QjhYTnlrVHk0SGtoUWwrLzB2NkVIeHJQY1B2VC9GVnh3cHEKbXUwT3Y2ZHFzOC91TStFREg4NWRX"
    "RDhIZlZhbkhZbnR4OHoxWXJTbUxGMFRRNFlqNFlOYW1Xd2h2WFEvN1E3RQp6WWVSSDkvc0dTTEhqMS92NTNPTWI0SXE3TjdW"
    "Uk83WG1iaW9DakpXanV2ckNwUjcydFZuRW1zQ0F3RUFBYU5UCk1GRXdIUVlEVlIwT0JCWUVGTnJMbzJxZENzd0RDbDZnVFl5"
    "ekpNS3ZNZDNpTUI4R0ExVWRJd1FZTUJhQUZOckwKbzJxZENzd0RDbDZnVFl5ekpNS3ZNZDNpTUE4R0ExVWRFd0VCL3dRRk1B"
    "TUJBZjh3RFFZSktvWklodmNOQVFFTApCUUFEZ2dFQkFJMGxxYjQ0MHpCaUpGenhrNGFXNk54dzZiUGQydnU0d0ZzNlhxd2hX"
    "VGZpb0hlcWJuWFdleGFYCkJLSWYvR29XZTFQUHkzSVZ0QXdWOXprVmtxWW1TY3VOUmZFNGh2a1dadnkyR3Q3Z3YrS1UrK1E1"
    "N0lTVjBOZkkKd0RzT3l4Q1g4ajZiZlIra2ZZWlM5dU1ITmFJTWJvTWRZNEI0bUdyQVJoTkY4eEtQK1VNcTA2MVh6WHE4K29E"
    "WAplYTFIQUI1bzNPVWduN3ZUWWp1cTkxT3F6KytQbnd2Z3RTMTR6WGJGVnk1N0htUzZpdEpjSEl1eFVqdS9DOENMCm92bHhU"
    "cTNtU1RFRkRFMUVURTdjdlo3dzlSTDNMRHNVNWJtK2FpVE1NSEw2UmpOS3RQUFpHa25VbEx5aXNZYVoKYjFrK2J3VElPSDV2"
    "dHozaVJ1WHVUSFVTOWhuRDQ4ST0KLS0tLS1FTkQgQ0VSVElGSUNBVEUtLS0tLQo="
)
_EMBEDDED_TLS_KEY_B64 = (
    "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JSUV2Z0lCQURBTkJna3Foa2lHOXcwQkFRRUZBQVNDQktnd2dnU2tBZ0VB"
    "QW9JQkFRQzI3akJVdkZvSVFCZ0oKQSthQXBrK1FaekhGaHpxbUdmZ1dzQmFURVNCWW9qWkJSTit1enJyS1JKOXRMR0E0VEw3"
    "MFR3ZkJobC9rU2dJdQpBRjdRS0hYNTJEMU1CdmtzbE1GWXZDMGp2ZkJwNyt5RjYrcFRXREdCMzBoOUYxZlRzN1drTWQ2Zytp"
    "dkhuYXNjCkVYNkRGYVF5M05vV3JuaDYva0hQVXkzVFlRUllRT0RYaWx5dUordE5BVW1NMnNnZkZ6Y3BFOHVCNUlVSmZ2OUwK"
    "K2hCOGF6M0Q3MC94VmNjS2FwcnREcituYXJQUDdqUGhBeC9PWFZnL0IzMVdweDJKN2NmTTlXSzBwaXhkRTBPRwpJK0dEV3Bs"
    "c0liMTBQKzBPeE0ySGtSL2Y3QmtpeDQ5ZjcrZHpqRytDS3V6ZTFVVHUxNW00cUFveVZvN3I2d3FVCmU5clZaeEpyQWdNQkFB"
    "RUNnZ0VBSlRRRzkwekJJTGxzU2ZVVm5XZDFlZ0JLd29ud2x4UmovTFUrT2hXN0Z0dVMKbmk2VU1WaVE2NDhPUDJWTmdsVzFa"
    "amxtY2VqU3VycUVlL2VPVU5aUnZBaksycG4yZGljZ3RWdTc4Rzl5SkJGcgo4SWFjeHV1Q1VnL25qYTFBS3VsN0VSUWxXMmJW"
    "bllqRzRuUDZYMDE0OGZFeGwzaFBQM0JUVVFkeEkvS3dzQVBWCnptSnZPME1Da1JNeWJIQVNQYUh5cFN0ckZmM1JvNmJGSDNn"
    "UXVDRDJXTE9zMmg0emx0OVhkTmJ6bUJBdXhxZkIKdW8yeCtDdmZEeDQyRmVPV0h1a08wS2ZTbVRrbWZ0Y3NUTmE5V3VBaHYz"
    "ZzMvMzJEUFN4cTJ6eHJLM09UR2JYUQpvRnoxQk9DNkpwc0h4NlNhejBORWdyMUxZR2pDY0FMWGxBK1JkejJudFFLQmdRRGJm"
    "YzRZTENhRUhYV0dkRlVRClYwR1crdUFWODhsWnk2UHpBeXk0WW1zd1U1QnIwWjFGRVVmL0dUSG9FT0dKY3gxYWxFZG9OdG9k"
    "UHZ6djFPYmwKbGtQSnJvVXZmajIrRUV5T0dGY2QzK0grREM5a0J2aEV6dVhGZXpLaXVWNnRTM0Q0MDBVdFlyaUcwVjdad1Rz"
    "UQpTUGRucWxwR3JpZFpMQUZibUljRDd1Qm9QUUtCZ1FEVlc1TWRUWHE2SmdpUE1peGZqeUhFTVBkeFJEZ0JjcVhSCitpQjFh"
    "dEhTWWswWVJsaEx5ZmJXM2NaMUs5aHRGTUFyZUlSYVJ3SjdWWWEyVnNNcXFTRERvUzFzRXVpZm42RysKQVN5VERXWFVhdUs4"
    "RkZVUExSQ0piR2lCMGdTVWkzdGgxU0lYTzNabU9JN2Z0dWVyRWk2dDliajhBQWMrUTBPTgpHdUIxMmZQbnh3S0JnUURYUUY0"
    "d2FJUHhScTZ1Q0VJdnYxS3NqU1hiZ1hReVlycExKUTdqV0dtRVFEOCs3WmVOClYzQkM1V09ERWFNTlY5NHVxWUlKMnRrMm0w"
    "SVV0YmNtNnFGYUZaTzV5dFVrSXZuZzFGQURGVCtkRkRnWm9aZ3kKYXJEOVpWOTRJOUNNcEpLTEF5NHhYMEpWdk5pSE5yQUV2"
    "WG9icVAzVm1ROHZyUzg3czY2ZEZkUHZoUUtCZ0ZMZAp4Ri9ITGZtS3VCeFYwbUl6QjF4WjRHRS9xN2owUEc4M2hNL1Y4elNS"
    "Tlh4T0poRVptaU9OODN5aTBPWmMvdDVqCmFwUmRyQnNXOXNGdkpWSTJhaUZSUW9FTlB3aHdTYk93WlEyZ1VJS1dHUVlQcDVI"
    "RFlQN2UraUFoMytHSjR4djIKV2MxSUxRNDZ2Vk1xaVFRcWhiTFBFMC9jK3ZNMTBOREhOWkxRV2lrVkFvR0JBS0wrRmpLaWRs"
    "MklTc0FsNlozVQpQUGk2OW16YVV1dXp2UVkySkVuRUhJbVVCN244VzFsSjlrZFlIK1pRaCtQVTRJNlhnMDdRRHdXSi9qTTRk"
    "S2hJCkFGdUtpaUFRUGIzNnE1MU55Y3JEd1hiL1ZaS1hrcEhWS0M1a3JPdGEwendacVNyZGJXOEc1VDhzenFrV0NTQUEKTFNO"
    "WDI3dm01aHFYVjNTTGJweWxMaXFCCi0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS0K"
)


def generate_self_signed_tls_cert():
    """
    Writes the bundled self-signed certificate + key to temporary files
    and returns (cert_path, key_path). No external 'openssl' call is
    needed at runtime. Returns (None, None) only if the temp files
    somehow can't be written (e.g. disk full).
    """
    try:
        cert_fd, cert_path = tempfile.mkstemp(suffix="_cert.pem")
        key_fd, key_path = tempfile.mkstemp(suffix="_key.pem")
        with os.fdopen(cert_fd, "wb") as f:
            f.write(base64.b64decode(_EMBEDDED_TLS_CERT_B64))
        with os.fdopen(key_fd, "wb") as f:
            f.write(base64.b64decode(_EMBEDDED_TLS_KEY_B64))
        return cert_path, key_path
    except Exception:
        return None, None


def get_hostname():
    try:
        return socket.gethostname()
    except Exception:
        return "Unknown"


def _hidden_subprocess_kwargs():
    """
    Extra kwargs to pass to subprocess calls so that on Windows they
    don't flash a visible console window (which happened for every
    PowerShell call made from this windowed/--windowed-built app, on
    both the source and destination machines). No-op on other OSes.
    """
    if platform.system() == "Windows":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def list_block_devices():
    """
    Lists block devices/disks on the current machine. Automatically
    picks the right command based on OS:
      - Linux/Mac -> lsblk
      - Windows   -> PowerShell Get-PhysicalDisk
    Returns an empty list if nothing works (GUI then suggests manual
    file selection instead).
    """
    system = platform.system()
    if system == "Windows":
        return _list_block_devices_windows()
    return _list_block_devices_linux()


def _list_block_devices_linux():
    try:
        out = subprocess.check_output(
            ["lsblk", "-dbpno", "NAME,SIZE,MODEL,SERIAL"], text=True, timeout=3
        )
        devices = []
        for line in out.strip().splitlines():
            parts = line.split(None, 3)
            if not parts:
                continue
            name = parts[0]
            size_bytes_str = parts[1] if len(parts) > 1 else ""
            model = parts[2] if len(parts) > 2 else ""
            serial = parts[3] if len(parts) > 3 else ""
            try:
                size_bytes = int(size_bytes_str)
            except ValueError:
                size_bytes = None
            devices.append({
                "path": name,
                "size": human_size(size_bytes) if size_bytes else size_bytes_str,
                "size_bytes": size_bytes,
                "model": model,
                "serial": serial,
            })
        return devices
    except Exception:
        return []


def _list_block_devices_windows():
    """
    Uses PowerShell 'Get-PhysicalDisk' to fetch the disk list as JSON.
    The returned 'path' is in \\\\.\\PhysicalDriveN form -- accessing
    the physical disk this way requires Administrator privileges.
    """
    try:
        cmd = [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Get-PhysicalDisk | Select-Object DeviceId,FriendlyName,Size,SerialNumber | ConvertTo-Json -Compress"
        ]
        out = subprocess.check_output(cmd, text=True, timeout=6, **_hidden_subprocess_kwargs())
        data = json.loads(out) if out.strip() else []
        if isinstance(data, dict):
            data = [data]
        devices = []
        for d in data:
            device_id = d.get("DeviceId")
            size_bytes = d.get("Size")
            devices.append({
                "path": f"\\\\.\\PhysicalDrive{device_id}",
                "size": human_size(size_bytes) if size_bytes else "",
                "size_bytes": int(size_bytes) if size_bytes else None,
                "model": d.get("FriendlyName", ""),
                "serial": (d.get("SerialNumber") or "").strip(),
            })
        return devices
    except Exception:
        return []


def list_dir_entries(path):
    """Returns (name, is_dir, size) entries for the given folder."""
    path = os.path.abspath(path)
    items = []
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        try:
            is_dir = os.path.isdir(full)
            size = None if is_dir else os.path.getsize(full)
        except OSError:
            continue
        items.append({"name": name, "is_dir": is_dir, "size": size})
    parent = os.path.dirname(path) if path not in ("/", "") else "/"
    return path, parent, items


def is_raw_device_path(path):
    """True if the given path looks like a raw disk device rather than a regular file/folder."""
    if platform.system() == "Windows":
        return path.lower().startswith(r"\\.\physicaldrive")
    return path.startswith("/dev/")


def get_disk_info_for_device(device_path):
    """
    Looks up model/serial/size for a known raw device path by matching
    it against the system's disk list. Returns
    {"model":..., "serial":..., "size_bytes":...} (size_bytes is None
    if it couldn't be determined).
    """
    for d in list_block_devices():
        if d.get("path", "").lower() == device_path.lower():
            return {
                "model": d.get("model") or "Unknown",
                "serial": d.get("serial") or "Unknown",
                "size_bytes": d.get("size_bytes"),
            }
    return {"model": "Unknown", "serial": "Unknown", "size_bytes": None}


def get_write_protect_status(device_path):
    """
    Best-effort check of whether the OS reports a block device as
    read-only at the moment (e.g. because a hardware/software
    write-blocker set it that way, or 'blockdev --setro' was used).
    Returns True / False / None (unknown / not applicable).
    """
    system = platform.system()
    try:
        if system == "Linux" and device_path.startswith("/dev/"):
            base = os.path.basename(device_path)
            ro_path = f"/sys/block/{base}/ro"
            if os.path.exists(ro_path):
                with open(ro_path) as f:
                    return f.read().strip() == "1"
            return None
        if system == "Windows" and device_path.lower().startswith(r"\\.\physicaldrive"):
            device_id = device_path.lower().replace(r"\\.\physicaldrive", "")
            cmd = [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                f"(Get-Disk -Number {device_id}).IsReadOnly"
            ]
            out = subprocess.check_output(cmd, text=True, timeout=5, **_hidden_subprocess_kwargs()).strip()
            if out:
                return out.lower() == "true"
            return None
    except Exception:
        return None
    return None


def find_disk_for_path(path):
    """
    Best-effort: given a regular file path, finds which physical disk
    device backs it (used to report the DESTINATION disk's model/serial
    in the chain-of-custody log). Returns a device path string or None.
    """
    system = platform.system()
    try:
        if system == "Linux":
            d = os.path.dirname(os.path.abspath(path)) or "/"
            while d and not os.path.exists(d):
                parent = os.path.dirname(d)
                if parent == d:
                    break
                d = parent
            out = subprocess.check_output(["df", "--output=source", d], text=True, timeout=3)
            lines = out.strip().splitlines()
            if len(lines) < 2:
                return None
            partition = lines[1].strip()
            m = re.match(r"(/dev/nvme\d+n\d+)p?\d*$", partition)
            if m:
                return m.group(1)
            m2 = re.match(r"(/dev/[a-zA-Z]+)\d*$", partition)
            if m2:
                return m2.group(1)
            return partition
        if system == "Windows":
            drive = os.path.splitdrive(os.path.abspath(path))[0]  # e.g. "C:"
            letter = drive.rstrip(":")
            cmd = [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                f"(Get-Partition -DriveLetter '{letter}').DiskNumber"
            ]
            out = subprocess.check_output(cmd, text=True, timeout=5, **_hidden_subprocess_kwargs()).strip()
            if out:
                return f"\\\\.\\PhysicalDrive{out}"
    except Exception:
        return None
    return None


# ----------------------------------------------------------------------
# Advanced forensic image containers (CustomE01 / CustomAFF4)
# ----------------------------------------------------------------------
# HONESTY NOTE: The real EWF/E01 and AFF4 specifications are complex
# binary formats. Full interoperability with EnCase/FTK (E01) requires
# the proprietary EWF spec + the libewf library; full AFF4 requires an
# RDF metadata graph per the AFF4 standard. Those require external
# system libraries (libewf, pyaff4) that aren't available offline.
# The containers below are custom, simplified implementations that
# capture the SAME CORE IDEAS these formats are known for -- embedded
# case metadata, compressed data, and an embedded verification hash --
# using only Python's standard library, so they always work without
# extra installs. The AFF4 one in particular is a genuine ZIP/DEFLATE
# container with an "information.turtle" metadata member, matching the
# real format's actual container approach (just without a full RDF
# graph). Neither is byte-compatible with the official tools' readers.
def build_custom_e01(source_path, output_path, header_info, chunk_size=CHUNK_SIZE, progress_cb=None):
    """Writes a simplified 'E01-style' container: magic + JSON header +
    zlib-compressed chunks + end marker + embedded SHA-256 of the
    original data. Returns the SHA-256 of the original (uncompressed) data."""
    hasher = hashlib.sha256()
    header = {
        "format": "CustomE01-v1 (simplified; NOT byte-compatible with EnCase/FTK's official EWF/E01 reader)",
        **header_info,
    }
    with open(source_path, "rb") as fin, open(output_path, "wb") as fout:
        fout.write(b"CE01")
        header_bytes = json.dumps(header, ensure_ascii=False).encode("utf-8")
        fout.write(struct.pack("<I", len(header_bytes)))
        fout.write(header_bytes)
        sent = 0
        while True:
            chunk = fin.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
            compressed = zlib.compress(chunk, 6)
            fout.write(struct.pack("<I", len(compressed)))
            fout.write(compressed)
            sent += len(chunk)
            if progress_cb:
                progress_cb(sent)
        fout.write(struct.pack("<I", 0))  # end marker
        original_hash = hasher.hexdigest()
        hash_bytes = original_hash.encode("ascii")
        fout.write(struct.pack("<I", len(hash_bytes)))
        fout.write(hash_bytes)
    return original_hash


def read_custom_e01_header(path):
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic != b"CE01":
            raise ValueError("Not a CustomE01 container (bad magic bytes).")
        (hlen,) = struct.unpack("<I", f.read(4))
        return json.loads(f.read(hlen).decode("utf-8"))


def extract_custom_e01(path, out_path):
    """Decompresses a CustomE01 container back to raw data. Returns
    (recomputed_hash, embedded_hash_from_container)."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f, open(out_path, "wb") as out:
        magic = f.read(4)
        if magic != b"CE01":
            raise ValueError("Not a CustomE01 container (bad magic bytes).")
        (hlen,) = struct.unpack("<I", f.read(4))
        f.read(hlen)
        while True:
            (clen,) = struct.unpack("<I", f.read(4))
            if clen == 0:
                break
            data = zlib.decompress(f.read(clen))
            hasher.update(data)
            out.write(data)
        (hashlen,) = struct.unpack("<I", f.read(4))
        embedded_hash = f.read(hashlen).decode("ascii")
    return hasher.hexdigest(), embedded_hash


def build_custom_aff4(source_path, output_path, header_info, chunk_size=CHUNK_SIZE, progress_cb=None):
    """
    Writes a simplified 'AFF4-style' container: a real ZIP (DEFLATE)
    file holding an 'information.turtle' metadata member (matching
    AFF4's real naming convention), a 'data.raw' member with the
    compressed image data, and a 'hash.sha256' member. Returns the
    SHA-256 of the original (uncompressed) data. Because it's a
    genuine ZIP file, it can also be inspected/extracted with any
    standard zip tool.
    """
    hasher = hashlib.sha256()
    lines = [
        "@format CustomAFF4-v1 (simplified container: real ZIP/DEFLATE + "
        "information.turtle metadata; NOT a full AFF4 RDF graph)"
    ]
    lines += [f"{k}: {v}" for k, v in header_info.items()]
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("information.turtle", "\n".join(lines))
        sent = 0
        with zf.open("data.raw", "w") as zdata, open(source_path, "rb") as fin:
            while True:
                chunk = fin.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
                zdata.write(chunk)
                sent += len(chunk)
                if progress_cb:
                    progress_cb(sent)
        original_hash = hasher.hexdigest()
        zf.writestr("hash.sha256", original_hash)
    return original_hash


def extract_custom_aff4(path, out_path):
    """Extracts a CustomAFF4 container back to raw data. Returns
    (recomputed_hash, embedded_hash_from_container)."""
    hasher = hashlib.sha256()
    with zipfile.ZipFile(path, "r") as zf:
        embedded_hash = zf.read("hash.sha256").decode("ascii").strip()
        with zf.open("data.raw", "r") as zdata, open(out_path, "wb") as out:
            while True:
                chunk = zdata.read(CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
                out.write(chunk)
    return hasher.hexdigest(), embedded_hash


# ----------------------------------------------------------------------
# Status banner
# ----------------------------------------------------------------------
class StatusBanner(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.label = tk.Label(
            self, text="Waiting...", anchor="w", justify="left",
            font=("Segoe UI", 11, "bold"), bg=COLOR_PANEL, fg=COLOR_MUTED,
            padx=12, pady=10,
        )
        self.label.pack(fill="x")

    def set(self, text, kind="info"):
        colors = {
            "ok": (COLOR_OK, "#0b2b1a"),
            "err": (COLOR_ERR, "#3a1414"),
            "warn": (COLOR_WARN, "#3a2c10"),
            "info": (COLOR_MUTED, COLOR_PANEL),
        }
        fg, bg = colors.get(kind, colors["info"])
        self.label.configure(text=text, fg=fg, bg=bg)


# ----------------------------------------------------------------------
# SERVER TAB
# ----------------------------------------------------------------------
class ServerTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=18, style="Panel.TFrame")
        self.server_thread = None
        self.srv_socket = None
        self.conn_socket = None
        self.stop_event = threading.Event()
        self._build_ui()

    def _build_ui(self):
        sub = ttk.Notebook(self, style="Sub.TNotebook")
        sub.pack(fill="both", expand=True)

        setup_tab = ttk.Frame(sub, padding=16, style="Panel.TFrame")
        log_tab = ttk.Frame(sub, padding=16, style="Panel.TFrame")
        sub.add(setup_tab, text="⚙️  Setup")
        sub.add(log_tab, text="📋  Log")

        # ---------------- Setup tab ----------------
        intro = tk.Label(
            setup_tab,
            text="Run this on the machine you want to image FROM. No setup needed — just start it and wait.",
            justify="left", anchor="w", bg=COLOR_BG, fg=COLOR_MUTED,
            font=("Segoe UI", 9), wraplength=560,
        )
        intro.pack(fill="x", pady=(0, 14))

        conn_label = tk.Label(setup_tab, text="🔌 Connection settings", bg=COLOR_BG, fg=COLOR_ACCENT2,
                               font=("Segoe UI", 11, "bold"), anchor="w")
        conn_label.pack(fill="x")

        conn_frame = ttk.Frame(setup_tab)
        conn_frame.pack(fill="x", pady=(6, 14))
        tk.Label(conn_frame, text="Host:", bg=COLOR_BG, fg=COLOR_TEXT).grid(row=0, column=0, sticky="w")
        self.host_var = tk.StringVar(value="0.0.0.0")
        ttk.Entry(conn_frame, textvariable=self.host_var, width=16).grid(row=0, column=1, padx=(4, 20))
        tk.Label(conn_frame, text="Port:", bg=COLOR_BG, fg=COLOR_TEXT).grid(row=0, column=2, sticky="w")
        self.port_var = tk.StringVar(value="9000")
        ttk.Entry(conn_frame, textvariable=self.port_var, width=10).grid(row=0, column=3, padx=(4, 0))
        tk.Label(conn_frame, text="  (0.0.0.0 = accept from any address)",
                 bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).grid(row=0, column=4, sticky="w")

        sec_frame = ttk.Frame(setup_tab)
        sec_frame.pack(fill="x", pady=(0, 10))
        self.tls_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sec_frame, text="🔒 Encrypt transfer (TLS)", variable=self.tls_var).pack(side="left")
        tk.Label(sec_frame, text="  must also be enabled on the Client — both sides must match",
                 bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(side="left")

        btn_row = ttk.Frame(setup_tab)
        btn_row.pack(fill="x", pady=(0, 14))
        self.start_btn = ttk.Button(btn_row, text="▶  Start Server (Wait for Connection)",
                                     command=self._start_server, style="Accent.TButton")
        self.start_btn.pack(side="left", fill="x", expand=True, ipady=6)
        self.stop_btn = ttk.Button(btn_row, text="⏹  Stop Server", command=self._stop_server,
                                    state="disabled", style="Danger.TButton")
        self.stop_btn.pack(side="left", padx=(8, 0), ipady=6)

        self.banner = StatusBanner(setup_tab)
        self.banner.pack(fill="x", pady=(0, 4))
        self.banner.set("⏳ Waiting — click 'Start Server' to begin.", "info")

        ssh_note = tk.Label(
            setup_tab,
            text="💡 Alternative: instead of TLS, you can tunnel this connection over SSH "
                 "(e.g. 'ssh -L 9000:localhost:9000 user@this-machine' run on the Client side), "
                 "which encrypts everything with zero code changes.",
            justify="left", anchor="w", bg=COLOR_BG, fg=COLOR_MUTED,
            font=("Segoe UI", 8), wraplength=560,
        )
        ssh_note.pack(fill="x", pady=(10, 0))

        # ---------------- Log tab ----------------
        log_header = ttk.Frame(log_tab)
        log_header.pack(fill="x")
        tk.Label(log_header, text="📋 Activity Log", bg=COLOR_BG, fg=COLOR_ACCENT2,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(log_header, text="Clear", command=self._clear_log, style="Cyan.TButton").pack(side="right")

        self.log_box = tk.Text(log_tab, height=20, state="disabled", bg=COLOR_LOG_BG, fg="#7ee787",
                                font=("Consolas", 9), relief="flat", padx=8, pady=6)
        self.log_box.pack(fill="both", expand=True, pady=(8, 0))

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _log(self, msg):
        def append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{ts()}] {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, append)

    def _start_server(self):
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Error", "Port must be numeric.")
            return
        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.banner.set("⏳ Starting...", "warn")
        self.server_thread = threading.Thread(
            target=self._run_server, args=(self.host_var.get(), port), daemon=True
        )
        self.server_thread.start()

    def _stop_server(self):
        """Signal the server thread to stop. It polls this flag (socket
        timeouts let it notice within ~1 second) instead of relying on
        closing the socket from this thread, which does not reliably
        unblock a thread stuck in accept()/recv() on all platforms."""
        self._log("Stop requested by user...")
        self.stop_event.set()
        self.stop_btn.configure(state="disabled")

    def _run_server(self, host, port):
        self.srv_socket = None
        self.conn_socket = None
        srv = None
        conn = None
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((host, port))
            srv.listen(1)
            srv.settimeout(1.0)
            self.srv_socket = srv
            self.after(0, lambda: self.banner.set(f"🔌 Waiting for a connection on {host}:{port}...", "warn"))
            self._log(f"Listening on: {host}:{port}")

            while not self.stop_event.is_set():
                try:
                    conn, addr = srv.accept()
                    break
                except socket.timeout:
                    continue

            if conn is None:
                self._log("Server stopped (no connection was made).")
                self.after(0, lambda: self.banner.set("⏹ Server stopped.", "info"))
                return

            self.conn_socket = conn
            self._log(f"Connection accepted: {addr[0]}:{addr[1]}")

            tls_cert_path = tls_key_path = None
            encrypted = False
            if self.tls_var.get():
                self._log("Setting up TLS encryption (generating a temporary self-signed certificate)...")
                tls_cert_path, tls_key_path = generate_self_signed_tls_cert()
                if tls_cert_path:
                    try:
                        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                        ctx.load_cert_chain(certfile=tls_cert_path, keyfile=tls_key_path)
                        conn = ctx.wrap_socket(conn, server_side=True)
                        self.conn_socket = conn
                        encrypted = True
                        self._log(f"🔒 TLS handshake complete — cipher: {conn.cipher()}")
                    except Exception as e:
                        self._log(f"⚠️ TLS setup failed ({e}); continuing UNENCRYPTED. "
                                   f"Make sure the Client also has TLS enabled.")
                else:
                    self._log("⚠️ Could not generate a TLS certificate (is 'openssl' installed?); "
                               "continuing UNENCRYPTED.")

            conn.settimeout(1.0)
            self.after(0, lambda: self.banner.set(
                f"🗂️  Client ({addr[0]}) is browsing for a source...{'  🔒' if encrypted else ''}", "warn"))

            send_json(conn, {"type": "ready", "encrypted": encrypted})

            while not self.stop_event.is_set():
                try:
                    req = recv_json(conn, stop_check=self.stop_event.is_set)
                except StopRequested:
                    self._log("Server stopped by user.")
                    self.after(0, lambda: self.banner.set("⏹ Server stopped.", "info"))
                    return
                if req is None:
                    self._log("Connection closed by the client.")
                    break
                cmd = req.get("cmd")

                if cmd == "list_disks":
                    items = list_block_devices()
                    send_json(conn, {"type": "disks", "items": items})
                    self._log("Sent disk list to client.")

                elif cmd == "list_dir":
                    path = req.get("path") or os.path.expanduser("~")
                    try:
                        abs_path, parent, items = list_dir_entries(path)
                        send_json(conn, {"type": "dir", "path": abs_path, "parent": parent, "items": items})
                        self._log(f"Client browsed folder: {abs_path}")
                    except OSError as e:
                        send_json(conn, {"type": "error", "message": str(e)})
                        self._log(f"Listing error ({path}): {e}")

                elif cmd == "select":
                    chosen = req.get("path")
                    image_format = req.get("format", "raw")
                    case_info = {
                        "case_number": req.get("case_number") or "(not specified)",
                        "examiner_name": req.get("examiner_name") or "(not specified)",
                    }
                    self._log(f"Client selected source: {chosen} (format: {image_format})")
                    self.after(0, lambda c=chosen: self.banner.set(f"📤 Sending selected source: {c}", "warn"))
                    conn.settimeout(None)  # allow sendall() to block normally during the actual transfer
                    try:
                        self._send_image(conn, chosen, image_format=image_format, case_info=case_info,
                                          encrypted=encrypted, peer_addr=addr)
                        self.after(0, lambda: self.banner.set("✅ Transfer complete.", "ok"))
                    except Exception as e:
                        self._log(f"ERROR: {e}")
                        try:
                            send_json(conn, {"type": "error", "message": str(e)})
                        except OSError:
                            pass
                        self.after(0, lambda err=e: self.banner.set(f"❌ Error: {err}", "err"))
                    break

                else:
                    send_json(conn, {"type": "error", "message": "unknown command"})

        except Exception as e:
            self._log(f"ERROR: {e}")
            self.after(0, lambda: self.banner.set(f"❌ Error occurred: {e}", "err"))
        finally:
            for sock in (conn, srv):
                try:
                    if sock:
                        sock.close()
                except OSError:
                    pass
            try:
                if 'tls_cert_path' in locals() and tls_cert_path and os.path.exists(tls_cert_path):
                    os.remove(tls_cert_path)
                if 'tls_key_path' in locals() and tls_key_path and os.path.exists(tls_key_path):
                    os.remove(tls_key_path)
            except OSError:
                pass
            self.srv_socket = None
            self.conn_socket = None
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            self.after(0, lambda: self.stop_btn.configure(state="disabled"))

    def _send_image(self, conn, source_path, image_format="raw", case_info=None,
                     encrypted=False, peer_addr=None):
        case_info = case_info or {"case_number": "(not specified)", "examiner_name": "(not specified)"}
        is_folder = os.path.isdir(source_path)
        is_disk = is_raw_device_path(source_path)
        temp_tar_path = None
        temp_container_path = None
        try:
            # --- Gather source disk info (model/serial/write-protect/size) if applicable ---
            source_model = "N/A (file, not a disk)"
            source_serial = "N/A (file, not a disk)"
            source_write_protected = None
            disk_size_bytes = None
            if is_disk:
                info = get_disk_info_for_device(source_path)
                source_model = info["model"]
                source_serial = info["serial"]
                disk_size_bytes = info.get("size_bytes")
                source_write_protected = get_write_protect_status(source_path)
                if source_write_protected is True:
                    self._log("✅ Source disk reports READ-ONLY at the OS level (write-blocker compatible).")
                elif source_write_protected is False:
                    self._log("⚠️ Source disk does NOT report read-only at the OS level. "
                               "This tool only ever opens sources in read-only mode and never writes to them; "
                               "if a hardware write-blocker is in use, protection is enforced at the hardware "
                               "layer and may not be visible to the OS.")

            if is_folder:
                self._log(f"Folder selected, building tar archive: {source_path}")
                self.after(0, lambda: self.banner.set(f"📦 Packaging folder: {source_path}", "warn"))
                fd, temp_tar_path = tempfile.mkstemp(suffix=".tar")
                os.close(fd)
                folder_name = os.path.basename(os.path.normpath(source_path)) or "folder"
                with tarfile.open(temp_tar_path, "w") as tar:
                    tar.add(source_path, arcname=folder_name)
                raw_source = temp_tar_path
                self._log(f"Tar archive ready: {human_size(os.path.getsize(temp_tar_path))}")
            else:
                raw_source = source_path

            original_hash = None
            archive_format = "tar" if is_folder else None

            if image_format in ("gzip", "e01", "aff4"):
                # Hash the ORIGINAL (uncompressed / pre-container) data first.
                self._log("Computing hash of original (pre-packaging) data...")
                oh = hashlib.sha256()
                with open(raw_source, "rb") as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        oh.update(chunk)
                original_hash = oh.hexdigest()
                self._log(f"Original data SHA-256: {original_hash}")

                header_info = {
                    "case_number": case_info["case_number"],
                    "examiner_name": case_info["examiner_name"],
                    "source_path": source_path,
                    "source_model": source_model,
                    "source_serial": source_serial,
                    "acquisition_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "original_sha256": original_hash,
                }

                if image_format == "gzip":
                    self._log("Compressing with gzip...")
                    self.after(0, lambda: self.banner.set("📦 Compressing (gzip)...", "warn"))
                    fd, temp_container_path = tempfile.mkstemp(suffix=".gz")
                    os.close(fd)
                    with open(raw_source, "rb") as fin, gzip.open(temp_container_path, "wb") as fout:
                        while True:
                            chunk = fin.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            fout.write(chunk)
                    archive_format = "tar.gz" if is_folder else "gz"

                elif image_format == "e01":
                    self._log("Building E01-style container (simplified, custom)...")
                    self.after(0, lambda: self.banner.set("📦 Building E01-style container...", "warn"))
                    fd, temp_container_path = tempfile.mkstemp(suffix=".E01")
                    os.close(fd)
                    build_custom_e01(raw_source, temp_container_path, header_info)
                    archive_format = "e01"

                elif image_format == "aff4":
                    self._log("Building AFF4-style container (ZIP-based, custom)...")
                    self.after(0, lambda: self.banner.set("📦 Building AFF4-style container...", "warn"))
                    fd, temp_container_path = tempfile.mkstemp(suffix=".aff4")
                    os.close(fd)
                    build_custom_aff4(raw_source, temp_container_path, header_info)
                    archive_format = "aff4"

                actual_source = temp_container_path
                self._log(f"Container ready: {human_size(os.path.getsize(temp_container_path))} "
                          f"(original: {human_size(os.path.getsize(raw_source))})")
            else:
                actual_source = raw_source

            if is_disk and image_format == "raw" and disk_size_bytes:
                # Use the size the OS already reported when the disk was listed,
                # instead of opening+seeking the raw device to find its end --
                # seeking to the end of a raw physical drive fails on Windows
                # (OSError: [Errno 22] Invalid argument) even though sequential
                # reads from the start work fine.
                total_size = disk_size_bytes
                self._log(f"Using OS-reported disk size: {human_size(total_size)} ({total_size} bytes).")
            else:
                try:
                    total_size = os.path.getsize(actual_source)
                except OSError:
                    with open(actual_source, "rb") as f:
                        f.seek(0, 2)
                        total_size = f.tell()

            total_chunks = math.ceil(total_size / CHUNK_SIZE) if total_size else 0

            self._log(
                f"Source: {source_path}{' (folder -> tar archive)' if is_folder else ''} "
                f"| Format: {image_format.upper()} "
                f"| Size: {human_size(total_size)} ({total_size} bytes) | {total_chunks} chunk(s)"
            )

            source_ip = None
            try:
                source_ip = conn.getsockname()[0]
            except OSError:
                pass
            dest_ip = peer_addr[0] if peer_addr else None

            # NOTE: meta is sent immediately, before any hashing/reading, so the
            # client's progress bar starts moving right away. Per-chunk hashes
            # are computed and sent inline with each chunk (single pass) rather
            # than in a separate pre-pass over the whole source -- for a large
            # disk, a separate pre-pass could take many minutes with nothing
            # visible on screen, which looked like the app had frozen.
            meta = {
                "type": "meta", "source": source_path, "size": total_size,
                "hash_algo": "sha256", "chunk_size": CHUNK_SIZE, "total_chunks": total_chunks,
                "is_folder_archive": is_folder,
                "archive_format": archive_format,
                "image_format": image_format,
                "compressed": image_format != "raw",
                "original_sha256": original_hash,
                "is_disk_source": is_disk,
                "source_model": source_model,
                "source_serial": source_serial,
                "source_write_protected": source_write_protected,
                "case_number": case_info["case_number"],
                "examiner_name": case_info["examiner_name"],
                "encrypted": encrypted,
                "source_hostname": get_hostname(),
                "source_ip": source_ip,
                "destination_ip": dest_ip,
            }
            send_json(conn, meta)

            overall_hasher = hashlib.sha256()
            sent = 0
            start_time = time.time()
            last_log = 0
            with open(actual_source, "rb") as f:
                index = 0
                while sent < total_size:
                    to_read = min(CHUNK_SIZE, total_size - sent)
                    chunk = f.read(to_read)
                    if not chunk:
                        break
                    chunk_hash = hashlib.sha256(chunk).hexdigest()
                    overall_hasher.update(chunk)
                    send_json(conn, {"type": "chunk_header", "index": index, "hash": chunk_hash, "length": len(chunk)})
                    conn.sendall(chunk)
                    sent += len(chunk)
                    index += 1
                    now = time.time()
                    if now - last_log > 0.5 or sent == total_size:
                        last_log = now
                        pct = (sent / total_size * 100) if total_size else 100
                        speed = human_speed(sent, now - start_time)
                        self._log(f"Sent: {human_size(sent)}/{human_size(total_size)}  ({pct:.1f}%)  speed: {speed}")
            source_hash = overall_hasher.hexdigest()

            # --- Handle any chunk re-send requests from the client (automatic
            # self-healing if it detected a hash mismatch on arrival) ---
            retry_rounds = 0
            while True:
                req = recv_json(conn)
                if req is None:
                    break
                if req.get("cmd") == "resend_chunks":
                    indices = req.get("indices", [])
                    retry_rounds += 1
                    self._log(f"⚠️ Client reported {len(indices)} corrupted chunk(s); resending (round {retry_rounds})...")
                    with open(actual_source, "rb") as f:
                        for idx in indices:
                            f.seek(idx * CHUNK_SIZE)
                            data = f.read(CHUNK_SIZE)
                            send_json(conn, {"type": "chunk_header", "index": idx,
                                              "hash": hashlib.sha256(data).hexdigest(), "length": len(data)})
                            conn.sendall(data)
                    self._log(f"Resent chunks: {indices}")
                elif req.get("cmd") == "done":
                    break

            elapsed = time.time() - start_time
            send_json(conn, {"type": "footer", "final_sha256": source_hash, "elapsed_sec": round(elapsed, 2),
                              "original_sha256": original_hash, "retry_rounds": retry_rounds,
                              "total_chunks": total_chunks})

            self._log(f"Transfer complete. Duration: {elapsed:.1f}s")
            self._log(f"SHA-256 (of transferred bytes): {source_hash}")
        finally:
            for p in (temp_tar_path, temp_container_path):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                        self._log("Temporary file (server side) cleaned up.")
                    except OSError:
                        pass


# ----------------------------------------------------------------------
# REMOTE FILE BROWSER (Toplevel window)
# ----------------------------------------------------------------------
class RemoteBrowser(tk.Toplevel):
    def __init__(self, master, client_tab):
        super().__init__(master)
        self.client_tab = client_tab
        self.title("Remote File / Disk Browser")
        self.geometry("560x480")
        self.configure(bg=COLOR_BG)
        self.mode = "dir"  # "dir" or "disks"
        self.current_path = None
        self.parent_path = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()

    def _build_ui(self):
        top = tk.Frame(self, bg=COLOR_BG)
        top.pack(fill="x", padx=10, pady=10)
        self.path_var = tk.StringVar(value="Loading...")
        tk.Label(top, textvariable=self.path_var, bg=COLOR_BG, fg=COLOR_TEXT,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(side="left", fill="x", expand=True)

        btns = tk.Frame(self, bg=COLOR_BG)
        btns.pack(fill="x", padx=10)
        ttk.Button(btns, text="⬆ Parent Folder", command=self._go_up).pack(side="left")
        ttk.Button(btns, text="💿 Show Disks", command=self._show_disks).pack(side="left", padx=6)
        ttk.Button(btns, text="🔄 Refresh", command=self._reload).pack(side="left")

        self.listbox = tk.Listbox(self, bg=COLOR_LOG_BG, fg=COLOR_TEXT, font=("Consolas", 10),
                                   selectbackground=COLOR_ACCENT, activestyle="none")
        self.listbox.pack(fill="both", expand=True, padx=10, pady=10)
        self.listbox.bind("<Double-Button-1>", self._on_double_click)

        bottom = tk.Frame(self, bg=COLOR_BG)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bottom, text="✅ Use Selected Item as Source",
                   command=self._confirm_selection, style="Accent.TButton").pack(fill="x", ipady=4)

    def _on_close(self):
        self.client_tab.cancel()

    def show_dir(self, resp):
        self.mode = "dir"
        self.current_path = resp["path"]
        self.parent_path = resp.get("parent")
        self.path_var.set(f"📁 {self.current_path}")
        self.listbox.delete(0, "end")
        self._entries = []
        if self.parent_path and self.parent_path != self.current_path:
            self.listbox.insert("end", "⬆  .. (parent folder)")
            self._entries.append({"name": "..", "is_dir": True, "size": None})
        for item in resp["items"]:
            icon = "📁" if item["is_dir"] else "📄"
            size_txt = "" if item["is_dir"] else f"  ({human_size(item['size'])})"
            self.listbox.insert("end", f"{icon}  {item['name']}{size_txt}")
            self._entries.append(item)

    def show_disks(self, resp):
        self.mode = "disks"
        self.path_var.set("💿 Disks on the remote system")
        self.listbox.delete(0, "end")
        self._entries = []
        items = resp.get("items", [])
        if not items:
            self.listbox.insert("end", "(No disks found — lsblk/PowerShell not available)")
        for item in items:
            label = f"💽  {item['path']}   {item['size']}   {item.get('model','')}"
            self.listbox.insert("end", label)
            self._entries.append({"name": item["path"], "is_dir": False, "is_disk": True})

    def _on_double_click(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        entry = self._entries[sel[0]]
        if self.mode == "dir" and entry["is_dir"]:
            if entry["name"] == "..":
                self.client_tab.request_dir(self.parent_path)
            else:
                new_path = os.path.join(self.current_path, entry["name"])
                self.client_tab.request_dir(new_path)
        else:
            self._confirm_selection()

    def _go_up(self):
        if self.mode == "dir" and self.parent_path:
            self.client_tab.request_dir(self.parent_path)

    def _reload(self):
        if self.mode == "dir":
            self.client_tab.request_dir(self.current_path)
        else:
            self.client_tab.request_disks()

    def _show_disks(self):
        self.client_tab.request_disks()

    def _confirm_selection(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Info", "Please select a file, disk, or folder.")
            return
        entry = self._entries[sel[0]]
        if entry["name"] == "..":
            return
        if self.mode == "disks":
            full_path = entry["name"]
        else:
            if entry["is_dir"]:
                full_path = os.path.join(self.current_path, entry["name"])
                choice = messagebox.askyesnocancel(
                    "Folder selected",
                    f"'{entry['name']}' is a folder.\n\n"
                    "• YES → Image the ENTIRE folder (all subfiles/subfolders, "
                    "packaged as a tar archive)\n"
                    "• NO → Go inside, pick a single file\n"
                    "• CANCEL → Do nothing"
                )
                if choice is None:
                    return
                if choice is False:
                    self.client_tab.request_dir(full_path)
                    return
                # choice == True -> image the whole folder as a tar
            else:
                full_path = os.path.join(self.current_path, entry["name"])

        self.destroy()
        self.client_tab.select_remote_source(full_path)


# ----------------------------------------------------------------------
# CLIENT TAB
# ----------------------------------------------------------------------
class ClientTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=18, style="Panel.TFrame")
        self.sock = None
        self.browser = None
        self.cancelled = False
        self.error_list = []
        self._build_ui()

    def _build_ui(self):
        sub = ttk.Notebook(self, style="Sub.TNotebook")
        sub.pack(fill="both", expand=True)

        connect_tab = ttk.Frame(sub, padding=16, style="Panel.TFrame")
        case_tab = ttk.Frame(sub, padding=16, style="Panel.TFrame")
        progress_tab = ttk.Frame(sub, padding=16, style="Panel.TFrame")
        sub.add(connect_tab, text="🔌  Connect")
        sub.add(case_tab, text="🗂️  Case & Format")
        sub.add(progress_tab, text="📊  Progress & Log")
        self._sub_notebook = sub
        self._progress_tab_index = 2

        # ==================== TAB 1: Connect ====================
        intro = tk.Label(
            connect_tab,
            text="Run this on the machine where you want to SAVE the image. Connect, then pick the file/disk to copy.",
            justify="left", anchor="w", bg=COLOR_BG, fg=COLOR_MUTED,
            font=("Segoe UI", 9), wraplength=560,
        )
        intro.pack(fill="x", pady=(0, 14))

        acq_label = tk.Label(connect_tab, text="🎯 What do you want to acquire?", bg=COLOR_BG,
                              fg=COLOR_ACCENT2, font=("Segoe UI", 11, "bold"), anchor="w")
        acq_label.pack(fill="x")
        acq_frame = ttk.Frame(connect_tab)
        acq_frame.pack(fill="x", pady=(8, 4))
        self.acquisition_type_var = tk.StringVar(value="file")
        self._acq_buttons = {}
        for key, label, emoji in [("disk", "Disk Image", "💽"), ("file", "File", "📄"),
                                    ("folder", "Folder", "📁")]:
            b = tk.Button(acq_frame, text=f"{emoji}  {label}", command=lambda k=key: self._select_acquisition_type(k),
                          bg=COLOR_PANEL, fg=COLOR_TEXT, activebackground=COLOR_ACCENT,
                          activeforeground="white", relief="flat", bd=0, font=("Segoe UI", 9, "bold"),
                          cursor="hand2")
            b.pack(side="left", padx=(0, 8), ipady=8, fill="x", expand=True)
            self._acq_buttons[key] = b
        self._select_acquisition_type("file")
        tk.Label(connect_tab, text="Select, then connect below — the right browser (disks/files) opens automatically.",
                  bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(fill="x", pady=(0, 14))

        conn_label = tk.Label(connect_tab, text="🌐 Server address", bg=COLOR_BG, fg=COLOR_ACCENT2,
                               font=("Segoe UI", 11, "bold"), anchor="w")
        conn_label.pack(fill="x")

        conn_frame = ttk.Frame(connect_tab)
        conn_frame.pack(fill="x", pady=(6, 8))
        tk.Label(conn_frame, text="Server IP:", bg=COLOR_BG, fg=COLOR_TEXT).grid(row=0, column=0, sticky="w")
        self.host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(conn_frame, textvariable=self.host_var, width=18).grid(row=0, column=1, padx=(4, 20))
        tk.Label(conn_frame, text="Port:", bg=COLOR_BG, fg=COLOR_TEXT).grid(row=0, column=2, sticky="w")
        self.port_var = tk.StringVar(value="9000")
        ttk.Entry(conn_frame, textvariable=self.port_var, width=10).grid(row=0, column=3, padx=(4, 0))

        sec_frame = ttk.Frame(connect_tab)
        sec_frame.pack(fill="x", pady=(0, 12))
        self.tls_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sec_frame, text="🔒 Encrypt transfer (TLS)", variable=self.tls_var).pack(side="left")
        tk.Label(sec_frame, text="  must match the Server's setting", bg=COLOR_BG, fg=COLOR_MUTED,
                 font=("Segoe UI", 8)).pack(side="left")

        btn_row = ttk.Frame(connect_tab)
        btn_row.pack(fill="x", pady=(0, 14))
        self.connect_btn = ttk.Button(btn_row, text="🔎  Connect & Select Source",
                                       command=self._start_connect, style="Accent.TButton")
        self.connect_btn.pack(side="left", fill="x", expand=True, ipady=6)
        self.cancel_btn = ttk.Button(btn_row, text="❌  Cancel / Disconnect", command=self.cancel,
                                      state="disabled", style="Danger.TButton")
        self.cancel_btn.pack(side="left", padx=(8, 0), ipady=6)

        self.banner = StatusBanner(connect_tab)
        self.banner.pack(fill="x", pady=(0, 4))
        self.banner.set("⏳ Waiting — enter server details and click 'Connect & Select Source'.", "info")

        tip = tk.Label(connect_tab, text="💡 Tip: fill in Case & Format before connecting, so it's ready "
                                          "as soon as you pick a source.",
                        bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8), wraplength=560, justify="left")
        tip.pack(fill="x", pady=(14, 0))

        # ==================== TAB 2: Case & Format ====================
        case_label = tk.Label(case_tab, text="🗂️ Case information (included in the audit report)",
                               bg=COLOR_BG, fg=COLOR_ACCENT2, font=("Segoe UI", 11, "bold"), anchor="w")
        case_label.pack(fill="x")
        case_frame = ttk.Frame(case_tab)
        case_frame.pack(fill="x", pady=(6, 16))
        tk.Label(case_frame, text="Case Number:", bg=COLOR_BG, fg=COLOR_TEXT).grid(row=0, column=0, sticky="w")
        self.case_number_var = tk.StringVar(value="")
        ttk.Entry(case_frame, textvariable=self.case_number_var, width=20).grid(row=0, column=1, padx=(4, 20))
        tk.Label(case_frame, text="Examiner Name:", bg=COLOR_BG, fg=COLOR_TEXT).grid(row=0, column=2, sticky="w")
        self.examiner_var = tk.StringVar(value="")
        ttk.Entry(case_frame, textvariable=self.examiner_var, width=20).grid(row=0, column=3, padx=(4, 0))

        out_label = tk.Label(case_tab, text="💾 Where to save the image", bg=COLOR_BG, fg=COLOR_ACCENT2,
                              font=("Segoe UI", 11, "bold"), anchor="w")
        out_label.pack(fill="x")

        out_frame = ttk.Frame(case_tab)
        out_frame.pack(fill="x", pady=(6, 12))
        self.output_var = tk.StringVar(value="image_copy.dd")
        ttk.Entry(out_frame, textvariable=self.output_var).pack(side="left", fill="x", expand=True)
        ttk.Button(out_frame, text="💾 Save As", command=self._browse_output, style="Cyan.TButton").pack(
            side="left", padx=(6, 0))

        format_label = tk.Label(case_tab, text="📦 Image format", bg=COLOR_BG, fg=COLOR_ACCENT2,
                                 font=("Segoe UI", 11, "bold"), anchor="w")
        format_label.pack(fill="x")
        format_frame = ttk.Frame(case_tab)
        format_frame.pack(fill="x", pady=(6, 4))
        self.format_var = tk.StringVar(value="raw")
        ttk.Radiobutton(format_frame, text="RAW/DD/ISO", value="raw",
                         variable=self.format_var).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(format_frame, text="Compressed (gzip)", value="gzip",
                         variable=self.format_var).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(format_frame, text="E01-style", value="e01",
                         variable=self.format_var).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(format_frame, text="AFF4-style", value="aff4",
                         variable=self.format_var).pack(side="left")
        tk.Label(case_tab, text="E01/AFF4 are simplified custom containers (case metadata + compression + "
                                 "embedded hash) built with Python's standard library — not byte-compatible "
                                 "with EnCase/FTK or the official AFF4 RDF spec.",
                 bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8), wraplength=560, justify="left").pack(
            fill="x", pady=(6, 0))

        # ==================== TAB 3: Progress & Log ====================
        prog_frame = ttk.Frame(progress_tab)
        prog_frame.pack(fill="x")
        self.progress = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress_pct_var = tk.StringVar(value="0%")
        tk.Label(prog_frame, textvariable=self.progress_pct_var, bg=COLOR_BG, fg=COLOR_ACCENT2,
                 width=6, font=("Segoe UI", 10, "bold")).pack(side="left", padx=(8, 0))

        self.detail_var = tk.StringVar(value="")
        tk.Label(progress_tab, textvariable=self.detail_var, bg=COLOR_BG, fg=COLOR_MUTED,
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(2, 6))

        speed_header = ttk.Frame(progress_tab)
        speed_header.pack(fill="x")
        tk.Label(speed_header, text="📈 Live Throughput", bg=COLOR_BG, fg=COLOR_ACCENT2,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.speed_now_var = tk.StringVar(value="")
        tk.Label(speed_header, textvariable=self.speed_now_var, bg=COLOR_BG, fg=COLOR_MUTED,
                 font=("Segoe UI", 8)).pack(side="right")
        self.speed_canvas = tk.Canvas(progress_tab, height=48, bg=COLOR_LOG_BG, highlightthickness=0)
        self.speed_canvas.pack(fill="x", pady=(4, 10))
        self._speed_history = []  # rolling window of recent bytes/sec samples

        self.banner2_placeholder = None  # (kept for clarity; main banner lives in Connect tab)
        self.result_banner = StatusBanner(progress_tab)
        self.result_banner.pack(fill="x", pady=(0, 12))
        self.result_banner.set("Integrity verification result will appear here.", "info")

        log_header = ttk.Frame(progress_tab)
        log_header.pack(fill="x")
        tk.Label(log_header, text="📋 Activity Log", bg=COLOR_BG, fg=COLOR_ACCENT2,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(log_header, text="Clear", command=self._clear_log, style="Cyan.TButton").pack(side="right")

        self.log_box = tk.Text(progress_tab, height=14, state="disabled", bg=COLOR_LOG_BG, fg="#79b8ff",
                                font=("Consolas", 9), relief="flat", padx=8, pady=6)
        self.log_box.pack(fill="both", expand=True, pady=(8, 0))

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _browse_output(self):
        path = filedialog.asksaveasfilename(title="Save image file as", defaultextension=".dd")
        if path:
            self.output_var.set(path)

    def _log(self, msg):
        def append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{ts()}] {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, append)

    def _log_error(self, msg):
        """Logs like _log(), but also records the error for the audit report."""
        self.error_list.append(f"[{ts()}] {msg}")
        self._log(f"ERROR: {msg}")

    def _reset_speed_graph(self):
        self._speed_history = []
        self.speed_now_var.set("")
        self.speed_canvas.delete("all")

    def _update_speed_graph(self, speed_bytes_per_sec):
        self._speed_history.append(speed_bytes_per_sec)
        max_points = 40
        if len(self._speed_history) > max_points:
            self._speed_history = self._speed_history[-max_points:]

        self.speed_now_var.set(f"{human_size(speed_bytes_per_sec)}/s")

        c = self.speed_canvas
        c.delete("all")
        w = c.winfo_width() or 400
        h = c.winfo_height() or 48
        pts = self._speed_history
        if len(pts) < 2:
            return
        peak = max(pts) or 1
        step_x = w / (max_points - 1)
        start_x = w - (len(pts) - 1) * step_x
        coords = []
        for i, v in enumerate(pts):
            x = start_x + i * step_x
            y = h - 4 - (v / peak) * (h - 10)
            coords.extend([x, y])
        c.create_line(*coords, fill=COLOR_ACCENT2, width=2, smooth=True)
        # subtle filled area under the line for a nicer look
        area = [start_x, h] + coords + [coords[-2], h]
        c.create_polygon(*area, fill=COLOR_ACCENT2, stipple="gray25", outline="")

    def _start_connect(self):
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Error", "Port must be numeric.")
            return
        if not self.output_var.get().strip():
            messagebox.showerror("Error", "Please specify the output file name first.")
            return

        self.cancelled = False
        self.connect_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.banner.set(f"🔌 Connecting to {self.host_var.get()}:{port}...", "warn")
        threading.Thread(target=self._connect_thread, args=(self.host_var.get(), port), daemon=True).start()

    def _select_acquisition_type(self, key):
        self.acquisition_type_var.set(key)
        for k, b in self._acq_buttons.items():
            if k == key:
                b.configure(bg=COLOR_ACCENT, fg="white")
            else:
                b.configure(bg=COLOR_PANEL, fg=COLOR_TEXT)

    def _connect_socket(self, host, port):
        """Shared connect + optional TLS handshake logic."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(8)
        sock.connect((host, port))

        if self.tls_var.get():
            self._log("Setting up TLS encryption...")
            try:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE  # self-signed cert -- encrypted, not CA-authenticated
                sock = ctx.wrap_socket(sock)
                self._log(f"🔒 TLS handshake complete — cipher: {sock.cipher()}")
            except Exception as e:
                raise RuntimeError(f"TLS handshake failed ({e}). Make sure the Server also has "
                                    f"TLS enabled and 'openssl' is available there.")

        sock.settimeout(1.0)
        ready = recv_json(sock, stop_check=lambda: self.cancelled)
        if ready is None or ready.get("type") != "ready":
            raise RuntimeError("Unexpected response from server.")
        if ready.get("encrypted"):
            self._log("🔒 Server confirms encrypted session.")
        return sock

    def _connect_thread(self, host, port):
        try:
            sock = self._connect_socket(host, port)
            self.sock = sock
            self._log("Connected.")

            acq_type = self.acquisition_type_var.get()
            if acq_type == "disk":
                self._log("Acquisition type: Disk Image — listing available disks...")
                self.after(0, lambda: self.banner.set("💽 Listing disks on the remote machine...", "warn"))
                self.request_disks()
            else:
                self._log(f"Acquisition type: {acq_type.title()} — browsing folders on the remote machine...")
                self.after(0, lambda: self.banner.set("🗂️  Browse and select a source on the remote machine...", "warn"))
                self.request_dir(None)
        except StopRequested:
            self._log("Cancelled by user.")
            self.after(0, lambda: self.banner.set("⏹ Cancelled.", "info"))
            self.after(0, self._reset_connect_buttons)
        except Exception as e:
            if not self.cancelled:
                self._log_error(str(e))
                self.after(0, lambda: self.banner.set(f"❌ Connection error: {e}", "err"))
            self.after(0, self._reset_connect_buttons)

    def _reset_connect_buttons(self):
        self.connect_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")

    # ---------------- Cancel / Disconnect ----------------
    def cancel(self):
        self.cancelled = True
        self._log("Cancel requested by user.")
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        if self.browser is not None:
            try:
                if self.browser.winfo_exists():
                    self.browser.destroy()
            except tk.TclError:
                pass
            self.browser = None
        self.banner.set("⏹ Disconnected / cancelled.", "info")
        self._reset_connect_buttons()

    # ---------------- Browsing requests ----------------
    def request_dir(self, path):
        threading.Thread(target=self._request_dir_thread, args=(path,), daemon=True).start()

    def _request_dir_thread(self, path):
        try:
            if self.sock is None:
                return
            send_json(self.sock, {"cmd": "list_dir", "path": path})
            resp = recv_json(self.sock, stop_check=lambda: self.cancelled)
            if resp is None:
                raise RuntimeError("Connection closed.")
            if resp.get("type") == "error":
                self.after(0, lambda: messagebox.showerror("Error", resp.get("message", "Unknown error")))
                return
            self.after(0, lambda: self._ensure_browser_and_show(resp, "dir"))
        except StopRequested:
            pass
        except Exception as e:
            if not self.cancelled:
                self._log_error(str(e))

    def request_disks(self):
        threading.Thread(target=self._request_disks_thread, daemon=True).start()

    def _request_disks_thread(self):
        try:
            if self.sock is None:
                return
            send_json(self.sock, {"cmd": "list_disks"})
            resp = recv_json(self.sock, stop_check=lambda: self.cancelled)
            if resp is None:
                raise RuntimeError("Connection closed.")
            self.after(0, lambda: self._ensure_browser_and_show(resp, "disks"))
        except StopRequested:
            pass
        except Exception as e:
            if not self.cancelled:
                self._log_error(str(e))

    def _ensure_browser_and_show(self, resp, kind):
        if self.browser is None or not self.browser.winfo_exists():
            self.browser = RemoteBrowser(self.winfo_toplevel(), self)
        if kind == "dir":
            self.browser.show_dir(resp)
        else:
            self.browser.show_disks(resp)
        self.browser.lift()

    # ---------------- After selection is confirmed ----------------
    def select_remote_source(self, remote_path):
        self._log(f"Selected remote source: {remote_path}")
        self.banner.set(f"📥 Selected: {remote_path} — starting transfer...", "warn")
        self.progress["value"] = 0
        self.progress_pct_var.set("0%")
        self.result_banner.set("Integrity verification result will appear here.", "info")
        self._reset_speed_graph()
        self.error_list = []  # each transfer gets its own clean error log --
                               # errors from earlier unrelated attempts (e.g. a
                               # failed connection before this one) must not
                               # appear in THIS transfer's audit report.
        self._sub_notebook.select(self._progress_tab_index)
        threading.Thread(target=self._select_and_receive, args=(remote_path,), daemon=True).start()

    def _select_and_receive(self, remote_path):
        try:
            image_format = self.format_var.get()  # "raw" | "gzip" | "e01" | "aff4"
            send_json(self.sock, {
                "cmd": "select", "path": remote_path, "format": image_format,
                "case_number": self.case_number_var.get().strip(),
                "examiner_name": self.examiner_var.get().strip(),
            })
            # Keep a short timeout throughout so Cancel can interrupt a
            # blocked read at any point, including mid-transfer.
            meta = recv_json(self.sock, stop_check=lambda: self.cancelled)
            if meta is None:
                raise RuntimeError("Connection closed.")
            if meta.get("type") == "error":
                raise RuntimeError(meta.get("message", "Server error"))
            self._receive_image(self.sock, meta, self.output_var.get())
        except StopRequested:
            self._log("Cancelled by user.")
            self.after(0, lambda: self.banner.set("⏹ Cancelled.", "info"))
        except Exception as e:
            if not self.cancelled:
                self._log_error(str(e))
                self.after(0, lambda: self.banner.set(f"❌ Error: {e}", "err"))
            else:
                self._log("Cancelled by user.")
                self.after(0, lambda: self.banner.set("⏹ Cancelled.", "info"))
        finally:
            self.after(0, self._reset_connect_buttons)

    def _receive_image(self, sock, meta, output_path):
        total_size = meta["size"]
        chunk_size = meta["chunk_size"]
        total_chunks = meta.get("total_chunks") or (math.ceil(total_size / chunk_size) if total_size else 0)
        is_folder_archive = meta.get("is_folder_archive", False)
        compressed = meta.get("compressed", False)
        archive_format = meta.get("archive_format")
        image_format = meta.get("image_format", "raw")
        encrypted = meta.get("encrypted", False)

        # --- Decide output filename extension based on source type/format ---
        ext_map = {"tar.gz": ".tar.gz", "tar": ".tar", "gz": ".gz", "e01": ".E01", "aff4": ".aff4"}
        if archive_format in ext_map and not output_path.lower().endswith(ext_map[archive_format]):
            output_path = output_path + ext_map[archive_format]
            self._log(f"Output file set to match format ({image_format.upper()}): {output_path}")

        self._log(f"Source: {meta['source']}"
                   f"{' (folder -> tar archive)' if is_folder_archive else ''}"
                   f"{f' ({image_format.upper()} format)' if image_format != 'raw' else ''}"
                   f"{' 🔒' if encrypted else ''} | Size: {human_size(total_size)} | {total_chunks} chunk(s)")
        self.after(0, lambda: self.banner.set("📥 Transfer in progress...", "warn"))

        received = 0
        start_time = time.time()
        lock_acquired = False
        temp_path = output_path + ".part"
        last_log = 0
        bad_indices = []
        retry_rounds_used = 0
        chunks_retried_total = set()

        out_f = open(temp_path, "wb")
        try:
            if HAS_FCNTL:
                try:
                    fcntl.flock(out_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    lock_acquired = True
                    self._log("🔒 Exclusive file lock acquired.")
                except OSError:
                    self._log("⚠️ Could not acquire file lock.")
            else:
                self._log("⚠️ Exclusive lock not supported on this system, step skipped.")

            # ---- Single-pass, chunk-verified receive: the server sends a small
            # JSON header (index + hash + length) immediately before each raw
            # chunk, so hashing and transfer happen together -- there is no
            # separate up-front "compute the whole manifest first" pass, which
            # for a large disk could take many minutes with zero visible
            # progress (looked like the app had frozen). ----
            last_received_for_speed = 0
            for _ in range(total_chunks):
                if self.cancelled:
                    raise StopRequested()
                header = recv_json(sock, stop_check=lambda: self.cancelled)
                if header is None:
                    raise RuntimeError("Connection closed before all chunks arrived.")
                idx = header["index"]
                expected_hash = header["hash"]
                length = header["length"]
                data = recv_exact(sock, length, stop_check=lambda: self.cancelled)
                if hashlib.sha256(data).hexdigest() != expected_hash:
                    self._log(f"⚠️ Chunk #{idx} failed verification on arrival — will request a re-send.")
                    bad_indices.append(idx)
                out_f.write(data)
                received += len(data)
                now = time.time()
                pct = (received / total_size * 100) if total_size else 100
                self.after(0, lambda p=pct: self.progress.configure(value=p))
                self.after(0, lambda p=pct: self.progress_pct_var.set(f"{p:.0f}%"))
                if now - last_log > 0.5 or received == total_size:
                    interval = now - last_log if last_log else (now - start_time)
                    instant_speed = (received - last_received_for_speed) / interval if interval > 0 else 0
                    self.after(0, lambda s=instant_speed: self._update_speed_graph(s))
                    last_received_for_speed = received
                    last_log = now
                    speed = human_speed(received, now - start_time)
                    detail = f"{human_size(received)} / {human_size(total_size)}   ·   speed: {speed}"
                    self.after(0, lambda d=detail: self.detail_var.set(d))
                    self._log(f"Received: {human_size(received)}/{human_size(total_size)}  ({pct:.1f}%)")

            out_f.flush()
            os.fsync(out_f.fileno())

            # ---- Automatic self-healing: request re-sends for any
            # chunk(s) that failed verification, up to 3 rounds. ----
            round_num = 0
            while bad_indices and round_num < 3:
                round_num += 1
                retry_rounds_used = round_num
                chunks_retried_total.update(bad_indices)
                self._log(f"🔁 Auto-retry round {round_num}: requesting {len(bad_indices)} "
                           f"chunk(s) again: {bad_indices}")
                self.after(0, lambda: self.banner.set(f"🔁 Auto-correcting {len(bad_indices)} "
                                                        f"corrupted chunk(s) (round {round_num})...", "warn"))
                send_json(sock, {"cmd": "resend_chunks", "indices": bad_indices})
                still_bad = []
                for _ in bad_indices:
                    header = recv_json(sock, stop_check=lambda: self.cancelled)
                    idx, length, expected_hash = header["index"], header["length"], header["hash"]
                    data = recv_exact(sock, length, stop_check=lambda: self.cancelled)
                    if hashlib.sha256(data).hexdigest() == expected_hash:
                        out_f.seek(idx * chunk_size)
                        out_f.write(data)
                        out_f.flush()
                        self._log(f"✅ Chunk #{idx} corrected successfully.")
                    else:
                        still_bad.append(idx)
                        self._log(f"❌ Chunk #{idx} still mismatched after retry.")
                bad_indices = still_bad

            send_json(sock, {"cmd": "done"})
            out_f.flush()
            os.fsync(out_f.fileno())
        except StopRequested:
            if HAS_FCNTL and lock_acquired:
                fcntl.flock(out_f.fileno(), fcntl.LOCK_UN)
            out_f.close()
            try:
                os.remove(temp_path)
                self._log(f"Cancelled — partial file removed: {temp_path}")
            except OSError:
                pass
            raise
        finally:
            if HAS_FCNTL and lock_acquired and not out_f.closed:
                fcntl.flock(out_f.fileno(), fcntl.LOCK_UN)
            if not out_f.closed:
                out_f.close()

        end_time = time.time()
        elapsed = end_time - start_time

        # Final whole-file hash (independent, holistic re-check on top of
        # the per-chunk verification above).
        local_hasher = hashlib.sha256()
        with open(temp_path, "rb") as f:
            while True:
                c = f.read(CHUNK_SIZE)
                if not c:
                    break
                local_hasher.update(c)
        local_hash = local_hasher.hexdigest()

        footer = recv_json(sock, stop_check=lambda: self.cancelled)
        remote_hash = footer["final_sha256"]
        original_hash = footer.get("original_sha256") or meta.get("original_sha256")
        server_retry_rounds = footer.get("retry_rounds", retry_rounds_used)

        integrity_ok = (local_hash == remote_hash) and not bad_indices

        self._log(f"Local  SHA-256 (transferred bytes): {local_hash}")
        self._log(f"Source SHA-256 (transferred bytes): {remote_hash}")
        if original_hash:
            self._log(f"Original (pre-compression) data SHA-256: {original_hash}")
        if chunks_retried_total:
            self._log(f"🔁 Chunks that needed auto-correction: {sorted(chunks_retried_total)} "
                       f"({len(chunks_retried_total)} total, {retry_rounds_used} round(s))")

        made_read_only = False
        final_path_used = temp_path
        if integrity_ok:
            os.replace(temp_path, output_path)
            final_path_used = output_path
            self._log(f"Verified, moved to final name: {output_path}")
            try:
                os.chmod(output_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                made_read_only = True
                self._log("🔒 File set to read-only.")
            except OSError as e:
                self._log(f"⚠️ Could not set read-only: {e}")
        else:
            self._log_error("Integrity could not be verified, file left as a draft: " + temp_path)

        # --- Destination disk info (best-effort, gathered locally) ---
        dest_device = find_disk_for_path(output_path)
        if dest_device:
            dest_info = get_disk_info_for_device(dest_device)
            dest_model, dest_serial = dest_info["model"], dest_info["serial"]
        else:
            dest_device, dest_model, dest_serial = "Unknown", "Unknown", "Unknown"

        # --- Chain of custody: who / when / from where ---
        case_number = self.case_number_var.get().strip() or "(not specified)"
        examiner_name = self.examiner_var.get().strip() or "(not specified)"
        dest_hostname = get_hostname()
        try:
            dest_ip = sock.getsockname()[0]
        except OSError:
            dest_ip = None
        source_hostname = meta.get("source_hostname", "Unknown")
        source_ip = meta.get("source_ip") or self.host_var.get()

        start_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))
        end_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))

        report = {
            "case_number": case_number,
            "examiner_name": examiner_name,
            "source_path": meta["source"],
            "output_path": final_path_used,
            "declared_size_bytes": total_size,
            "received_size_bytes": received,
            "total_chunks": total_chunks,
            "hash_algorithm": "sha256",
            "source_hash": remote_hash,
            "local_hash": local_hash,
            "original_data_hash": original_hash,
            "integrity_verified": integrity_ok,
            "exclusive_lock_used": lock_acquired,
            "file_made_read_only": made_read_only,
            "atomic_rename_applied": integrity_ok,
            "is_folder_archive": is_folder_archive,
            "compressed": compressed,
            "image_format": image_format,
            "archive_format": archive_format,
            "encrypted_transfer": encrypted,
            "chunks_auto_corrected": sorted(chunks_retried_total),
            "auto_retry_rounds_used": retry_rounds_used,
            "chunks_unrecoverable": bad_indices,
            "source_disk_model": meta.get("source_model"),
            "source_disk_serial": meta.get("source_serial"),
            "source_write_protected": meta.get("source_write_protected"),
            "source_hostname": source_hostname,
            "source_ip": source_ip,
            "destination_disk_device": dest_device,
            "destination_disk_model": dest_model,
            "destination_disk_serial": dest_serial,
            "destination_hostname": dest_hostname,
            "destination_ip": dest_ip,
            "transfer_started": start_iso,
            "transfer_ended": end_iso,
            "transfer_duration_sec": round(elapsed, 2),
            "acquisition_tool": f"{APP_NAME} (remote source selection)",
            "errors": list(self.error_list),
        }
        report_path = os.path.splitext(output_path)[0] + "_chain_of_custody.json"
        with open(report_path, "w", encoding="utf-8") as rf:
            json.dump(report, rf, indent=2, ensure_ascii=False)
        self._log(f"📄 JSON report saved: {report_path}")

        # --- Human-readable .txt audit log ---
        txt_path = os.path.splitext(output_path)[0] + "_audit_log.txt"
        lines = []
        lines.append("=" * 60)
        lines.append(f" {APP_NAME} — FORENSIC IMAGE ACQUISITION AUDIT LOG")
        lines.append("=" * 60)
        lines.append(f"Case Number        : {case_number}")
        lines.append(f"Examiner Name      : {examiner_name}")
        lines.append(f"Start Time         : {start_iso}")
        lines.append(f"End Time           : {end_iso}")
        lines.append(f"Duration           : {elapsed:.2f} seconds")
        lines.append(f"Chunks             : {total_chunks} (chunk size: {human_size(chunk_size)})")
        lines.append(f"Encrypted Transfer : {'YES (TLS)' if encrypted else 'NO'}")
        lines.append("")
        lines.append("CHAIN OF CUSTODY")
        lines.append(f"  Acquired by      : {examiner_name}")
        lines.append(f"  Source machine   : {source_hostname}  ({source_ip})")
        lines.append(f"  Destination machine: {dest_hostname}  ({dest_ip})")
        lines.append(f"  Timestamp        : {start_iso} → {end_iso}")
        lines.append("")
        lines.append("SOURCE")
        lines.append(f"  Path             : {meta['source']}")
        lines.append(f"  Type             : {'Folder (tar)' if is_folder_archive else ('Disk' if meta.get('is_disk_source') else 'File')}")
        lines.append(f"  Model            : {meta.get('source_model', 'N/A')}")
        lines.append(f"  Serial Number    : {meta.get('source_serial', 'N/A')}")
        swp = meta.get("source_write_protected")
        lines.append(f"  Write-Protected  : {'YES (OS-reported read-only)' if swp is True else ('NO' if swp is False else 'N/A / Unknown')}")
        lines.append("")
        lines.append("DESTINATION")
        lines.append(f"  Path             : {final_path_used}")
        lines.append(f"  Disk Device      : {dest_device}")
        lines.append(f"  Model            : {dest_model}")
        lines.append(f"  Serial Number    : {dest_serial}")
        lines.append("")
        lines.append(f"Image Format       : {image_format.upper()}"
                     f"{' (' + archive_format.upper() + ')' if archive_format and archive_format != image_format else ''}")
        lines.append(f"Hash Algorithm     : SHA-256")
        lines.append(f"Transfer Hash (local)  : {local_hash}")
        lines.append(f"Transfer Hash (source) : {remote_hash}")
        if original_hash:
            lines.append(f"Original Data Hash (pre-compression): {original_hash}")
        lines.append(f"Integrity Verified : {'YES' if integrity_ok else 'NO'}")
        lines.append(f"Exclusive Lock Used: {'YES' if lock_acquired else 'NO'}")
        lines.append(f"Read-Only Applied  : {'YES' if made_read_only else 'NO'}")
        if chunks_retried_total:
            lines.append(f"Auto-Corrected Chunks: {sorted(chunks_retried_total)} ({retry_rounds_used} round(s))")
        if bad_indices:
            lines.append(f"UNRECOVERABLE Chunks: {bad_indices}")
        lines.append("")
        lines.append("ERRORS ENCOUNTERED")
        if self.error_list:
            for err in self.error_list:
                lines.append(f"  - {err}")
        else:
            lines.append("  (none)")
        lines.append("=" * 60)

        with open(txt_path, "w", encoding="utf-8") as tf:
            tf.write("\n".join(lines) + "\n")
        self._log(f"📄 Text audit log saved: {txt_path}")

        # --- Professional HTML integrity report (printable to PDF from any browser) ---
        html_path = os.path.splitext(output_path)[0] + "_integrity_report.html"
        self._write_html_report(html_path, report)
        self._log(f"📄 HTML integrity report saved: {html_path} (open in a browser, then Print → Save as PDF)")

        if is_folder_archive and integrity_ok and archive_format in ("tar", "tar.gz"):
            extract_cmd = "tar -xzf" if archive_format == "tar.gz" else "tar -xf"
            self._log(f"ℹ️ This is a folder archive. To extract: {extract_cmd} \"{output_path}\"")
        elif image_format == "gzip" and integrity_ok:
            self._log(f"ℹ️ This is gzip-compressed. To decompress: gunzip \"{output_path}\"")
        elif image_format == "e01" and integrity_ok:
            self._log(f"ℹ️ This is a CustomE01-style container (simplified, not EnCase/FTK-compatible). "
                       f"Use this tool's build_custom_e01/extract_custom_e01 helpers, or a script with "
                       f"zlib, to extract the raw data and verify its embedded hash.")
        elif image_format == "aff4" and integrity_ok:
            self._log(f"ℹ️ This is a CustomAFF4-style container — a real ZIP file. You can inspect it with "
                       f"'unzip -l \"{output_path}\"' or extract 'data.raw' directly with any zip tool.")

        if integrity_ok:
            self.after(0, lambda: self.banner.set("✅ Transfer complete.", "ok"))
            self.after(0, lambda: self.result_banner.set(
                f"✅ INTEGRITY VERIFIED — hashes match exactly  ({elapsed:.1f}s)"
                f"{f'  ·  {len(chunks_retried_total)} chunk(s) auto-corrected' if chunks_retried_total else ''}",
                "ok"))
        else:
            self.after(0, lambda: self.banner.set("❌ Integrity error occurred.", "err"))
            self.after(0, lambda: self.result_banner.set(
                "❌ HASHES DO NOT MATCH — data integrity could not be verified!", "err"))

        try:
            sock.close()
        except OSError:
            pass
        self.sock = None

    def _write_html_report(self, html_path, r):
        """Writes a clean, professional-looking HTML integrity report.
        Open it in any browser and use Print → Save as PDF for a PDF copy."""
        def esc(v):
            if v is None:
                return "N/A"
            return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        status_color = "#16a34a" if r["integrity_verified"] else "#dc2626"
        status_text = "INTEGRITY VERIFIED" if r["integrity_verified"] else "INTEGRITY FAILED"

        def row(label, value):
            return f"<tr><td class='k'>{esc(label)}</td><td class='v'>{esc(value)}</td></tr>"

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Integrity Report — {esc(r['case_number'])}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f3f4f6; margin:0; padding:32px; color:#1f2937; }}
  .sheet {{ max-width:820px; margin:0 auto; background:white; border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.08); overflow:hidden; }}
  .header {{ background:linear-gradient(135deg,#8b5cf6,#22d3ee); color:white; padding:28px 32px; }}
  .header h1 {{ margin:0; font-size:22px; }}
  .header p {{ margin:4px 0 0; opacity:0.9; font-size:13px; }}
  .status {{ display:inline-block; margin:20px 32px 0; padding:10px 18px; border-radius:8px;
             font-weight:bold; color:white; background:{status_color}; font-size:15px; }}
  .section {{ padding: 20px 32px; border-top:1px solid #e5e7eb; }}
  .section h2 {{ font-size:14px; text-transform:uppercase; letter-spacing:0.05em; color:#6b7280; margin:0 0 12px; }}
  table {{ width:100%; border-collapse:collapse; }}
  td {{ padding:6px 0; font-size:13px; vertical-align:top; }}
  td.k {{ color:#6b7280; width:220px; }}
  td.v {{ color:#111827; font-family: Consolas, monospace; word-break:break-all; }}
  .footer {{ padding:16px 32px; font-size:11px; color:#9ca3af; }}
</style></head>
<body>
<div class="sheet">
  <div class="header">
    <h1>🔍 {esc(APP_NAME)} — Forensic Image Integrity Report</h1>
    <p>Case {esc(r['case_number'])} · Examined by {esc(r['examiner_name'])}</p>
  </div>
  <div class="status">{status_text}</div>

  <div class="section">
    <h2>Chain of Custody</h2>
    <table>
      {row("Case Number", r["case_number"])}
      {row("Examiner Name", r["examiner_name"])}
      {row("Source Machine", f"{r.get('source_hostname')} ({r.get('source_ip')})")}
      {row("Destination Machine", f"{r.get('destination_hostname')} ({r.get('destination_ip')})")}
      {row("Transfer Started", r["transfer_started"])}
      {row("Transfer Ended", r["transfer_ended"])}
      {row("Duration (seconds)", r["transfer_duration_sec"])}
      {row("Encrypted Transfer (TLS)", "Yes" if r.get("encrypted_transfer") else "No")}
    </table>
  </div>

  <div class="section">
    <h2>Source</h2>
    <table>
      {row("Path", r["source_path"])}
      {row("Model", r.get("source_disk_model"))}
      {row("Serial Number", r.get("source_disk_serial"))}
      {row("Write-Protected (OS-reported)", r.get("source_write_protected"))}
    </table>
  </div>

  <div class="section">
    <h2>Destination</h2>
    <table>
      {row("Path", r["output_path"])}
      {row("Disk Device", r.get("destination_disk_device"))}
      {row("Model", r.get("destination_disk_model"))}
      {row("Serial Number", r.get("destination_disk_serial"))}
    </table>
  </div>

  <div class="section">
    <h2>Integrity &amp; Hashing</h2>
    <table>
      {row("Hash Algorithm", r["hash_algorithm"].upper())}
      {row("Source Hash (transferred bytes)", r["source_hash"])}
      {row("Local Hash (transferred bytes)", r["local_hash"])}
      {row("Original Data Hash (pre-compression)", r.get("original_data_hash") or "N/A")}
      {row("Total Chunks", r.get("total_chunks"))}
      {row("Chunks Auto-Corrected", r.get("chunks_auto_corrected") or "None")}
      {row("Auto-Retry Rounds Used", r.get("auto_retry_rounds_used"))}
      {row("Unrecoverable Chunks", r.get("chunks_unrecoverable") or "None")}
      {row("Exclusive Lock Used", "Yes" if r["exclusive_lock_used"] else "No")}
      {row("Read-Only Applied", "Yes" if r["file_made_read_only"] else "No")}
      {row("Image Format", r["image_format"])}
    </table>
  </div>

  <div class="section">
    <h2>Errors Encountered</h2>
    <table>{"".join(row('Error', e) for e in r["errors"]) if r["errors"] else row("Errors", "None")}</table>
  </div>

  <div class="footer">Generated automatically by {esc(APP_NAME)}. Open this file in any web browser and use
  Print → Save as PDF to produce a PDF copy for submission.</div>
</div>
</body></html>"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)


# ----------------------------------------------------------------------
# VERIFY TAB — post-acquisition re-verification. Real forensic evidence
# often needs to be re-verified long after acquisition (e.g. before a
# court hearing, or when handing custody to another examiner) to prove
# it hasn't been tampered with. This recomputes the image's hash and
# compares it against the original chain-of-custody report.
# ----------------------------------------------------------------------
class VerifyTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=18, style="Panel.TFrame")
        self._build_ui()

    def _build_ui(self):
        intro = tk.Label(
            self,
            text=("Use this anytime AFTER an acquisition — e.g. before a court hearing, or when handing "
                  "the evidence to another examiner — to prove the image file hasn't been altered since "
                  "it was captured. It recomputes the file's SHA-256 and compares it to the original report."),
            justify="left", anchor="w", bg=COLOR_BG, fg=COLOR_MUTED,
            font=("Segoe UI", 9), wraplength=620,
        )
        intro.pack(fill="x", pady=(0, 16))

        img_label = tk.Label(self, text="📁 Image file to verify", bg=COLOR_BG, fg=COLOR_ACCENT2,
                              font=("Segoe UI", 11, "bold"), anchor="w")
        img_label.pack(fill="x")
        img_frame = ttk.Frame(self)
        img_frame.pack(fill="x", pady=(6, 14))
        self.image_path_var = tk.StringVar(value="")
        ttk.Entry(img_frame, textvariable=self.image_path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(img_frame, text="📂 Browse", command=self._browse_image, style="Cyan.TButton").pack(
            side="left", padx=(6, 0))

        report_label = tk.Label(self, text="📄 Original chain-of-custody report (.json)", bg=COLOR_BG,
                                 fg=COLOR_ACCENT2, font=("Segoe UI", 11, "bold"), anchor="w")
        report_label.pack(fill="x")
        report_frame = ttk.Frame(self)
        report_frame.pack(fill="x", pady=(6, 6))
        self.report_path_var = tk.StringVar(value="")
        ttk.Entry(report_frame, textvariable=self.report_path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(report_frame, text="📂 Browse", command=self._browse_report, style="Cyan.TButton").pack(
            side="left", padx=(6, 0))
        tk.Label(self, text="This is the '..._chain_of_custody.json' file saved next to the image "
                             "at acquisition time.",
                 bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(fill="x", pady=(0, 14))

        self.verify_btn = ttk.Button(self, text="🔍  Verify Integrity Now", command=self._start_verify,
                                      style="Accent.TButton")
        self.verify_btn.pack(fill="x", ipady=6, pady=(0, 14))

        self.result_banner = StatusBanner(self)
        self.result_banner.pack(fill="x", pady=(0, 14))
        self.result_banner.set("⏳ Select an image file and its report, then click Verify.", "info")

        details_label = tk.Label(self, text="📋 Details", bg=COLOR_BG, fg=COLOR_ACCENT2,
                                  font=("Segoe UI", 11, "bold"), anchor="w")
        details_label.pack(fill="x")
        self.details_box = tk.Text(self, height=14, state="disabled", bg=COLOR_LOG_BG, fg="#7ee787",
                                    font=("Consolas", 9), relief="flat", padx=8, pady=6)
        self.details_box.pack(fill="both", expand=True, pady=(6, 0))

    def _log(self, msg):
        self.details_box.configure(state="normal")
        self.details_box.insert("end", f"{msg}\n")
        self.details_box.see("end")
        self.details_box.configure(state="disabled")

    def _clear_log(self):
        self.details_box.configure(state="normal")
        self.details_box.delete("1.0", "end")
        self.details_box.configure(state="disabled")

    def _browse_image(self):
        path = filedialog.askopenfilename(title="Select the image file to verify")
        if path:
            self.image_path_var.set(path)
            guess = os.path.splitext(path)[0]
            if guess.endswith((".dd", ".tar", ".gz", ".E01", ".aff4", ".raw")):
                guess = os.path.splitext(guess)[0]
            candidate = guess + "_chain_of_custody.json"
            if os.path.exists(candidate):
                self.report_path_var.set(candidate)

    def _browse_report(self):
        path = filedialog.askopenfilename(title="Select the chain-of-custody .json report",
                                           filetypes=[("JSON report", "*.json"), ("All files", "*.*")])
        if path:
            self.report_path_var.set(path)

    def _start_verify(self):
        image_path = self.image_path_var.get().strip()
        report_path = self.report_path_var.get().strip()
        if not image_path or not os.path.isfile(image_path):
            messagebox.showerror("Error", "Please select a valid image file.")
            return
        if not report_path or not os.path.isfile(report_path):
            messagebox.showerror("Error", "Please select a valid chain-of-custody .json report.")
            return
        self._clear_log()
        self.verify_btn.configure(state="disabled")
        self.result_banner.set("⏳ Verifying...", "warn")
        threading.Thread(target=self._verify_thread, args=(image_path, report_path), daemon=True).start()

    def _verify_thread(self, image_path, report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)

            expected_hash = report.get("source_hash") or report.get("local_hash")
            if not expected_hash:
                raise ValueError("The report file doesn't contain a recognizable hash field.")

            self._log(f"Case Number     : {report.get('case_number', 'N/A')}")
            self._log(f"Examiner        : {report.get('examiner_name', 'N/A')}")
            self._log(f"Acquired        : {report.get('transfer_started', 'N/A')} → "
                       f"{report.get('transfer_ended', 'N/A')}")
            self._log(f"Original source : {report.get('source_path', 'N/A')}")
            self._log(f"Expected SHA-256: {expected_hash}")
            self._log("")
            self._log(f"Hashing '{image_path}' now...")

            file_size = os.path.getsize(image_path)
            hasher = hashlib.sha256()
            read_so_far = 0
            with open(image_path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    read_so_far += len(chunk)
            actual_hash = hasher.hexdigest()

            self._log(f"Computed SHA-256: {actual_hash}")
            self._log(f"File size       : {human_size(file_size)} ({file_size} bytes)")
            self._log("")

            match = (actual_hash == expected_hash)
            verify_time = time.strftime("%Y-%m-%d %H:%M:%S")
            self._log(f"Verification performed at: {verify_time}")

            if match:
                self._log("✅ RESULT: Hashes match exactly. This image is IDENTICAL to what was "
                           "acquired — no tampering or corruption detected since acquisition.")
                self.after(0, lambda: self.result_banner.set(
                    "✅ VERIFIED — this image is unchanged since acquisition.", "ok"))
            else:
                self._log("❌ RESULT: Hashes DO NOT MATCH. This file has changed since it was "
                           "acquired — it may have been modified, corrupted, or is not the same file.")
                self.after(0, lambda: self.result_banner.set(
                    "❌ MISMATCH — this file differs from the original acquisition!", "err"))

            # Append a re-verification record to the original report (audit trail
            # of every time this evidence was checked, by whom, and when).
            report.setdefault("re_verifications", []).append({
                "verified_at": verify_time,
                "hostname": get_hostname(),
                "result": "MATCH" if match else "MISMATCH",
                "recomputed_hash": actual_hash,
            })
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            self._log(f"\n📄 Re-verification recorded in: {report_path}")

        except Exception as e:
            self._log(f"ERROR: {e}")
            self.after(0, lambda: self.result_banner.set(f"❌ Error: {e}", "err"))
        finally:
            self.after(0, lambda: self.verify_btn.configure(state="normal"))


# ----------------------------------------------------------------------
# Scrollable tab wrapper (adds a vertical scrollbar + mouse-wheel
# support around a tab's content, so nothing gets cut off on shorter
# screens/windows)
# ----------------------------------------------------------------------
class ScrollableTab(ttk.Frame):
    def __init__(self, parent, tab_class):
        super().__init__(parent)
        canvas = tk.Canvas(self, bg=COLOR_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tab_class(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", on_inner_configure)

        def on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind("<Configure>", on_canvas_configure)

        def _on_mousewheel(event):
            delta = event.delta if event.delta else 0
            if delta:
                canvas.yview_scroll(int(-1 * (delta / 120)), "units")

        def _bind_wheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        def _unbind_wheel(event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        self.inner = inner


# ----------------------------------------------------------------------
# MAIN WINDOW
# ----------------------------------------------------------------------
def _load_app_icon(root):
    """Sets the window/taskbar icon from the embedded base64 PNG.
    Falls back silently (no icon) if the platform/theme doesn't support it."""
    try:
        icon_img = tk.PhotoImage(data=base64.b64decode(ICON_B64))
        root.iconphoto(True, icon_img)
        root._icon_img_ref = icon_img  # keep a reference so it isn't garbage-collected
        return icon_img
    except Exception:
        return None


def _show_splash(root, logo_img):
    """Brief splash screen shown while the main window is being built."""
    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    w, h = 360, 220
    sw = splash.winfo_screenwidth()
    sh = splash.winfo_screenheight()
    splash.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    splash.configure(bg=THEMES["dark"]["BG"])
    try:
        splash.attributes("-topmost", True)
    except tk.TclError:
        pass

    if logo_img is not None:
        tk.Label(splash, image=logo_img, bg=THEMES["dark"]["BG"]).pack(pady=(36, 12))
    tk.Label(splash, text=APP_NAME, font=("Segoe UI", 20, "bold"),
             bg=THEMES["dark"]["BG"], fg=THEMES["dark"]["TEXT"]).pack()
    tk.Label(splash, text=APP_TAGLINE, font=("Segoe UI", 9),
             bg=THEMES["dark"]["BG"], fg=THEMES["dark"]["ACCENT2"]).pack(pady=(2, 0))
    tk.Label(splash, text="Loading...", font=("Segoe UI", 8),
             bg=THEMES["dark"]["BG"], fg=THEMES["dark"]["MUTED"]).pack(side="bottom", pady=14)

    splash.update()
    return splash


def _apply_ttk_styles(style):
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TFrame", background=COLOR_BG)
    style.configure("Panel.TFrame", background=COLOR_BG)
    style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("TEntry", fieldbackground="#ffffff", padding=4)
    style.configure("TButton", padding=6)

    style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"),
                     background=COLOR_ACCENT, foreground="white", borderwidth=0, focusthickness=0)
    style.map("Accent.TButton",
              background=[("active", "#a78bfa"), ("disabled", "#4b4b63")],
              foreground=[("disabled", "#9a9ab0")])

    style.configure("Danger.TButton", font=("Segoe UI", 10, "bold"),
                     background=COLOR_ERR, foreground="white", borderwidth=0, focusthickness=0)
    style.map("Danger.TButton",
              background=[("active", "#ff8095"), ("disabled", "#4b4b63")],
              foreground=[("disabled", "#9a9ab0")])

    style.configure("Cyan.TButton", font=("Segoe UI", 9, "bold"),
                     background=COLOR_ACCENT2, foreground="#0c0c14", borderwidth=0)
    style.map("Cyan.TButton", background=[("active", "#67e8f9")])

    style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 10, "bold"),
                     background=COLOR_PANEL, foreground=COLOR_MUTED)
    style.map("TNotebook.Tab",
              background=[("selected", COLOR_ACCENT)],
              foreground=[("selected", "white")])

    style.configure("Sub.TNotebook", background=COLOR_BG, borderwidth=0)
    style.configure("Sub.TNotebook.Tab", padding=(14, 8), font=("Segoe UI", 9, "bold"),
                     background=COLOR_PANEL, foreground=COLOR_MUTED)
    style.map("Sub.TNotebook.Tab",
              background=[("selected", COLOR_ACCENT2)],
              foreground=[("selected", "#0c0c14")])

    style.configure("Horizontal.TProgressbar", thickness=18, background=COLOR_ACCENT2, troughcolor=COLOR_PANEL)


def main():
    root = tk.Tk()
    root.withdraw()  # hide the (still empty) main window until the splash has shown
    root.title(f"{APP_NAME} — {APP_TAGLINE}")
    root.geometry("720x820")
    root.minsize(640, 640)

    logo_img = _load_app_icon(root)
    splash = _show_splash(root, logo_img)
    splash.update()
    time.sleep(1.3)  # keep the splash on screen long enough to actually be seen

    style = ttk.Style()

    def build_ui():
        for child in root.winfo_children():
            child.destroy()
        root.configure(bg=COLOR_BG)
        _apply_ttk_styles(style)

        header = tk.Frame(root, bg=COLOR_BG)
        header.pack(fill="x", padx=18, pady=(18, 6))

        title_row = tk.Frame(header, bg=COLOR_BG)
        title_row.pack(fill="x", anchor="w")
        if logo_img is not None:
            tk.Label(title_row, image=logo_img, bg=COLOR_BG).pack(side="left", padx=(0, 10))
        title_text = tk.Frame(title_row, bg=COLOR_BG)
        title_text.pack(side="left", fill="both", expand=True)
        tk.Label(title_text, text=APP_NAME, font=("Segoe UI", 18, "bold"),
                  bg=COLOR_BG, fg=COLOR_TEXT).pack(anchor="w")
        tk.Label(title_text, text=APP_TAGLINE, font=("Segoe UI", 9),
                  bg=COLOR_BG, fg=COLOR_ACCENT).pack(anchor="w")

        theme_icon = "🌙" if CURRENT_THEME == "light" else "☀️"
        theme_btn = tk.Button(
            title_row, text=f"{theme_icon}", font=("Segoe UI", 12), relief="flat", bd=0,
            bg=COLOR_PANEL, fg=COLOR_TEXT, activebackground=COLOR_ACCENT2, cursor="hand2",
            command=lambda: toggle_theme(),
        )
        theme_btn.pack(side="right", padx=(8, 0), ipadx=8, ipady=4)

        ttk.Separator(root, orient="horizontal").pack(fill="x", padx=18, pady=(0, 8))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        server_tab = ScrollableTab(notebook, ServerTab)
        client_tab = ScrollableTab(notebook, ClientTab)
        verify_tab = ScrollableTab(notebook, VerifyTab)

        notebook.add(server_tab, text="🖥️  SERVER (Source Machine)")
        notebook.add(client_tab, text="💻  CLIENT (Local Machine)")
        notebook.add(verify_tab, text="🔁  VERIFY (Later Re-check)")

    def toggle_theme():
        apply_theme("light" if CURRENT_THEME == "dark" else "dark")
        build_ui()

    build_ui()

    splash.destroy()
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
