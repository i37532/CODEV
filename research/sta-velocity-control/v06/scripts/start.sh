#!/usr/bin/env bash
set -euo pipefail
script_dir="$(dirname "$(readlink -f "$0")")"
repo_dir="$(readlink -f "$script_dir/../../../..")"
export PYTHONPATH="$repo_dir/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$repo_dir/.px4-python/bin:$PATH"
exec python3 "$(dirname "$(readlink -f "$0")")/toolbox.py" start "$@"
