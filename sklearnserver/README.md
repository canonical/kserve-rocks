## Testing

### Prerequisites

* docker
* Google Cloud CLI tools ([installation guide](https://cloud.google.com/sdk/docs/install))

### Instructions

From the [upstream usage example](https://kserve.github.io/website/master/modelserving/v1beta1/sklearn/v2/#deploy-the-model-with-rest-endpoint-through-inferenceservice/), this rock can be tested locally using:

Launch the server with:
```
# download the model locally
mkdir sample_model
gsutil cp -r gs://kfserving-examples/models/sklearn/1.0/model ./sample_model/

# mount the model into the container at runtime
docker run -p 8080:8080 -v $(pwd)/sample_model:/mnt/models sklearnserver:<version> --model_name test_model --model_dir=/mnt/models --http_port=8080

```

Test the server with:
```
cat <<EOF >> iris-input-v2.json
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

which should return the expected output described in the docs.  
