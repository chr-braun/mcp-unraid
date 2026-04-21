"""MCP server for Unraid management.

Exposes system monitoring and Docker management tools via FastMCP
over HTTP (streamable transport) for Cursor and other MCP clients.
"""

import os
import pathlib
import importlib.util
import subprocess

from fastmcp import FastMCP

try:
    import docker
    _docker_client = docker.from_env()
except Exception as e:
    _docker_client = None
    print(f"[server] docker client init failed: {e}")

mcp = FastMCP("unraid-mcp")


# ---------------------------------------------------------------------------
# Basic system tools
# ---------------------------------------------------------------------------

@mcp.tool()
def ping() -> str:
    """Health check."""
    return "pong von Unraid"


@mcp.tool()
def uptime() -> str:
    """System uptime (days/hours/minutes)."""
    try:
        with open("/host/proc/uptime") as f:
            seconds = float(f.read().split()[0])
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"Uptime: {days}d {hours}h {minutes}m {secs}s"
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def cpu_load() -> str:
    """1/5/15 min load average."""
    try:
        with open("/host/proc/loadavg") as f:
            parts = f.read().split()
        return f"Load avg (1/5/15): {parts[0]} / {parts[1]} / {parts[2]}"
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def mem_info() -> str:
    """Memory usage (used/total/free/available in MB)."""
    try:
        info = {}
        with open("/host/proc/meminfo") as f:
            for line in f:
                key, val = line.split(":", 1)
                info[key.strip()] = int(val.strip().split()[0])
        total = info["MemTotal"] // 1024
        free = info["MemFree"] // 1024
        avail = info["MemAvailable"] // 1024
        used = total - avail
        return f"RAM: {used} MB benutzt / {total} MB total (frei: {free} MB, verfügbar: {avail} MB)"
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def temps() -> str:
    """Thermal sensor readings."""
    base = "/host/sys/class/thermal"
    out = []
    try:
        for name in sorted(os.listdir(base)):
            if not name.startswith("thermal_zone"):
                continue
            zone = os.path.join(base, name)
            try:
                with open(os.path.join(zone, "type")) as f:
                    t = f.read().strip()
                with open(os.path.join(zone, "temp")) as f:
                    c = int(f.read().strip()) / 1000.0
                out.append(f"{t}: {c:.1f}°C")
            except Exception:
                continue
        return "\n".join(out) if out else "Keine Sensoren gefunden."
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def network_info() -> str:
    """Network interfaces with RX/TX bytes."""
    try:
        with open("/host/proc/net/dev") as f:
            lines = f.readlines()[2:]
        out = []
        for line in lines:
            iface, rest = line.split(":", 1)
            fields = rest.split()
            rx_bytes = int(fields[0])
            tx_bytes = int(fields[8])
            iface = iface.strip()
            if iface in ("lo",):
                continue
            out.append(f"{iface}: RX {rx_bytes/1e6:.1f} MB | TX {tx_bytes/1e6:.1f} MB")
        return "\n".join(out)
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def top_processes(n: int = 10) -> str:
    """Top N processes by CPU usage (from inside container)."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%cpu"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = out.stdout.splitlines()
        return "\n".join(lines[: n + 1])
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def disk_usage() -> str:
    """Usage of all mounted disks under /host_mnt (Unraid array + user shares)."""
    base = "/host_mnt"
    out = []
    try:
        for name in sorted(os.listdir(base)):
            full = os.path.join(base, name)
            if not os.path.ismount(full) and not os.path.isdir(full):
                continue
            try:
                st = os.statvfs(full)
                total = st.f_blocks * st.f_frsize / (1024**3)
                free = st.f_bavail * st.f_frsize / (1024**3)
                used = total - free
                pct = (used / total * 100) if total else 0
                out.append(f"{name}: {used:.1f}/{total:.1f} GB ({pct:.0f}%)")
            except Exception:
                continue
        return "\n".join(out)
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def shares_list() -> str:
    """List all top-level shares under /mnt/user."""
    try:
        return "\n".join(sorted(os.listdir("/host_mnt/user")))
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def array_status() -> str:
    """Unraid array status from /host/proc/mdstat (if available)."""
    path = "/host/proc/mdstat"
    try:
        if not os.path.exists(path):
            return "mdstat nicht verfügbar"
        with open(path) as f:
            return f.read()
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def smart_status(device: str) -> str:
    """smartctl -a on /dev/<device>. Requires --privileged and /dev mount."""
    try:
        out = subprocess.run(
            ["smartctl", "-a", f"/dev/{device}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.stdout + (out.stderr if out.returncode != 0 else "")
    except FileNotFoundError:
        return "smartctl nicht installiert (smartmontools fehlt)."
    except Exception as e:
        return f"Fehler: {e}"


# ---------------------------------------------------------------------------
# Docker tools (via Docker SDK over /var/run/docker.sock)
# ---------------------------------------------------------------------------

def _need_docker() -> str | None:
    if _docker_client is None:
        return "Docker-Client nicht verfügbar (docker.sock Mount fehlt?)"
    return None


@mcp.tool()
def docker_ps() -> str:
    """List running containers."""
    if err := _need_docker():
        return err
    lines = []
    for c in _docker_client.containers.list(all=False):
        lines.append(f"{c.name} ({c.status}) - {c.image.tags[0] if c.image.tags else c.image.short_id}")
    return "\n".join(lines)


@mcp.tool()
def docker_inspect(name: str) -> str:
    """Basic info on a container: status, image, ports, mounts."""
    if err := _need_docker():
        return err
    try:
        c = _docker_client.containers.get(name)
        ports = c.attrs["NetworkSettings"].get("Ports") or {}
        mounts = [f"{m['Source']}:{m['Destination']} ({m['Mode']})" for m in c.attrs.get("Mounts", [])]
        return (
            f"Name: {c.name}\nStatus: {c.status}\nImage: {c.image.tags}\n"
            f"Ports: {ports}\nMounts:\n" + "\n".join(mounts)
        )
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def docker_start(name: str) -> str:
    """Start a container by name."""
    if err := _need_docker():
        return err
    try:
        _docker_client.containers.get(name).start()
        return f"Gestartet: {name}"
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def docker_stop(name: str) -> str:
    """Stop a container by name."""
    if err := _need_docker():
        return err
    try:
        _docker_client.containers.get(name).stop()
        return f"Gestoppt: {name}"
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def docker_restart(name: str) -> str:
    """Restart a container by name."""
    if err := _need_docker():
        return err
    try:
        _docker_client.containers.get(name).restart()
        return f"Restart ausgelöst: {name}"
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def docker_logs(name: str) -> str:
    """Last 50 log lines of container."""
    if err := _need_docker():
        return err
    try:
        c = _docker_client.containers.get(name)
        return c.logs(tail=50).decode(errors="replace")
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def docker_stats() -> str:
    """CPU and RAM usage per running container."""
    if err := _need_docker():
        return err
    lines = []
    for c in _docker_client.containers.list():
        try:
            s = c.stats(stream=False)
            cpu_total = s["cpu_stats"]["cpu_usage"]["total_usage"] - s["precpu_stats"]["cpu_usage"]["total_usage"]
            sys_total = s["cpu_stats"].get("system_cpu_usage", 0) - s["precpu_stats"].get("system_cpu_usage", 0)
            cpu_pct = (cpu_total / sys_total * len(s["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])) * 100) if sys_total > 0 else 0
            mem_used = s["memory_stats"].get("usage", 0) / (1024**2)
            mem_total = s["memory_stats"].get("limit", 1) / (1024**2)
            lines.append(f"{c.name}: CPU {cpu_pct:.1f}% | RAM {mem_used:.0f}/{mem_total:.0f} MB")
        except Exception:
            continue
    return "\n".join(lines)


@mcp.tool()
def docker_images() -> str:
    """List all Docker images with size."""
    if err := _need_docker():
        return err
    lines = []
    for img in _docker_client.images.list():
        tag = img.tags[0] if img.tags else "<none>"
        size_mb = img.attrs["Size"] / (1024**2)
        lines.append(f"{tag} — {size_mb:.0f} MB")
    return "\n".join(sorted(lines))


@mcp.tool()
def docker_prune_images(confirm: bool = False) -> str:
    """Remove dangling images. Requires confirm=True."""
    if err := _need_docker():
        return err
    if not confirm:
        return "Abgebrochen. Für Ausführung confirm=true setzen."
    try:
        res = _docker_client.images.prune(filters={"dangling": True})
        freed = res.get("SpaceReclaimed", 0) // (1024**2)
        return f"Entfernt: {res.get('ImagesDeleted')} | Platz frei: {freed} MB"
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def docker_remove_container(name: str, force: bool = False, confirm: bool = False) -> str:
    """Remove a container. Requires confirm=True."""
    if err := _need_docker():
        return err
    if not confirm:
        return "Abgebrochen. confirm=true nötig."
    try:
        _docker_client.containers.get(name).remove(force=force)
        return f"Entfernt: {name}"
    except Exception as e:
        return f"Fehler: {e}"


@mcp.tool()
def system_info() -> str:
    """Combined uptime + load + memory + thermals + disks + network."""
    blocks = [
        uptime(),
        cpu_load(),
        mem_info(),
        temps(),
        disk_usage(),
        network_info(),
    ]
    return "\n---\n".join(blocks)


# ---------------------------------------------------------------------------
# Self-management tools (scoped to /app for safety)
# ---------------------------------------------------------------------------

SCOPE = pathlib.Path("/app")
ALLOWED = [SCOPE / "server.py", SCOPE / "plugins"]


def _in_scope(path: str) -> pathlib.Path:
    full = (SCOPE / path.lstrip("/")).resolve()
    if not any(str(full).startswith(str(a.resolve())) for a in ALLOWED):
        raise ValueError(f"Pfad außerhalb Scope: {full}")
    return full


@mcp.tool()
def read_file(path: str) -> str:
    """Read a file under /app (server.py or plugins/**)."""
    return _in_scope(path).read_text()


@mcp.tool()
def write_file(path: str, content: str, confirm: bool = False) -> str:
    """Write a file under /app. Requires confirm=True. Restart container to load new plugin."""
    if not confirm:
        return "Abgebrochen. confirm=true nötig."
    f = _in_scope(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content)
    return f"OK: {f} ({len(content)} bytes). Bei Plugin-Änderung: docker restart mcp-unraid"


@mcp.tool()
def list_files(subdir: str = "") -> str:
    """List files under /app/<subdir>."""
    base = _in_scope(subdir) if subdir else SCOPE
    return "\n".join(sorted(str(p.relative_to(SCOPE)) for p in base.rglob("*") if p.is_file()))


# ---------------------------------------------------------------------------
# Plugin loader (plugins/*.py are auto-loaded at startup)
# ---------------------------------------------------------------------------

for pf in sorted((SCOPE / "plugins").glob("*.py")):
    spec = importlib.util.spec_from_file_location(pf.stem, pf)
    mod = importlib.util.module_from_spec(spec)
    mod.mcp = mcp
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        print(f"[server] plugin {pf.name} failed: {e}")


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8787)
