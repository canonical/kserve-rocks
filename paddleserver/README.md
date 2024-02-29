## Testing instructions

From the [upstream usage example](https://kserve.github.io/website/master/modelserving/v1beta1/paddle/), this rock can be tested locally using:

Launch the server with:
```
# download the model locally
mkdir sample_model
gsutil cp -r gs://kfserving-examples/models/paddle/resnet ./sample_model/

# mount the model into the container at runtime
docker run -p 8080:8080 -v $(pwd)/sample_model/resnet:/mnt/models paddleserver:0.11.2 --model_name test_model --model_dir=/mnt/models --http_port=8080

```

Test the server with:
```
wget https://kserve.github.io/website/master/modelserving/v1beta1/paddle/jay.json -O input.json

curl -v
  -H "Content-Type: application/json" \
  -d @./input.json \
  localhost:8080/v1/models/test_model:predict
```

which should return the expected output described in the docs.  
