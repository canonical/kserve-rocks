## Testing

### Prerequisites

* docker
* Google Cloud CLI tools ([installation guide](https://cloud.google.com/sdk/docs/install))

### Instructions

From the [upstream usage example](https://kserve.github.io/website/master/modelserving/v1beta1/pmml/), this rock can be tested locally using:

Launch the server with:
```
# download the model locally
mkdir sample_model
gsutil cp -r gs://kfserving-examples/models/pmml ./sample_model/

# mount the model into the container at runtime
docker run -p 8080:8080 -v $(pwd)/sample_model/pmml:/mnt/models pmmlserver:<version> --model_name test_model --model_dir=/mnt/models --http_port=8080

```

Test the server with:
```
cat <<EOF >> input.json
{
  "instances": [
    [5.1, 3.5, 1.4, 0.2]
  ]
}
EOF

curl -v \
  -H "Content-Type: application/json" \
  -d @./input.json \
  localhost:8080/v1/models/test_model:predict
```

which should return the expected output described in the docs.  
