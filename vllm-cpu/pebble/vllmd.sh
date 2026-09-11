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
# References:
#   https://ubuntu.com/docs/pebble/how-to/forward-logs-to-loki/
#   https://ubuntu.com/docs/pebble/reference/log-forwarding/

LOG_LAYER_FILE="/opt/pebble/log-layer.yaml"
RENDERED_LOG_LAYER="/tmp/rendered_log_layer.yaml"

# Escape sed replacement-special characters ('\', '/', '&') in LOKI_URL so the
# URL can be substituted into the template safely with '/' as the delimiter.
escaped_loki_url="$(printf '%s' "${LOKI_URL:-}" | sed -e 's/[\\/&]/\\&/g')"

if [ -n "${escaped_loki_url}" ]; then
    echo "Log-forwarding to Loki is enabled (LOKI_URL=${LOKI_URL})."
    sed -e "s/\$LOKI_URL/${escaped_loki_url}/g" \
        -e "s/\$HOSTNAME/${HOSTNAME}/g" \
        "${LOG_LAYER_FILE}" > "${RENDERED_LOG_LAYER}"
    if pebble add logging "${RENDERED_LOG_LAYER}"; then
        echo "Pebble logging layer added from ${RENDERED_LOG_LAYER}."
    else
        echo "WARNING: 'pebble add logging' failed; starting vLLM without log forwarding." >&2
    fi
else
    echo "Log-forwarding to Loki is disabled (LOKI_URL not set)."
fi

# Hand off to the real vLLM binary, preserved as 'vllm-original' when the
# /opt/venv/bin/vllm wrapper was installed. All arguments are passed through
# unchanged, so callers invoke this exactly like the upstream `vllm` command
# (e.g. `vllm serve --model ...`). 'exec' keeps vLLM as the service's main
# process so Pebble signals (e.g. SIGTERM on stop) are delivered to it directly.
exec /opt/venv/bin/vllm-original "$@"
