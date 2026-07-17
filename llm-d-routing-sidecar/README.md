## llm-d-routing-sidecar

Canonical rock for the [llm-d](https://github.com/llm-d) routing sidecar
(`pd-sidecar`) v0.4.0, built from the upstream
[`Dockerfile.sidecar`](https://github.com/llm-d/llm-d-router/blob/v0.4.0/Dockerfile.sidecar).

The sidecar is a plain Go build (CGO disabled) that ships a single static
binary, installed at `/app/pd-sidecar`.

### Building

```bash
tox -e pack
tox -e export-to-docker
tox -e sanity
```

### Running

The sidecar is the rock's entrypoint service; pass `pd-sidecar` flags after the
image name:

```bash
docker run --rm llm-d-routing-sidecar:0.4.0 --help
```
