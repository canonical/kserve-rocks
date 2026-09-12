#!/bin/bash
# Wrapper for the vLLM CLI, installed as /opt/venv/bin/vllm (the real binary is
# preserved as /opt/venv/bin/vllm-original). Because /opt/venv/bin is first on
# PATH, every `vllm ...` invocation - the Pebble service, the upstream image
# entrypoint (`vllm serve`), and KServe manifests - runs through here first.
#
# Optionally enables Pebble log forwarding to Loki, then execs the real vLLM
# binary with all arguments passed through unchanged. Forwarding is enabled
# only when LOKI_URL is set (for example, http://<host>:3100/loki/api/v1/push);
# otherwise it is skipped and vLLM starts normally.
#
# Pebble can only forward logs for services it supervises, so this script has
# to cope with two very different invocations:
#
#   1. As the Pebble service command (the rock entrypoint,
#      `pebble enter --args vllm`). A Pebble daemon is already running, so the
#      rendered log layer is added to it and the real binary is exec'd.
#
#   2. As the container's main process, when the image entrypoint is overridden
#      and vLLM is started directly. KServe does exactly this: it sets
#      `command: [vllm, serve, /mnt/models, ...]`, which replaces the rock
#      entrypoint. There is no Pebble daemon, so `pebble add` would fail with
#      "cannot communicate with server ... .pebble.socket not found" and logs
#      would never be forwarded. In that case this script bootstraps Pebble by
#      re-exec'ing through `pebble enter`, which starts the daemon and then runs
#      the vllm service (re-entering this script via case 1).
#
# References:
#   https://ubuntu.com/docs/pebble/how-to/forward-logs-to-loki/
#   https://ubuntu.com/docs/pebble/reference/log-forwarding/

PEBBLE_DIR="${PEBBLE:-/var/lib/pebble/default}"
PEBBLE_SOCKET="${PEBBLE_DIR}/.pebble.socket"
LOG_LAYER_FILE="/opt/pebble/log-layer.yaml"
# The layer is rendered under /tmp rather than into ${PEBBLE_DIR}/layers because
# the rock runs as a non-root user that cannot write to the Pebble directory.
RENDERED_LOG_LAYER="/tmp/rendered_log_layer.yaml"
REAL_VLLM="/opt/venv/bin/vllm-original"

# Render the log-layer template, substituting the Loki URL and hostname.
# Escapes sed replacement-special characters ('\', '/', '&') in LOKI_URL so the
# URL can be substituted into the template safely with '/' as the delimiter.
render_log_layer() {
    local escaped_loki_url
    escaped_loki_url="$(printf '%s' "${LOKI_URL}" | sed -e 's/[\\/&]/\\&/g')"
    sed -e "s/\$LOKI_URL/${escaped_loki_url}/g" \
        -e "s/\$HOSTNAME/${HOSTNAME}/g" \
        "${LOG_LAYER_FILE}" > "${RENDERED_LOG_LAYER}"
}

# Without a Loki endpoint there is nothing to set up; start vLLM directly.
# 'exec' keeps vLLM as the main process so signals (e.g. SIGTERM on stop) are
# delivered to it directly.
if [ -z "${LOKI_URL:-}" ]; then
    echo "Log-forwarding to Loki is disabled (LOKI_URL not set)."
    exec "${REAL_VLLM}" "$@"
fi

# Case 1: a Pebble daemon is already running, so attach the logging layer to it.
if [ -S "${PEBBLE_SOCKET}" ]; then
    echo "Log-forwarding to Loki is enabled (LOKI_URL=${LOKI_URL})."
    render_log_layer
    # '--combine' makes this idempotent: a plain 'pebble add' fails with HTTP
    # 400 if the 'logging' layer was already added (e.g. on service restart).
    if pebble add --combine logging "${RENDERED_LOG_LAYER}"; then
        echo "Pebble logging layer added from ${RENDERED_LOG_LAYER}."
    else
        echo "WARNING: 'pebble add' failed; starting vLLM without log forwarding." >&2
    fi
    exec "${REAL_VLLM}" "$@"
fi

# Guard against re-exec loops: if Pebble was already bootstrapped but there is
# still no socket, give up on forwarding rather than fork-bombing the container.
if [ "${VLLM_PEBBLE_BOOTSTRAP:-}" = "1" ]; then
    echo "WARNING: Pebble daemon did not start; running vLLM without log forwarding." >&2
    exec "${REAL_VLLM}" "$@"
fi

# Case 2: no Pebble daemon (the entrypoint was overridden). Start one and let it
# supervise vLLM so that it can forward the service's logs.
echo "Log-forwarding to Loki is enabled (LOKI_URL=${LOKI_URL}); starting Pebble to supervise vLLM."
export VLLM_PEBBLE_BOOTSTRAP=1

# 'pebble enter --args vllm' substitutes the arguments below into the service's
# overridable (bracketed) arguments, and the service command already ends with a
# fixed 'serve'. Drop a leading 'serve' from callers such as KServe
# (`vllm serve /mnt/models ...`) so it is not passed to vLLM twice.
[ "${1:-}" = "serve" ] && shift

# '--verbose' streams the supervised service's output to this process's stdout,
# preserving the container logs a directly-exec'd vLLM would have produced.
exec pebble enter --verbose --args vllm "$@"