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

    juju deploy --trust --channel latest/edge kserve-controller --config deployment-mode=knative --config custom_images="{\"serving_runtimes__huggingfaceserver\": \"${your_image_registry_name}/huggingfaceserver:local\", \"serving_runtimes__huggingfaceserver__multinode\": \"${your_image_registry_name}/huggingfaceserver:local\"}"
    juju wait-for application --query='status=="blocked"' kserve-controller

    juju integrate kserve-controller istio-pilot
    juju integrate kserve-controller knative-serving
    juju wait-for application --query='status=="active"' kserve-controller
    ```

1. Update the default runtime of `containerd` so that `InferenceServices` can access GPUs without explicitly defining `runtimeClassName: nvidia` in their spec:
    ```bash
    sudo sed -i 's/default_runtime_name = "runc"/default_runtime_name = "nvidia"/g' /etc/containerd/conf.d/99-nvidia.toml

    sudo systemctl restart snap.k8s.containerd
    ```

1. Test GPU access for pods:

    First, run:
    ```bash
    kubectl apply -f - <<EOF
    apiVersion: v1
    kind: Pod
    metadata:
      name: gpu-accessibility-test
    spec:
      restartPolicy: OnFailure
      containers:
        - name: cuda-vector-add
          image: "k8s.gcr.io/cuda-vector-add:v0.1"
          resources:
            limits:
              nvidia.com/gpu: 1
    EOF

    kubectl apply -f - <<EOF
    apiVersion: v1
    kind: Pod
    metadata:
      name: another-gpu-accessibility-test
    spec:
      restartPolicy: Never
      containers:
        - name: is-torch-seeing-cuda
          command: ["python"]
          args: ["-c", "from torch.cuda import is_available; print(is_available())"]
          image: ${your_image_registry_name}/huggingfaceserver:local
          resources:
            limits:
              nvidia.com/gpu: 1
    EOF
    ```

    After waiting for long enough, also run:
    ```bash
    kubectl logs pods/gpu-accessibility-test
    printf "\n- - - - - -\n\n"
    kubectl logs pods/another-gpu-accessibility-test
    ```

    And eventually assert the output is similar to:
    ```log
    [Vector addition of 50000 elements]
    Copy input data from the host memory to the CUDA device
    CUDA kernel launch with 196 blocks of 256 threads
    Copy output data from the CUDA device to the host memory
    Test PASSED
    Done

    - - - - - -

    True
    ```

1. Test a corresponding serving runtime is successfully initialized ([simplified example](https://kserve.github.io/website/docs/model-serving/predictive-inference/frameworks/huggingface/fill-mask)):
    ```bash
    kubectl apply -f - <<EOF
    apiVersion: serving.kserve.io/v1beta1
    kind: InferenceService
    metadata:
      name: huggingface-bert-served
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
              nvidia.com/gpu: "1"
    EOF

    printf "\n- - - - - -\n\n"
    kubectl get -o yaml deployment/huggingface-bert-served-predictor-00001-deployment | grep -- image:

    printf "\n- - - - - -\n\n"
    kubectl logs deployment/huggingface-bert-served-predictor-00001-deployment -c storage-initializer

    printf "\n- - - - - -\n\n"
    kubectl exec -it deployment/huggingface-bert-served-predictor-00001-deployment -c kserve-container -- pebble logs -n 100

    printf "\n- - - - - -\n\n"
    curl -v \
      "$(kubectl get inferenceservice huggingface-bert-served -o jsonpath='{.status.url}')/v1/models/bert:predict" \
      -H "content-type: application/json" \
      -d '{"instances": ["The capital of France is [MASK].", "The capital of [MASK] is paris."]}'
    ```

    Assert the output is similar to:
    ```log
    inferenceservice.serving.kserve.io/huggingface-bert created

    - - - - - -

            image: index.docker.io/mattiaatcanonical/huggingfaceserver@sha256:c486eb7ccc8d9060127da1bb2b3cfbc4b4d4e7bd879dded415ceedf76e0591ac
            image: gcr.io/knative-releases/knative.dev/serving/cmd/queue@sha256:c61042001b1f21c5d06bdee9b42b5e4524e4370e09d4f46347226f06db29ba0f

    - - - - - -

    2026-05-19T14:39:25.773Z [pebble] {"type":"security","datetime":"2026-05-19T14:39:25Z","level":"WARN","event":"sys_startup:584792","description":"Starting daemon","appid":"pebble"}
    2026-05-19T14:39:25.774Z [pebble] Started daemon.
    2026-05-19T14:39:25.777Z [pebble] POST /v1/services 1.540924ms 202 (http+unix)
    2026-05-19T14:39:25.779Z [pebble] Service "storage-initializer" starting: /storage-initializer/scripts/initializer-entrypoint [ hf://google-bert/bert-base-uncased /mnt/models ]
    2026-05-19T14:39:26.782Z [pebble] GET /v1/changes/1/wait 1.004546087s 200 (http+unix)
    2026-05-19T14:39:26.783Z [pebble] Started default services with change 1.
    2026-05-19T14:40:24.416Z [pebble] Service "storage-initializer" stopped unexpectedly with code 0
    2026-05-19T14:40:24.416Z [pebble] Service "storage-initializer" on-success action is "shutdown", triggering success shutdown
    2026-05-19T14:40:24.416Z [pebble] Server exiting! Reason: <nil>
    2026-05-19T14:40:24.416Z [pebble] {"type":"security","datetime":"2026-05-19T14:40:24Z","level":"WARN","event":"sys_shutdown:584792","description":"Shutting down daemon","appid":"pebble"}

    - - - - - -

    2026-05-19T14:40:40.340Z [huggingfaceserver] INFO 05-19 14:40:40 [importing.py:44] Triton is installed but 0 active driver(s) found (expected 1). Disabling Triton to prevent runtime errors.
    2026-05-19T14:40:40.340Z [huggingfaceserver] INFO 05-19 14:40:40 [importing.py:68] Triton not installed or not compatible; certain GPU-related functions will not be available.
    2026-05-19T14:40:42.175Z [huggingfaceserver] [2026-05-19 14:40:42] INFO kserve_storage.py:161: Copying contents of /mnt/models to local
    2026-05-19T14:40:42.175Z [huggingfaceserver] [2026-05-19 14:40:42] INFO kserve_storage.py:229: Successfully copied /mnt/models to None
    2026-05-19T14:40:42.175Z [huggingfaceserver] [2026-05-19 14:40:42] INFO kserve_storage.py:230: Model downloaded in 0.00038004199996066745 seconds.
    2026-05-19T14:40:42.187Z [huggingfaceserver] [2026-05-19 14:40:42] INFO utils.py:53: not a supported model by vLLM
    2026-05-19T14:40:42.188Z [huggingfaceserver] [2026-05-19 14:40:42] INFO kserve_storage.py:161: Copying contents of /mnt/models to local
    2026-05-19T14:40:42.188Z [huggingfaceserver] [2026-05-19 14:40:42] INFO kserve_storage.py:229: Successfully copied /mnt/models to None
    2026-05-19T14:40:42.188Z [huggingfaceserver] [2026-05-19 14:40:42] INFO kserve_storage.py:230: Model downloaded in 0.00013190199933887925 seconds.
    2026-05-19T14:40:42.189Z [huggingfaceserver] [2026-05-19 14:40:42] INFO utils.py:53: not a supported model by vLLM
    2026-05-19T14:40:42.189Z [huggingfaceserver] `torch_dtype` is deprecated! Use `dtype` instead!
    2026-05-19T14:40:42.189Z [huggingfaceserver] [2026-05-19 14:40:42] INFO __main__.py:299: Loading encoder model for task 'fill_mask' in torch.float32
    2026-05-19T14:40:42.358Z [huggingfaceserver] [2026-05-19 14:40:42] INFO encoder_model.py:184: Successfully loaded tokenizer
    2026-05-19T14:40:42.470Z [huggingfaceserver] Some weights of the model checkpoint at /mnt/models were not used when initializing BertForMaskedLM: ['bert.pooler.dense.bias', 'bert.pooler.dense.weight', 'cls.seq_relationship.bias', 'cls.seq_relationship.weight']
    2026-05-19T14:40:42.470Z [huggingfaceserver] - This IS expected if you are initializing BertForMaskedLM from the checkpoint of a model trained on another task or with another architecture (e.g. initializing a BertForSequenceClassification model from a BertForPreTraining model).
    2026-05-19T14:40:42.470Z [huggingfaceserver] - This IS NOT expected if you are initializing BertForMaskedLM from the checkpoint of a model that you expect to be exactly identical (initializing a BertForSequenceClassification model from a BertForSequenceClassification model).
    2026-05-19T14:40:42.476Z [huggingfaceserver] [2026-05-19 14:40:42] INFO encoder_model.py:207: Successfully loaded huggingface model from path /mnt/models
    2026-05-19T14:40:42.477Z [huggingfaceserver] [2026-05-19 14:40:42] INFO utils.py:53: not a supported model by vLLM
    2026-05-19T14:40:42.477Z [huggingfaceserver] [2026-05-19 14:40:42] INFO model_server.py:423: Registering model: bert
    2026-05-19T14:40:42.477Z [huggingfaceserver] [2026-05-19 14:40:42] INFO model_server.py:301: Setting max asyncio worker threads as 32
    2026-05-19T14:40:42.515Z [huggingfaceserver] [2026-05-19 14:40:42] INFO server.py:120: OpenAI endpoints registered
    2026-05-19T14:40:42.515Z [huggingfaceserver] [2026-05-19 14:40:42] INFO server.py:130: Time series endpoints not registered
    2026-05-19T14:40:42.515Z [huggingfaceserver] [2026-05-19 14:40:42] INFO server.py:181: Starting uvicorn with 1 workers
    2026-05-19T14:40:42.570Z [huggingfaceserver] [2026-05-19 14:40:42] INFO server.py:83: Started server process [14]
    2026-05-19T14:40:42.570Z [huggingfaceserver] [2026-05-19 14:40:42] INFO on.py:48: Waiting for application startup.
    2026-05-19T14:40:42.573Z [huggingfaceserver] [2026-05-19 14:40:42] INFO server.py:70: Starting gRPC server with 4 workers
    2026-05-19T14:40:42.573Z [huggingfaceserver] [2026-05-19 14:40:42] INFO server.py:71: Starting gRPC server on [::]:8081
    2026-05-19T14:40:42.573Z [huggingfaceserver] [2026-05-19 14:40:42] INFO on.py:62: Application startup complete.
    2026-05-19T14:40:42.573Z [huggingfaceserver] [2026-05-19 14:40:42] INFO server.py:215: Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)

    - - - - - -

    * Host huggingface-bert-served.default.10.64.140.43.nip.io:80 was resolved.
    * IPv6: (none)
    * IPv4: 10.64.140.43
    *   Trying 10.64.140.43:80...
    * Connected to huggingface-bert-served.default.10.64.140.43.nip.io (10.64.140.43) port 80
    > POST /v1/models/bert:predict HTTP/1.1
    > Host: huggingface-bert-served.default.10.64.140.43.nip.io
    > User-Agent: curl/8.5.0
    > Accept: */*
    > content-type: application/json
    > Content-Length: 86
    > 
    < HTTP/1.1 200 OK
    < content-length: 34
    < content-type: application/json
    < date: Tue, 19 May 2026 14:49:32 GMT
    < server: istio-envoy
    < x-envoy-upstream-service-time: 22622
    < 
    * Connection #0 to host huggingface-bert-served.default.10.64.140.43.nip.io left intact
    {"predictions":["paris","france"]}
    ```

    ***TODO: please update these logs every time rock changes are applied***
