#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./setup.sh --air [options]

Prepare this checkout for the current portable/air MVP.

Options:
  --air              Prepare the portable/air profile.
  --root PATH        Profile root. Defaults to $XDG_DATA_HOME/zsper/profiles/air.
  --name NAME        Profile name. Defaults to air.
  --registry PATH    Profile registry. Defaults to $XDG_CONFIG_HOME/zsper/profiles.json.
  --no-venv          Skip creating .venv and run from the source checkout.
  -h, --help         Show this help.

Environment:
  ZSPER_AIR_ROOT          Default air profile root.
  ZSPER_AIR_NAME          Default air profile name.
  ZSPER_PROFILE_REGISTRY  Default profile registry path.
  ZSPER_VENV              Project virtual environment path.
  PYTHON                  Python executable to use.
USAGE
}

air=0
create_venv=1
air_name="${ZSPER_AIR_NAME:-air}"
air_root="${ZSPER_AIR_ROOT:-}"
registry="${ZSPER_PROFILE_REGISTRY:-}"
python_bin="${PYTHON:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --air)
      air=1
      shift
      ;;
    --root)
      if [[ $# -lt 2 ]]; then
        echo "--root requires a path" >&2
        usage >&2
        exit 2
      fi
      air_root="${2:-}"
      shift 2
      ;;
    --name)
      if [[ $# -lt 2 ]]; then
        echo "--name requires a value" >&2
        usage >&2
        exit 2
      fi
      air_name="${2:-}"
      shift 2
      ;;
    --registry)
      if [[ $# -lt 2 ]]; then
        echo "--registry requires a path" >&2
        usage >&2
        exit 2
      fi
      registry="${2:-}"
      shift 2
      ;;
    --no-venv)
      create_venv=0
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

if [[ "$air" -ne 1 ]]; then
  usage >&2
  exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

if [[ -z "$python_bin" ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    python_bin="python3.12"
  elif command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
  else
    python_bin="python"
  fi
fi

if ! "$python_bin" - <<'PY'
import sys

raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
then
  echo "Zsper requires Python 3.12 or newer." >&2
  exit 1
fi

if [[ -z "$registry" ]]; then
  registry="${XDG_CONFIG_HOME:-$HOME/.config}/zsper/profiles.json"
fi

if [[ -z "$air_root" ]]; then
  air_root="${XDG_DATA_HOME:-$HOME/.local/share}/zsper/profiles/$air_name"
fi

export ZSPER_PROFILE_REGISTRY="$registry"
export PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ "$create_venv" -eq 1 ]]; then
  venv_path="${ZSPER_VENV:-$repo_root/.venv}"
  if [[ ! -x "$venv_path/bin/python" ]]; then
    echo "Creating project virtual environment at $venv_path"
    "$python_bin" -m venv "$venv_path"
  fi
  python_bin="$venv_path/bin/python"
  echo "Installing Zsper and local RAG runtime dependencies"
  "$python_bin" -m pip install --upgrade \
    --editable "$repo_root" \
    "docling>=2.0" \
    "numpy>=2.0" \
    "rank-bm25>=0.2" \
    "sentence-transformers>=3.0"
  wrapper="$venv_path/bin/zsper"
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' 'set -euo pipefail'
    printf 'export ZSPER_PROFILE_REGISTRY="${ZSPER_PROFILE_REGISTRY:-%s}"\n' "$registry"
    printf 'export PYTHONPATH="%s/src${PYTHONPATH:+:$PYTHONPATH}"\n' "$repo_root"
    printf 'exec "%s/bin/python" -m zsper "$@"\n' "$venv_path"
  } > "$wrapper"
  chmod +x "$wrapper"
  zsper_cmd="$wrapper"
else
  zsper_cmd="PYTHONPATH=\"$repo_root/src\" \"$python_bin\" -m zsper"
fi

run_zsper() {
  "$python_bin" -m zsper "$@"
}

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
profile_json="$tmp_dir/profile.json"

echo "Preparing Zsper portable/air profile"
echo "Repo: $repo_root"
echo "Registry: $registry"
echo "Requested root: $air_root"

if run_zsper profile show --profile "$air_name" > "$profile_json" 2>/dev/null; then
  profile_ref="$air_name"
  echo "Using existing air profile: $air_name"
elif run_zsper profile show --profile "$air_root" > "$profile_json" 2>/dev/null; then
  profile_ref="$air_root"
  echo "Using existing air profile root: $air_root"
else
  run_zsper profile init --mode air-offline --root "$air_root" --name "$air_name"
  run_zsper profile show --profile "$air_name" > "$profile_json"
  profile_ref="$air_name"
fi

profile_mode="$(PROFILE_JSON="$profile_json" "$python_bin" - <<'PY'
import json
import os
from pathlib import Path

profile = json.loads(Path(os.environ["PROFILE_JSON"]).read_text(encoding="utf-8"))
print(profile["mode"])
PY
)"
if [[ "$profile_mode" != "air-offline" ]]; then
  echo "Profile $profile_ref is $profile_mode, not air-offline." >&2
  exit 1
fi

actual_root="$(PROFILE_JSON="$profile_json" "$python_bin" - <<'PY'
import json
import os
from pathlib import Path

profile = json.loads(Path(os.environ["PROFILE_JSON"]).read_text(encoding="utf-8"))
print(profile["root"])
PY
)"

note_path="$actual_root/brain/notes/air-readiness.md"
mkdir -p "$(dirname "$note_path")"
{
  printf '%s\n' '# Air Offline Readiness'
  printf '\n'
  printf '%s\n' 'This local note is created by ./setup.sh --air.'
  printf '%s\n' 'It verifies that the air profile can ingest and search offline content.'
  printf '%s\n' 'Use local files only while travelling; hosted model, search, and extraction calls stay blocked.'
} > "$note_path"

run_zsper profile doctor --profile "$profile_ref" >/dev/null

if run_zsper brain search --profile "$profile_ref" offline | grep -F "air-readiness.md" >/dev/null; then
  echo "Readiness note already indexed"
else
  run_zsper brain ingest --profile "$profile_ref" "$note_path" >/dev/null
fi

"$python_bin" -m zsper.rag.setup_index \
  --profile-json "$profile_json" \
  --source "$note_path" >/dev/null

if ! run_zsper brain search --profile "$profile_ref" offline | grep -F "air-readiness.md" >/dev/null; then
  echo "Offline search smoke check failed." >&2
  exit 1
fi

echo
echo "Air profile ready"
echo "Profile: $profile_ref"
echo "Root: $actual_root"
echo
echo "Try:"
echo "  $zsper_cmd brain ingest --profile $profile_ref /path/to/notes.md"
echo "  $zsper_cmd brain search --profile $profile_ref offline"
echo "  $zsper_cmd profile use $profile_ref"
