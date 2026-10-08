#!/usr/bin/env bash
# AX02: default is read-only dry-run. No implicit simulator launch.
set -euo pipefail
ablation_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ablation_repo="$(cd -- "$ablation_dir/../../.." && pwd)"
export PYTHONPATH="$ablation_repo/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$ablation_repo/.px4-python/bin:$PATH"
exec python3 "$ablation_dir/ax02/run.py" "$@"
