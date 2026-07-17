## llm-d-inference-scheduler

Canonical rock for the [llm-d](https://github.com/llm-d) inference scheduler
("Endpoint Picker", `epp`) v0.4.0, built from the upstream
[`Dockerfile.epp`](https://github.com/llm-d/llm-d-router/blob/v0.4.0/Dockerfile.epp).

The image is a CGO build that links `libpython3.12` and a static HuggingFace
tokenizers library, and ships a Python 3.12 runtime with the chat-completions
dependencies (excluding `torch`) installed.

### Exposed ports

| Port | Purpose                  |
| ---- | ------------------------ |
| 9002 | gRPC                     |
| 9003 | health                   |
| 9090 | metrics                  |
| 5557 | KV-Events ZMQ SUB socket |

### Building

> **Note:** Building this rock compiles the `epp` binary with CGO and downloads
> the tokenizers static library and Python dependencies. This can take a while.

```bash
tox -e pack
tox -e export-to-docker
tox -e sanity
```

### Running

The scheduler is the rock's entrypoint service; pass `epp` flags after the image
name:

```bash
docker run --rm llm-d-inference-scheduler:0.4.0 --help
```
