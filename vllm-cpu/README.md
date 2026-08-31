## vllm-cpu

Canonical rock for [vLLM](https://github.com/vllm-project/vllm) v0.19.0, CPU-only edition.  
Supports both `linux/amd64` (x86_64) and `linux/arm64` (aarch64).

### Testing

#### Prerequisites

* docker

#### Instructions

Launch the server with a small model (downloads from the HuggingFace Hub on first run):

```bash
docker run -p 8000:8000 \
  -e HF_HOME=/tmp/huggingface \
  vllm-cpu:0.19.0 \
  --model facebook/opt-125m
```

Test with the OpenAI-compatible completions endpoint:

```bash
curl -H "content-type: application/json" \
  localhost:8000/v1/completions \
  -d '{"model": "facebook/opt-125m", "prompt": "The capital of France is", "max_tokens": 20}'
```

### Log forwarding

The rock can forward the vLLM server logs to a [Grafana Loki](https://grafana.com/oss/loki/)
instance using [Pebble log forwarding](https://ubuntu.com/docs/pebble/how-to/forward-logs-to-loki/).
Forwarding is opt-in: set the `LOKI_URL` environment variable to the Loki push
endpoint and the container adds a Pebble `log-targets` layer at startup. When
`LOKI_URL` is unset, forwarding is disabled and the server starts normally.

```bash
docker run -p 8000:8000 \
  -e HF_HOME=/tmp/huggingface \
  -e LOKI_URL=http://my-loki:3100/loki/api/v1/push \
  vllm-cpu:0.19.0 \
  --model facebook/opt-125m
```

Forwarded logs carry Pebble's default `pebble_service` label plus `app=vllm`,
`edition=cpu`, `version=0.19.0`, and `pod=$HOSTNAME`.

### Building

> **Note:** Building this rock compiles vLLM's C++ CPU extensions from source.
> This takes approximately 30–60 minutes depending on the machine.

```bash
tox -e pack
tox -e export-to-docker
tox -e sanity
```
