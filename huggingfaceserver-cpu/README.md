## Testing

### Prerequisites

* docker

### Instructions

From the [upstream usage examples](https://github.com/kserve/kserve/blob/v0.17.0/python/huggingfaceserver/README.md), this rock can be tested locally using a small HuggingFace model.

The example below uses `gpt2` (a small, publicly available text-generation model). The server will download the model from the HuggingFace Hub on first launch and cache it under `/tmp/huggingface` inside the container.

Launch the server with:
```bash
docker run -p 8080:8080 \
  --shm-size=4g \
  -e HF_HOME=/tmp/huggingface \
  -e VLLM_CPU_DISABLE_AVX512="true" \
  huggingfaceserver-cpu:<version> \
  --model_name=gpt2 \
  --model_id=gpt2 \
  --http_port=8080
```

Test the server with the OpenAI-compatible completions endpoint (used when vLLM is the backend):
```bash
curl -H "content-type: application/json" \
  localhost:8080/openai/v1/completions \
  -d '{"model": "gpt2", "prompt": "The capital of France is", "stream": false, "max_tokens": 20}'
```

The response should be similar to:
```json
{
  "id": "cmpl-...",
  "choices": [{"finish_reason": "length", "index": 0, "text": " Paris..."}],
  "model": "gpt2",
  "object": "text_completion"
}
```

Test with the OpenAI-compatible chat endpoint:
```bash
curl -H "content-type: application/json" \
  localhost:8080/openai/v1/chat/completions \
  -d '{"model": "gpt2", "messages": [{"role": "user", "content": "Hello!"}], "stream": false}'
```

> **Note:** This rock targets CPU-only deployments. Model loading may take longer than on GPU, and throughput will be lower. The `VLLM_CPU_DISABLE_AVX512=true` flag disables AVX-512 instructions if your CPU does not support them; remove it if your CPU does support AVX-512 for better performance.
