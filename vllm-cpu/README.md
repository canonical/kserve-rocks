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

### Building

> **Note:** Building this rock compiles vLLM's C++ CPU extensions from source.
> This takes approximately 30–60 minutes depending on the machine.

```bash
tox -e pack
tox -e export-to-docker
tox -e sanity
```
