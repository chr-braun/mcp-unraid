# mcp-unraid

> MCP server for **Unraid** system monitoring & Docker management — built with [FastMCP](https://gofastmcp.com) and the Python Docker SDK.
> Works with Cursor, Claude Desktop, and any other MCP-capable client.

📖 **Sprachen / Languages:** [🇩🇪 Deutsch](#-deutsch) · [🇬🇧 English](#-english)

---

## 🇩🇪 Deutsch

### Was ist das?

Ein MCP-Server, der in einem Docker-Container auf deinem Unraid läuft und dem KI-Client (Cursor, Claude, …) Werkzeuge gibt, um den Server zu inspizieren **und** Docker-Container zu verwalten — ohne dass du ins Web-UI oder die Shell wechseln musst.

### Funktionen

**System-Monitoring**
- `ping`, `uptime`, `cpu_load`, `mem_info`, `temps`, `network_info`, `top_processes`
- `disk_usage`, `shares_list`, `array_status`
- `smart_status <device>` (benötigt `--privileged` + `/dev` Mount)
- `system_info` — aggregierter Überblick

**Docker**
- `docker_ps`, `docker_inspect`, `docker_logs`, `docker_stats`, `docker_images`
- `docker_start`, `docker_stop`, `docker_restart`
- `docker_prune_images`, `docker_remove_container`

**Self-Management (Plugins ohne Rebuild)**
- `read_file`, `write_file`, `list_files` — Scope: `/app/server.py` + `/app/plugins/`
- Jede `plugins/*.py` wird beim Start automatisch geladen
- Neue Tools hinzufügen → Datei schreiben → Container neu starten → Tool ist live

**Share & Löschen (Plugins)**
- `share_sizes`, `path_size`, `list_dir` — exakte Größen via `du -sb`
- `delete_path` — löscht Pfade unter `/mnt/user/**` via **temporärem Alpine-Container** (kein rw-Mount in der Haupt-MCP nötig). Geschützte Pfade: `appdata`, `system`, `domains`, `isos`, `data`. Immer `confirm=True` erforderlich.

### Installation

#### 1. Auf Unraid einloggen (SSH empfohlen statt Web-Terminal)

```bash
ssh root@<deine-unraid-ip>
```

#### 2. Code klonen + Container bauen

```bash
APP=/mnt/user/appdata/mcp-unraid
git clone https://github.com/chr-braun/mcp-unraid "$APP"
cd "$APP"
docker build -t mcp-unraid:latest .
```

#### 3. Container starten

```bash
docker run -d \
  --name mcp-unraid \
  --restart unless-stopped \
  --privileged \
  -p 8789:8787 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /proc:/host/proc:ro \
  -v /sys:/host/sys:ro \
  -v /dev:/dev \
  -v /mnt:/host_mnt:ro \
  -v "$APP/server.py:/app/server.py" \
  -v "$APP/plugins:/app/plugins" \
  mcp-unraid:latest
```

> `server.py` und `plugins/` werden als Bind-Mounts eingebunden. Code-Änderungen landen sofort im Container; nur ein `docker restart mcp-unraid` reicht, um neue Tools zu laden (kein Rebuild nötig).

#### 4. Cursor konfigurieren

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "unraid-mcp": {
      "url": "http://<deine-unraid-ip>:8789/mcp"
    }
  }
}
```

In Cursor den MCP-Server aktivieren (Settings → MCP) — danach stehen alle Tools zur Verfügung.

### Eigene Tools hinzufügen

Lege eine Datei unter `plugins/` an, z. B. `plugins/meine_tools.py`:

```python
import os

@mcp.tool()
def hello(name: str = "Welt") -> str:
    """Sag Hallo."""
    return f"Hallo, {name}!"
