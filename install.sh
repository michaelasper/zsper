#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: install.sh [options]

Install Zsper as a home-scoped CLI. It does not create a profile and does not
choose a default profile.

Options:
  --repo URL       Git repository to install. Defaults to GitHub origin.
  --ref REF        Git branch, tag, or commit to install. Defaults to main.
  --app-dir PATH   Managed checkout path. Defaults to $XDG_DATA_HOME/zsper/app.
  --venv PATH      Managed virtualenv path. Defaults to $XDG_DATA_HOME/zsper/venv.
  --bin-dir PATH   Directory for the zsper wrapper. Defaults to $HOME/.local/bin.
  --config-dir PATH
                   Zsper config dir. Defaults to $XDG_CONFIG_HOME/zsper.
  --dry-run        Print the install plan without writing files.
  -h, --help       Show this help.

After install, create and select a profile explicitly:
  zsper profile init --mode work --root "$HOME/.local/share/zsper/profiles/work"
  zsper profile use work
USAGE
}

repo_url="${ZSPER_INSTALL_REPO:-https://github.com/michaelasper/zsper.git}"
ref="${ZSPER_INSTALL_REF:-main}"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
app_dir="${ZSPER_APP_DIR:-$data_home/zsper/app}"
venv_dir="${ZSPER_VENV:-$data_home/zsper/venv}"
bin_dir="${ZSPER_BIN_DIR:-$HOME/.local/bin}"
config_dir="${ZSPER_CONFIG_DIR:-$config_home/zsper}"
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      if [[ $# -lt 2 ]]; then
        echo "--repo requires a URL" >&2
        exit 2
      fi
      repo_url="$2"
      shift 2
      ;;
    --ref)
      if [[ $# -lt 2 ]]; then
        echo "--ref requires a branch, tag, or commit" >&2
        exit 2
      fi
      ref="$2"
      shift 2
      ;;
    --app-dir)
      if [[ $# -lt 2 ]]; then
        echo "--app-dir requires a path" >&2
        exit 2
      fi
      app_dir="$2"
      shift 2
      ;;
    --venv)
      if [[ $# -lt 2 ]]; then
        echo "--venv requires a path" >&2
        exit 2
      fi
      venv_dir="$2"
      shift 2
      ;;
    --bin-dir)
      if [[ $# -lt 2 ]]; then
        echo "--bin-dir requires a path" >&2
        exit 2
      fi
      bin_dir="$2"
      shift 2
      ;;
    --config-dir)
      if [[ $# -lt 2 ]]; then
        echo "--config-dir requires a path" >&2
        exit 2
      fi
      config_dir="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

registry_path="${ZSPER_PROFILE_REGISTRY:-$config_dir/profiles.json}"
config_file="$config_dir/config.toml"
wrapper_path="$bin_dir/zsper"

if command -v python3.12 >/dev/null 2>&1; then
  python_bin="python3.12"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="python3"
else
  python_bin="python"
fi

run() {
  if [[ "$dry_run" -eq 1 ]]; then
    printf '+'
    for arg in "$@"; do
      printf ' %q' "$arg"
    done
    printf '\n'
  else
    "$@"
  fi
}

write_file() {
  local path="$1"
  local content="$2"
  if [[ "$dry_run" -eq 1 ]]; then
    printf '+ write %q\n' "$path"
  else
    mkdir -p "$(dirname "$path")"
    printf '%s' "$content" > "$path"
  fi
}

require_python() {
  if [[ "$dry_run" -eq 1 ]]; then
    printf '+ %q - <<PY\n' "$python_bin"
    return
  fi

  if ! "$python_bin" - <<'PY'
import sys

raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
  then
    echo "Zsper requires Python 3.12 or newer." >&2
    exit 1
  fi
}

checkout_repo() {
  if [[ -d "$app_dir/.git" ]]; then
    existing_url="$(git -C "$app_dir" config --get remote.origin.url || true)"
    if [[ "$existing_url" != "$repo_url" ]]; then
      echo "Existing checkout at $app_dir uses remote $existing_url, expected $repo_url" >&2
      exit 1
    fi
    run git -C "$app_dir" fetch origin "$ref" --tags
    run git -C "$app_dir" checkout "$ref"
    run git -C "$app_dir" pull --ff-only origin "$ref"
  elif [[ -e "$app_dir" ]]; then
    echo "Existing path at $app_dir is not a managed Zsper git checkout" >&2
    exit 1
  else
    run mkdir -p "$(dirname "$app_dir")"
    run git clone --branch "$ref" "$repo_url" "$app_dir"
  fi
}

write_wrapper() {
  wrapper_content="$(cat <<EOF
#!/usr/bin/env bash
set -euo pipefail
export ZSPER_CONFIG_DIR="\${ZSPER_CONFIG_DIR:-$config_dir}"
export ZSPER_PROFILE_REGISTRY="\${ZSPER_PROFILE_REGISTRY:-$registry_path}"
exec "$venv_dir/bin/zsper" "\$@"
EOF
)"
  write_file "$wrapper_path" "$wrapper_content"
  run chmod +x "$wrapper_path"
}

write_default_config_files() {
  run mkdir -p "$config_dir"
  run mkdir -p "$(dirname "$registry_path")"

  if [[ "$dry_run" -eq 1 ]]; then
    printf '+ create %q if missing\n' "$config_file"
    printf '+ create %q if missing\n' "$registry_path"
    return
  fi

  if [[ ! -f "$config_file" ]]; then
    cat > "$config_file" <<'EOF'
# Zsper user config
# Set a default after creating a profile:
#   zsper profile use NAME
EOF
  fi

  if [[ ! -f "$registry_path" ]]; then
    cat > "$registry_path" <<'EOF'
{
  "profiles": [],
  "schema_version": 1
}
EOF
  fi
}

print_next_steps() {
  if [[ "$dry_run" -eq 1 ]]; then
    heading="Zsper install plan"
  else
    heading="Zsper installed"
  fi

  cat <<EOF

$heading
App: $app_dir
Venv: $venv_dir
CLI: $wrapper_path
Config: $config_file
Registry: $registry_path
Wrapper env: ZSPER_CONFIG_DIR=$config_dir
Wrapper env: ZSPER_PROFILE_REGISTRY=$registry_path

No profile was created and no default profile was selected.

Next:
  zsper profile init --mode work --root "$data_home/zsper/profiles/work"
  zsper profile use work
  zsper profile doctor

Portable profile:
  zsper profile init --mode air-offline --root "$data_home/zsper/profiles/portable" --name portable
  zsper profile use portable

The air-offline mode is for portable, disconnected, or lower-compute contexts.
It blocks hosted model, search, extraction, and model-download calls until the
profile policy changes.
EOF

  case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *)
      cat <<EOF

Add Zsper to your shell path if needed:
  export PATH="$bin_dir:\$PATH"
EOF
      ;;
  esac
}

require_python
run mkdir -p "$bin_dir"
checkout_repo
run "$python_bin" -m venv "$venv_dir"
run "$venv_dir/bin/python" -m pip install --upgrade pip
run "$venv_dir/bin/python" -m pip install -e "$app_dir[api,database,rag]"
write_default_config_files
write_wrapper
print_next_steps
