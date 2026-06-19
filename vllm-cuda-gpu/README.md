## vllm

Canonical rock for [vLLM](https://github.com/vllm-project/vllm) v0.19.0, GPU/CUDA edition.
It packages the prebuilt vLLM CUDA wheel as an OpenAI-compatible inference server and
targets NVIDIA GPUs on `linux/amd64` (x86_64).

For a CPU-only build, see [`../vllm-cpu`](../vllm-cpu).

### Testing

#### Prerequisites

* an NVIDIA GPU with a compatible driver
* the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  (so that `docker run --gpus all` exposes the GPU to the container)
* docker

#### Instructions

Launch the server with a small model (downloads from the HuggingFace Hub on first run):

```bash
docker run --gpus all -p 8000:8000 \
  -e HF_HOME=/tmp/huggingface \
  vllm-cuda-gpu:0.19.0 \
  --model facebook/opt-125m
```

Test with the OpenAI-compatible completions endpoint:

```bash
curl -H "content-type: application/json" \
  localhost:8000/v1/completions \
  -d '{"model": "facebook/opt-125m", "prompt": "The capital of France is", "max_tokens": 20}'
```

### Building

> **Note:** Building this rock downloads multi-gigabyte CUDA wheels (PyTorch,
> NVIDIA runtime libraries, FlashInfer). The build itself runs on CPU and does not
> require a GPU; only running the server does.

```bash
tox -e pack
tox -e export-to-docker
tox -e sanity
```

`tox -e sanity` runs on any machine (it only checks that the expected files are present
in the rock).