```

Dann Container neu laden:

```bash
docker restart mcp-unraid
```

Alternativ komplett über den Agent:
1. Agent ruft `write_file(path="plugins/meine_tools.py", content="…", confirm=true)` auf
2. Agent ruft `docker_restart(name="mcp-unraid")` auf
3. Nach ~10 s sind die neuen Tools verfügbar

### Sicherheit

| Aspekt | Lösung |
|---|---|
| Haupt-MCP hat nur **ro** auf `/mnt` | Kein versehentliches Löschen/Schreiben |
| Löschen via temporärem Alpine-Container | Scope hart begrenzt auf `user/**`, kritische Shares blockiert |
| Docker-Kontrolle via `docker.sock` | Container ist `--privileged` nur wegen `smartctl`; kann später auf einen dedizierten Cap-Drop/Add ersetzt werden |
| `write_file`/`read_file` scoped | Nur `/app/server.py` und `/app/plugins/**` beschreibbar |
| Kein Auth-Layer | Setze den Port **nur im LAN** ein; bei öffentlicher Nutzung vorschalten: Reverse-Proxy mit Basic Auth/mTLS |

### Erkenntnisse aus der Entwicklung

- **Unraid-FUSE lässt keine `inotify`-Events durch.** Libraries wie `watchfiles` funktionieren auf `/mnt/user/...` nicht. Lösung: Polling (oder explizites `docker restart` beim Plugin-Update).
- **Self-Restart aus dem Container raus** (eigener Thread ruft `docker restart $selbst`) funktioniert technisch — aber Cursor verliert manchmal die Verbindung und reconnectet nicht automatisch. Manuelles `docker restart` durch den Agent-Tool-Call ist zuverlässiger.
- **Docker-in-Docker per `docker.sock`** ist viel mächtiger als es aussieht: Für das `delete_path`-Tool wurde bewusst **kein** rw-Mount auf `/mnt` gewählt, sondern ein kurzlebiger Alpine-Container pro Löschung. Das isoliert die Schreibrechte zeitlich.
- **FastMCP 3.x** emittiert bei Tool-Registrierung zwar `tools/list_changed`, aber viele Clients (u. a. Cursor) refreshen die Tool-Liste nur bei Reconnect. Deshalb: nach neuem Plugin → Container restart.
- **`privileged: true`** war notwendig, damit `smartctl` die Block-Devices über `/dev` ansprechen kann. Ohne das schlägt `SMART Status not supported: Incomplete response` fehl.
- **Tool-Argumente via `confirm=true`** als Sicherheitsnetz: destruktive Operationen (prune, delete, remove) verweigern ohne Confirm die Ausführung, so wird kein Unfall durch eine Halluzination des Agenten möglich.

### Beitragen

PRs willkommen. Plugin-Beispiele besonders gern — das Design ist explizit darauf ausgelegt, ohne Core-Änderung erweitert zu werden.

### Lizenz

MIT

---

## 🇬🇧 English

### What is this?

An MCP server that runs inside a Docker container on your Unraid host and gives an AI client (Cursor, Claude, etc.) tools to inspect the server **and** manage Docker containers — without you switching to the web UI or shell.

### Features

**System monitoring**
- `ping`, `uptime`, `cpu_load`, `mem_info`, `temps`, `network_info`, `top_processes`
- `disk_usage`, `shares_list`, `array_status`
- `smart_status <device>` (requires `--privileged` + `/dev` mount)
- `system_info` — aggregated overview

**Docker**
- `docker_ps`, `docker_inspect`, `docker_logs`, `docker_stats`, `docker_images`
- `docker_start`, `docker_stop`, `docker_restart`
- `docker_prune_images`, `docker_remove_container`

**Self-management (plugins without rebuild)**
- `read_file`, `write_file`, `list_files` — scope: `/app/server.py` + `/app/plugins/`
- Every `plugins/*.py` is auto-loaded on startup
- Add a new tool → write file → restart container → tool is live

**Shares & deletion (plugins)**
- `share_sizes`, `path_size`, `list_dir` — exact sizes via `du -sb`
- `delete_path` — deletes paths under `/mnt/user/**` via an **ephemeral Alpine container** (no rw-mount in the main MCP needed). Protected paths: `appdata`, `system`, `domains`, `isos`, `data`. `confirm=True` always required.

### Installation

#### 1. Log in to Unraid (SSH recommended over the web terminal)

```bash
ssh root@<your-unraid-ip>
```

#### 2. Clone the repo + build the container

```bash
APP=/mnt/user/appdata/mcp-unraid
git clone https://github.com/chr-braun/mcp-unraid "$APP"
cd "$APP"
docker build -t mcp-unraid:latest .
```

#### 3. Start the container

```bash
docker run -d \
  --name mcp-unraid \
  --restart unless-stopped \
  --privileged \
  -p 8789:8787 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /proc:/host/proc:ro \
  -v /sys:/host/sys:ro \
  -v /dev:/dev \
  -v /mnt:/host_mnt:ro \
  -v "$APP/server.py:/app/server.py" \
  -v "$APP/plugins:/app/plugins" \
  mcp-unraid:latest
```

> `server.py` and `plugins/` are bind-mounted. Code changes land in the container immediately; a single `docker restart mcp-unraid` is enough to pick up new tools (no rebuild needed).

#### 4. Configure Cursor

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "unraid-mcp": {
      "url": "http://<your-unraid-ip>:8789/mcp"
    }
  }
}
```

Enable the MCP server in Cursor (Settings → MCP) — all tools are then available.

### Adding your own tools

Create a file under `plugins/`, e.g. `plugins/my_tools.py`:

```python
import os

@mcp.tool()
def hello(name: str = "world") -> str:
    """Say hi."""
    return f"Hello, {name}!"
```

Then restart the container:

```bash
docker restart mcp-unraid
```

Or fully agent-driven:
1. Agent calls `write_file(path="plugins/my_tools.py", content="…", confirm=true)`
2. Agent calls `docker_restart(name="mcp-unraid")`
3. After ~10 s the new tools are available.

### Security

| Aspect | Design |
|---|---|
| Main MCP has **ro** on `/mnt` | No accidental deletes/writes |
| Deletion via throwaway Alpine container | Scope hard-limited to `user/**`, critical shares blocked |
| Docker control via `docker.sock` | Container runs `--privileged` only because of `smartctl`; could be narrowed with specific caps |
| `write_file`/`read_file` scoped | Only `/app/server.py` and `/app/plugins/**` are writable |
| No auth layer | Expose on **LAN only**; for public use put a reverse proxy with Basic Auth / mTLS in front |

### Lessons learned

- **Unraid FUSE does not propagate `inotify` events.** Libraries like `watchfiles` do not work on `/mnt/user/...`. Fix: polling (or explicit `docker restart` on plugin updates).
- **Self-restart from inside the container** (a thread calling `docker restart $self`) works technically — but Cursor occasionally drops the connection and does not auto-reconnect. Manual `docker_restart` via the agent tool call is more reliable.
- **Docker-in-Docker via `docker.sock`** is more powerful than it looks: for `delete_path` we deliberately chose **no** rw-mount on `/mnt` but a short-lived Alpine container per deletion. This isolates write permissions in time.
- **FastMCP 3.x** emits `tools/list_changed` on tool registration, but many clients (including Cursor) only refresh the tool list on reconnect. Hence: after adding a plugin → restart the container.
- **`privileged: true`** was needed so `smartctl` can talk to block devices via `/dev`. Without it `SMART Status not supported: Incomplete response` fails.
- **`confirm=true` arguments** as safety net: destructive ops (prune, delete, remove) refuse to run without explicit confirmation, so a single hallucination from the agent cannot cause damage.

### Contributing

PRs welcome. Plugin examples especially — the design is explicitly meant to be extended without touching the core.

### License

MIT
