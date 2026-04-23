## Testing

### Prerequisites

* an NVIDIA-compatible GPU (necessary only for testing the serving runtime, not for building the rock)

### Instructions

This rock can be tested locally by building it from source (on CPU) and running it as a serving runtime in the KServe charm (on GPU) following [the upstream usage example](https://kserve.github.io/website/docs/model-serving/predictive-inference/frameworks/huggingface/fill-mask). In particular:

1. Set up Rockcraft:
    ```bash
    sudo snap install lxd
    lxd init --auto
    sudo snap install rockcraft --classic
    ```

1. Build your rock:
    ```bash
    cd huggingfaceserver
    rockcraft pack
    rock_filename=$(ls | grep -- .rock)
    ```

1. Set up Docker:
    ```bash
    sudo snap install docker
    ```

1. Export your rock to Docker's image registry:
    ```bash
    sudo rockcraft.skopeo --insecure-policy copy oci-archive:${rock_filename} docker-daemon:huggingfaceserver:local
    ```

1. Push the image to your own image registry on Docker Hub (doubling the tag with the "-gpu" prefix):
    ```bash
    sudo docker login
    read -p "Enter your Docker Hub image registry name: " your_image_registry_name
    sudo docker image tag huggingfaceserver:local ${your_image_registry_name}/huggingfaceserver:local
    sudo docker push ${your_image_registry_name}/huggingfaceserver:local
    sudo docker image tag ${your_image_registry_name}/huggingfaceserver:local ${your_image_registry_name}/huggingfaceserver:local-gpu
    sudo docker push ${your_image_registry_name}/huggingfaceserver:local-gpu
    ```

1. Uninstall Docker:
    ```bash
    sudo snap remove --purge docker
    sudo apt-get remove -y docker-ce docker-ce-cli containerd.io
    sudo rm -rf /run/containerd
    ```

1. Set up Canonical K8s:
    ```bash
    cd ../..
    git clone https://github.com/canonical/kserve-operators/
    cd kserve-operators
    sudo snap install concierge --classic
    sudo concierge prepare --trace
    cd ..
    ```

1. Set up [the NVIDIA GPU operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/getting-started.html):
    ```bash
    curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 \
        && chmod 700 get_helm.sh \
        && ./get_helm.sh \
        && rm ./get_helm.sh
    helm repo add nvidia https://helm.ngc.nvidia.com/nvidia \
        && helm repo update
    helm install --wait --generate-name \
        -n gpu-operator --create-namespace \
        nvidia/gpu-operator \
        --version=v26.3.1
    ```

1. Deploy KServe with the locally built rock:
    ```bash
    juju add-model kubeflow
    juju switch kubeflow

    juju deploy --trust --channel latest/edge istio-pilot --config default-gateway=test-gateway
    juju wait-for application --query='status=="active"' istio-pilot

    juju deploy --trust --channel latest/edge istio-gateway --config kind=ingress
    juju wait-for application --query='status=="blocked"' istio-gateway

    juju integrate istio-pilot istio-gateway
    juju wait-for application --query='status=="active"' istio-gateway

    juju deploy --trust --channel latest/edge knative-operator
    juju wait-for application --query='status=="active"' knative-operator

    juju deploy --trust --channel latest/edge knative-serving --config istio.gateway.namespace=kubeflow --config istio.gateway.name=test-gateway
    juju wait-for application --query='status=="active"' knative-serving

    juju deploy --trust --channel latest/edge kserve-controller --config deployment-mode=knative --config custom_images="{\"serving_runtimes__huggingfaceserver\": \"${your_image_registry_name}/huggingfaceserver:local\", \"serving_runtimes__huggingfaceserver__multinode\": \"${your_image_registry_name}/huggingfaceserver:local\", \"configmap__storageInitializer\": \"kserve/storage-initializer:v0.17.0\"}"
    juju wait-for application --query='status=="blocked"' kserve-controller

    juju integrate kserve-controller istio-pilot
    juju integrate kserve-controller knative-serving
    juju wait-for application --query='status=="active"' kserve-controller
    ```

1. Test a corresponding serving runtime is successfully initialized ([simplified example](https://kserve.github.io/website/docs/model-serving/predictive-inference/frameworks/huggingface/fill-mask)):
    ```bash
    kubectl apply -f - <<EOF
    apiVersion: serving.kserve.io/v1beta1
    kind: InferenceService
    metadata:
      name: huggingface-bert
    spec:
      predictor:
        model:
          imagePullPolicy: Always
          modelFormat:
            name: huggingface
          args:
            - --model_name=bert
          storageUri: "hf://google-bert/bert-base-uncased"
          resources:
            limits:
              cpu: "1"
              memory: 2Gi
              nvidia.com/gpu: "1"
            requests:
              cpu: "1"
              memory: 2Gi
              nvidia.com/gpu: "1"
    EOF

    printf "\n- - - - - -\n\n"
    kubectl get -o yaml deployment/huggingface-bert-predictor-00001-deployment | grep -- image:

    printf "\n- - - - - -\n\n"
    kubectl logs deployment/huggingface-bert-predictor-00001-deployment -c storage-initializer

    printf "\n- - - - - -\n\n"
    kubectl exec -it deployment/huggingface-bert-predictor-00001-deployment -c kserve-container -- pebble logs

    printf "\n- - - - - -\n\n"
    curl -v \
      "$(kubectl get inferenceservice huggingface-bert -o jsonpath='{.status.url}')/v1/models/bert:predict" \
      -H "content-type: application/json" \
      -d '{"instances": ["The capital of France is [MASK].", "The capital of [MASK] is paris."]}'

    ```
    Assert the output is similar to:
    ```log
    inferenceservice.serving.kserve.io/huggingface-bert created

    - - - - - -

            image: index.docker.io/mattiaatcanonical/huggingfaceserver@sha256:cc536bbf03de4d0e7b074e51f6b09885791f7422807c075d018df4512b2b22f4
            image: gcr.io/knative-releases/knative.dev/serving/cmd/queue@sha256:c61042001b1f21c5d06bdee9b42b5e4524e4370e09d4f46347226f06db29ba0f

    - - - - - -

    2026-04-22 16:53:20.337 1 storage.initializer INFO [initializer-entrypoint:<module>():16] Initializing, args: (src_uri, dest_path): [('hf://google-bert/bert-base-uncased', '/mnt/models')]
    2026-04-22 16:53:20.338 1 storage.initializer INFO [kserve_storage.py:download():161] Copying contents of hf://google-bert/bert-base-uncased to local
    2026-04-22 16:54:22.422 1 storage.initializer INFO [kserve_storage.py:download():229] Successfully copied hf://google-bert/bert-base-uncased to /mnt/models
    2026-04-22 16:54:22.423 1 storage.initializer INFO [kserve_storage.py:download():230] Model downloaded in 62.08553597900027 seconds.

    - - - - - -

    2026-04-22T16:58:39.280Z [huggingfaceserver] INFO 04-22 16:58:39 [importing.py:44] Triton is installed but 0 active driver(s) found (expected 1). Disabling Triton to prevent runtime errors.
    2026-04-22T16:58:39.280Z [huggingfaceserver] INFO 04-22 16:58:39 [importing.py:68] Triton not installed or not compatible; certain GPU-related functions will not be available.
    2026-04-22T16:58:40.857Z [huggingfaceserver] [2026-04-22 16:58:40] INFO kserve_storage.py:161: Copying contents of /mnt/models to local
    2026-04-22T16:58:40.857Z [huggingfaceserver] [2026-04-22 16:58:40] INFO kserve_storage.py:229: Successfully copied /mnt/models to None
    2026-04-22T16:58:40.857Z [huggingfaceserver] [2026-04-22 16:58:40] INFO kserve_storage.py:230: Model downloaded in 0.0004727460000140127 seconds.
    2026-04-22T16:58:40.869Z [huggingfaceserver] [2026-04-22 16:58:40] INFO utils.py:53: not a supported model by vLLM
    2026-04-22T16:58:40.870Z [huggingfaceserver] [2026-04-22 16:58:40] INFO kserve_storage.py:161: Copying contents of /mnt/models to local
    2026-04-22T16:58:40.870Z [huggingfaceserver] [2026-04-22 16:58:40] INFO kserve_storage.py:229: Successfully copied /mnt/models to None
    2026-04-22T16:58:40.870Z [huggingfaceserver] [2026-04-22 16:58:40] INFO kserve_storage.py:230: Model downloaded in 0.0001229839999723481 seconds.
    2026-04-22T16:58:40.871Z [huggingfaceserver] [2026-04-22 16:58:40] INFO utils.py:53: not a supported model by vLLM
    2026-04-22T16:58:40.871Z [huggingfaceserver] `torch_dtype` is deprecated! Use `dtype` instead!
    2026-04-22T16:58:40.871Z [huggingfaceserver] [2026-04-22 16:58:40] INFO __main__.py:299: Loading encoder model for task 'fill_mask' in torch.float32
    2026-04-22T16:58:41.012Z [huggingfaceserver] [2026-04-22 16:58:41] INFO encoder_model.py:184: Successfully loaded tokenizer
    2026-04-22T16:58:41.104Z [huggingfaceserver] Some weights of the model checkpoint at /mnt/models were not used when initializing BertForMaskedLM: ['bert.pooler.dense.bias', 'bert.pooler.dense.weight', 'cls.seq_relationship.bias', 'cls.seq_relationship.weight']
    2026-04-22T16:58:41.104Z [huggingfaceserver] - This IS expected if you are initializing BertForMaskedLM from the checkpoint of a model trained on another task or with another architecture (e.g. initializing a BertForSequenceClassification model from a BertForPreTraining model).
    2026-04-22T16:58:41.104Z [huggingfaceserver] - This IS NOT expected if you are initializing BertForMaskedLM from the checkpoint of a model that you expect to be exactly identical (initializing a BertForSequenceClassification model from a BertForSequenceClassification model).
    2026-04-22T16:58:41.109Z [huggingfaceserver] [2026-04-22 16:58:41] INFO encoder_model.py:207: Successfully loaded huggingface model from path /mnt/models
    2026-04-22T16:58:41.110Z [huggingfaceserver] [2026-04-22 16:58:41] INFO utils.py:53: not a supported model by vLLM
    2026-04-22T16:58:41.110Z [huggingfaceserver] [2026-04-22 16:58:41] INFO model_server.py:423: Registering model: bert
    2026-04-22T16:58:41.111Z [huggingfaceserver] [2026-04-22 16:58:41] INFO model_server.py:301: Setting max asyncio worker threads as 32
    2026-04-22T16:58:41.145Z [huggingfaceserver] [2026-04-22 16:58:41] INFO server.py:120: OpenAI endpoints registered
    2026-04-22T16:58:41.145Z [huggingfaceserver] [2026-04-22 16:58:41] INFO server.py:130: Time series endpoints not registered
    2026-04-22T16:58:41.145Z [huggingfaceserver] [2026-04-22 16:58:41] INFO server.py:181: Starting uvicorn with 1 workers
    2026-04-22T16:58:41.200Z [huggingfaceserver] [2026-04-22 16:58:41] INFO server.py:83: Started server process [14]
    2026-04-22T16:58:41.200Z [huggingfaceserver] [2026-04-22 16:58:41] INFO on.py:48: Waiting for application startup.
    2026-04-22T16:58:41.204Z [huggingfaceserver] [2026-04-22 16:58:41] INFO server.py:70: Starting gRPC server with 4 workers
    2026-04-22T16:58:41.204Z [huggingfaceserver] [2026-04-22 16:58:41] INFO server.py:71: Starting gRPC server on [::]:8081
    2026-04-22T16:58:41.204Z [huggingfaceserver] [2026-04-22 16:58:41] INFO on.py:62: Application startup complete.
    2026-04-22T16:58:41.204Z [huggingfaceserver] [2026-04-22 16:58:41] INFO server.py:215: Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)

    - - - - - -

    * Host huggingface-bert.default.10.64.140.43.nip.io:80 was resolved.
    * IPv6: (none)
    * IPv4: 10.64.140.43
    *   Trying 10.64.140.43:80...
    * Connected to huggingface-bert.default.10.64.140.43.nip.io (10.64.140.43) port 80
    > POST /v1/models/bert:predict HTTP/1.1
    > Host: huggingface-bert.default.10.64.140.43.nip.io
    > User-Agent: curl/8.5.0
    > Accept: */*
    > content-type: application/json
    > Content-Length: 86
    > 
    < HTTP/1.1 200 OK
    < content-length: 34
    < content-type: application/json
    < date: Wed, 22 Apr 2026 17:02:02 GMT
    < server: istio-envoy
    < x-envoy-upstream-service-time: 28237
    < 
    * Connection #0 to host huggingface-bert.default.10.64.140.43.nip.io left intact
    {"predictions":["paris","france"]}
    ```
