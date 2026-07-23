# Agent Guidelines

## Commits

Do not add a "Co-Authored-By: Claude" trailer (or any similar co-author line) to
commit messages.

## devenv

devenv does *not* use process-compose to start its processes. It uses the devenv native process manager. Do not look for process-compose logs.

### Starting and stopping devenv processes

Always use detached mode. Claude Code's bash tool has a 2-minute timeout; running
`devenv up` in the foreground will be killed, leaving orphaned processes.

```bash
# Check for already-running processes first
devenv processes status 2>/dev/null && devenv down

# Start in background, no TUI
devenv up -d --no-tui

# Wait for readiness probes to pass
devenv processes wait --timeout 60

# Check status / view logs
devenv processes status
devenv processes logs gitea

# Clean shutdown
devenv down
```

### Common pitfalls

- **Phantom process managers**: If `devenv up` loses its terminal, it leaves an
  orphaned manager. Running `devenv up` again starts a *second* instance. Always
  check `devenv processes status` before starting.
- **Port conflicts**: Orphaned processes hold ports; the next `devenv up` silently
  auto-increments (3000 → 3001). Use `--strict-ports` to fail loudly.
- **Stale PID files**: Services may leave PID files behind on unclean shutdown,
  blocking the next start. Add pre-cleanup tasks if needed.


### Prefix most commands with `devenv --quiet -O dotenv.enable:bool false shell --`

Klangk uses [devenv](https://devenv.sh) (Nix-based) for its dev environment. **Every command that touches the project toolchain must be run through the devenv shell**, including git. The toolchain — Python venv, Node, Dart/Flutter, podman, pre-commit hooks, etc. — only exists inside the shell.

```bash
devenv --quiet -O dotenv.enable:bool false shell -- git commit -m "..."
devenv --quiet -O dotenv.enable:bool false shell -- pytest
```

The flags: `--quiet` suppresses noisy devenv output; `-O dotenv.enable:bool false` prevents devenv from loading `.env` (which can interfere with test environments that set their own env vars via monkeypatch). `shell --` launches an ephemeral shell with the full environment, runs the command, and exits — this is the pattern agents should use for one-off commands. (`devenv shell` with no `--` drops into an interactive shell; not useful for non-interactive agents.) This applies to **all** commands: builds, tests, lint, `git`, `podman`, `flutter`, `gh`.

A long-running interactive `devenv up` (backend + proxy + workspace image build) is a human-facing workflow; agents generally don't run it. If you need the backend up for something, ask.
