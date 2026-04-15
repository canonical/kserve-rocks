## Testing

### Prerequisites

* rockcraft
* docker
* gsutil ([installation guide](https://docs.cloud.google.com/storage/docs/gsutil_install#deb))

### Instructions

This rock can be tested locally by building it from source and running it following the [upstream usage example](https://kserve.github.io/website/docs/model-serving/predictive-inference/frameworks/lightgbm):

1. Build your rock:
    ```bash
    cd lgbserver
    rockcraft pack
    rock_filename=$(ls | grep -- .rock)
    ```

1. Export your rock to Docker's image registry:
    ```bash
    sudo rockcraft.skopeo --insecure-policy copy oci-archive:${rock_filename} docker-daemon:lgbserver:local
    ```

1. Launch the server:
    ```bash
    # download the model locally
    gsutil cp -r gs://kfserving-examples/models/lightgbm/iris ./sample_model/

    # mount the model into the container at runtime
    sudo docker run -p 8080:8080 -v ./sample_model:/mnt/models lgbserver:local --model_name test_model --model_dir=/mnt/models --http_port=8080
    ```

1. Test the server by calling its inference endpoint:
    ```bash
    cat > iris-input-v2.json << EOF
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

    curl -H "Content-Type: application/json" -d @./iris-input-v2.json localhost:8080/v2/models/test_model/infer
    ```

    which should return an output similar to:
    ```log
    {"model_name":"test_model","model_version":null,"id":"dc12cddd-b914-4b1f-a5fb-425e624a3f5b","parameters":null,"outputs":[{"name":"output-0","shape":[2,3],"datatype":"FP64","parameters":null,"data":[0.00028762259763255566,0.9763481320224064,0.023364245379961103,0.0005625431624697456,0.9988642605470336,0.0005731962904966214]}]}
    ```
