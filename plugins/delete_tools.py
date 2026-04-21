"""Safe path deletion via ephemeral Alpine container.

Uses docker.sock to spawn a temporary privileged container that performs
the actual `rm -rf`. This avoids requiring an rw-mount of /mnt in the
main MCP container.
"""

import os
import docker

BLOCKED = ["user/appdata", "user/system", "user/domains", "user/isos", "user/data"]


@mcp.tool()
def delete_path(path: str, confirm: bool = False) -> str:
    """Delete /mnt/<path> via a throwaway Alpine container.

    Scope: user/**
    Blocked: appdata, system, domains, isos, data
    Requires confirm=True to actually delete.
    """
    rel = os.path.normpath(path.strip().lstrip("/"))
    if rel.startswith("..") or not rel.startswith("user/"):
        return f"Scope-Fehler: nur user/** erlaubt, bekam: {rel}"
    for b in BLOCKED:
        if rel == b or rel.startswith(b + "/"):
            return f"Blockiert (geschützt): {rel}"
    full = "/mnt/" + rel
    parent = os.path.dirname(full)
    child = os.path.basename(full)
    if not child:
        return "Ungültiger Pfad (leerer Name)"
    if not confirm:
        return (
            f"DRY RUN\nPfad: {full}\nParent-Mount: {parent}\nZiel: {child}\n"
            f"Aufruf mit confirm=true zum tatsächlichen Löschen."
        )
    client = docker.from_env()
    try:
        logs = client.containers.run(
            "alpine:latest",
            command=["sh", "-c", f"rm -rf '/target/{child}' && echo OK"],
            volumes={parent: {"bind": "/target", "mode": "rw"}},
            remove=True,
            stdout=True,
            stderr=True,
        )
        out = logs.decode() if isinstance(logs, bytes) else str(logs)
        return f"Gelöscht: {full}\n{out.strip()}"
    except docker.errors.ContainerError as e:
        return f"Container-Fehler: {e}"
    except Exception as e:
        return f"Fehler: {e}"
