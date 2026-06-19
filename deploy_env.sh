#!/usr/bin/env bash
# shellcheck shell=bash
# Load deploy.config for this checkout. DEPLOY_ROOT is always the checkout dir.

deploy_env_load() {
  local root="${1:?deploy root required}"
  root="$(cd "$root" && pwd)"
  local cfg="$root/deploy.config"

  if [[ ! -f "$cfg" ]]; then
    echo "ERROR: missing deploy.config in $root" >&2
    echo "  cp deploy.config.example deploy.config" >&2
    echo "  set mode=dev or mode=prod for this checkout" >&2
    return 1
  fi

  local mode="" backend_port="" frontend_port=""
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    [[ "$line" != *=* ]] && continue
    local key="${line%%=*}"
    local val="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%"${val##*[![:space:]]}"}"
    key="$(echo "$key" | tr '[:upper:]' '[:lower:]')"
    case "$key" in
      mode) mode="$val" ;;
      backend_port) backend_port="$val" ;;
      frontend_port) frontend_port="$val" ;;
    esac
  done < "$cfg"

  mode="$(echo "$mode" | tr '[:upper:]' '[:lower:]')"
  if [[ "$mode" != "dev" && "$mode" != "prod" ]]; then
    echo "ERROR: deploy.config mode must be dev or prod (got '${mode:-<empty>}')" >&2
    return 1
  fi

  DEPLOY_MODE="$mode"
  if [[ "$mode" == "dev" ]]; then
    DEPLOY_BACKEND_PORT="${backend_port:-8920}"
    DEPLOY_FRONTEND_PORT="${frontend_port:-5174}"
  else
    DEPLOY_BACKEND_PORT="${backend_port:-8921}"
    DEPLOY_FRONTEND_PORT="${frontend_port:-5175}"
  fi
  export ARION_DEPLOY_MODE=dev

  export DEPLOY_ROOT="$root"
  export BACKEND_PORT="$DEPLOY_BACKEND_PORT"
  export FRONTEND_PORT="$DEPLOY_FRONTEND_PORT"
  export DEPLOY_MODE
}
