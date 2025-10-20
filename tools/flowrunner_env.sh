#!/usr/bin/env bash

# Flow Runner integration helper.
# Source this script to export FLOW_RUNNER_PYTHONPATH based on a local checkout.

_restore_mode=none
if [ -n "${BASH_VERSION-}" ]; then
  _prev_opts="$(set +o)"
  _restore_mode=bash
  set -e
  set -u
  set -o pipefail
elif [ -n "${ZSH_VERSION-}" ]; then
  _prev_errexit="$(set -o | awk '/errexit/{print $2}')"
  _prev_nounset="$(set -o | awk '/nounset/{print $2}')"
  _prev_pipefail="$(set -o | awk '/pipefail/{print $2}')"
  set -o errexit
  set -o nounset
  set -o pipefail >/dev/null 2>&1 || true
  _restore_mode=zsh
fi

if [ -n "${ZSH_VERSION-}" ]; then
  if [[ "${ZSH_EVAL_CONTEXT:-}" != *:file* ]]; then
    echo "Please source this script: source tools/flowrunner_env.sh" >&2
    if [ "${_restore_mode}" = "bash" ]; then eval "${_prev_opts}"; fi
    if [ "${_restore_mode}" = "zsh" ]; then
      if [ "${_prev_errexit}" = "off" ]; then set +o errexit; fi
      if [ "${_prev_nounset}" = "off" ]; then set +o nounset; fi
      if [ "${_prev_pipefail}" = "off" ]; then set +o pipefail 2>/dev/null || true; fi
    fi
    exit 1
  fi
  script_source="${(%):-%x}"
else
  if [[ "${BASH_SOURCE[0]-}" == "${0}" ]]; then
    echo "Please source this script: source tools/flowrunner_env.sh" >&2
    if [ "${_restore_mode}" = "bash" ]; then eval "${_prev_opts}"; fi
    if [ "${_restore_mode}" = "zsh" ]; then
      if [ "${_prev_errexit}" = "off" ]; then set +o errexit; fi
      if [ "${_prev_nounset}" = "off" ]; then set +o nounset; fi
      if [ "${_prev_pipefail}" = "off" ]; then set +o pipefail 2>/dev/null || true; fi
    fi
    exit 1
  fi
  script_source="${BASH_SOURCE[0]-$0}"
fi

ROOT_DIR="$(cd "$(dirname "${script_source}")/.." && pwd)"
FLOW_RUNNER_DIR="${FLOW_RUNNER_DIR:-"${ROOT_DIR}/flow-runner"}"

if [[ ! -d "${FLOW_RUNNER_DIR}/packages/flowrunner/src" ]] || [[ ! -d "${FLOW_RUNNER_DIR}/packages/mcprouter/src" ]]; then
  echo "Flow Runner sources not found under ${FLOW_RUNNER_DIR}. Clone and install flow-runner first." >&2
  _status=1
else
  export FLOW_RUNNER_PYTHONPATH="${FLOW_RUNNER_DIR}/packages/flowrunner/src:${FLOW_RUNNER_DIR}/packages/mcprouter/src"
  echo "FLOW_RUNNER_PYTHONPATH set to ${FLOW_RUNNER_PYTHONPATH}"
  _status=0
fi

if [ "${_restore_mode}" = "bash" ]; then
  eval "${_prev_opts}"
elif [ "${_restore_mode}" = "zsh" ]; then
  if [ "${_prev_errexit}" = "off" ]; then set +o errexit; fi
  if [ "${_prev_nounset}" = "off" ]; then set +o nounset; fi
  if [ "${_prev_pipefail}" = "off" ]; then set +o pipefail 2>/dev/null || true; fi
fi

unset _restore_mode _prev_opts _prev_errexit _prev_nounset _prev_pipefail script_source ROOT_DIR FLOW_RUNNER_DIR

return "${_status}"
