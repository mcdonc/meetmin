{ pkgs, lib, config, inputs, ... }:

{
  languages.python = {
    enable = true;
    uv = {
      enable = true;
      sync.enable = true;
    };
    venv = {
      enable = true;
      requirements = null;
    };
  };

  # Self-hosted Gitea instance for storing transcript repos.
  # Provides the `gitea` CLI in the shell and runs the server via `devenv up`.
  packages = [ pkgs.gitea ];

  # State (SQLite DB, config, repos) lives under .devenv/state/gitea.
  processes.gitea.exec = ''
    export GITEA_WORK_DIR="${config.devenv.state}/gitea"
    export GITEA_CUSTOM="$GITEA_WORK_DIR/custom"
    CONF="$GITEA_WORK_DIR/app.ini"
    mkdir -p "$GITEA_WORK_DIR/custom/conf"

    if [ ! -f "$CONF" ]; then
      cat > "$CONF" <<EOF
APP_NAME = Meetmin Gitea
RUN_MODE = prod

[server]
HTTP_ADDR = 127.0.0.1
HTTP_PORT = 3000
DOMAIN = localhost
ROOT_URL = http://localhost:3000/
# Built-in SSH server on 2222 (leaves the system sshd on 22 alone).
DISABLE_SSH = false
START_SSH_SERVER = true
# SSH login user (defaults to the OS user; pin to the conventional "git").
SSH_USER = git
SSH_DOMAIN = localhost
SSH_PORT = 2222
SSH_LISTEN_HOST = 127.0.0.1
SSH_LISTEN_PORT = 2222

[database]
DB_TYPE = sqlite3
PATH = $GITEA_WORK_DIR/gitea.db

[security]
INSTALL_LOCK = true

[service]
# Lock it down: no open sign-up, keep emails private.
DISABLE_REGISTRATION = true
DEFAULT_KEEP_EMAIL_PRIVATE = true

[repository]
# New repos are private unless explicitly made public.
DEFAULT_PRIVATE = private

[log]
MODE = console
LEVEL = info
EOF
    fi

    gitea migrate --config "$CONF"
    # Create a dev admin (idempotent — ignores "already exists").
    gitea admin user create --config "$CONF" \
      --username admin --password meetmin-dev --email admin@localhost \
      --admin --must-change-password=false 2>/dev/null || true

    exec gitea web --config "$CONF"
  '';
}
