#!/bin/bash
# Entry point for the vLLM Pebble service.
#
# Optionally enables Pebble log forwarding to Loki, then execs the vLLM
# OpenAI-compatible server. Forwarding is enabled only when LOKI_URL is set
# (for example, http://<host>:3100/loki/api/v1/push); otherwise it is skipped
# and vLLM starts normally.
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

# Hand off to vLLM. 'exec' keeps vLLM as the service's main process so Pebble
# signals (e.g. SIGTERM on stop) are delivered to it directly.
exec /opt/venv/bin/vllm serve "$@"
