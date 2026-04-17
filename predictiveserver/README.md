## Testing

### Prerequisites

* docker
* Google Cloud CLI tools ([installation guide](https://cloud.google.com/sdk/docs/install))

### Instructions

From the [upstream usage examples](https://kserve.github.io/website/latest/modelserving/v1beta1/sklearn/v2/), this rock can be tested locally using a sklearn model with predictiveserver:

Launch the server with:
```bash
# download a sample sklearn model locally
mkdir -p sample_model
gsutil cp -r gs://kfserving-examples/models/sklearn/1.0/model ./sample_model/

# mount the model into the container at runtime
docker run -p 8080:8080 -v $(pwd)/sample_model:/mnt/models \
  predictiveserver:<version> \
  --model_name test_model \
  --model_dir=/mnt/models/model \
  --http_port=8080
```

Test the server with:
```bash
cat <<EOF > iris-input-v2.json
{
  "inputs": [
    {
      "name": "input-0",
      "shape": [2, 4],
      "datatype": "FP32",
      "data": [
        [6.8, 2.8, 4.8, 1.4],
        [6.0, 3.4, 4.5, 1.6]
      ]
    }
  ]
}
EOF

curl -v \
  -H "Content-Type: application/json" \
  -d @./iris-input-v2.json \
  localhost:8080/v2/models/test_model/infer
```

The response should include an inference result similar to:

```json
{"model_name":"test_model","outputs":[...]}
```
