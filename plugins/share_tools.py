"""Share & path inspection tools."""

import os
import subprocess


@mcp.tool()
def share_sizes(top_n: int = 30) -> str:
    """Größe jedes Top-Level-Shares unter /mnt/user, sortiert."""
    base = "/host_mnt/user"
    if not os.path.isdir(base):
        return "Pfad nicht gemountet"
    entries = []
    for name in sorted(os.listdir(base)):
        full = os.path.join(base, name)
        if not os.path.isdir(full):
            continue
        try:
            out = subprocess.run(
                ["du", "-sb", "--one-file-system", full],
                capture_output=True,
                text=True,
                timeout=1200,
            )
            size = int(out.stdout.split()[0]) if out.stdout.strip() else 0
            entries.append((name, size))
        except Exception:
            entries.append((name, -1))
    entries.sort(key=lambda x: x[1], reverse=True)
    lines = []
    for name, size in entries[:top_n]:
        if size < 0:
            lines.append(f"{name}: error")
        else:
            lines.append(f"{name}: {size/(1024**3):.1f} GB")
    return "\n".join(lines)


@mcp.tool()
def path_size(path: str) -> str:
    """du -sb auf /mnt/<path>."""
    full = os.path.join("/host_mnt", path.lstrip("/"))
    if not os.path.exists(full):
        return f"Pfad nicht gefunden: {full}"
    out = subprocess.run(["du", "-sb", full], capture_output=True, text=True, timeout=1200)
    if out.returncode != 0:
        return f"Fehler: {out.stderr.strip()}"
    size = int(out.stdout.split()[0])
    return f"{path}: {size/(1024**3):.2f} GB"


@mcp.tool()
def list_dir(path: str, top_n: int = 30) -> str:
    """Unterordner von /mnt/<path> mit Größe, sortiert."""
    full = os.path.join("/host_mnt", path.lstrip("/"))
    if not os.path.isdir(full):
        return f"Kein Verzeichnis: {full}"
    entries = []
    for name in sorted(os.listdir(full)):
        sub = os.path.join(full, name)
        if not os.path.isdir(sub):
            continue
        try:
            out = subprocess.run(["du", "-sb", sub], capture_output=True, text=True, timeout=1200)
            size = int(out.stdout.split()[0]) if out.stdout.strip() else 0
        except Exception:
            size = -1
        entries.append((name, size))
    entries.sort(key=lambda x: x[1], reverse=True)
    return "\n".join(
        f"{n}: {s/(1024**3):.1f} GB" if s >= 0 else f"{n}: error" for n, s in entries[:top_n]
    )
