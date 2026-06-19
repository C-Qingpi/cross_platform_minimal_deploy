#!/bin/bash
# Dev entrypoint — requires deploy.config mode=dev
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy_env.sh
source "$ROOT/deploy_env.sh"
deploy_env_load "$ROOT"
deploy_env_require_mode dev
exec /bin/bash "$ROOT/start.sh"
