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

1. Push the image to your own image registry on Docker Hub:
    ```bash
    sudo docker login
    read -p "Enter your Docker Hub image registry name: " your_image_registry_name
    sudo docker image tag huggingfaceserver:local ${your_image_registry_name}/huggingfaceserver:local
    sudo docker push ${your_image_registry_name}/huggingfaceserver:local
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

    juju deploy --trust --channel latest/edge kserve-controller --config deployment-mode=knative --config custom_images="{\"serving_runtimes__huggingfaceserver__multinode\": \"${your_image_registry_name}/huggingfaceserver:local\"}"
    juju wait-for application --query='status=="blocked"' kserve-controller

    juju integrate kserve-controller istio-pilot
    juju integrate kserve-controller knative-serving
    juju wait-for application --query='status=="active"' kserve-controller
    ```

1. Test a corresponding serving runtime is successfully initialized ([simplified example](https://github.com/canonical/kserve-rocks/pull/206)):
    ```bash
    kubectl apply -f - <<EOF
    apiVersion: serving.kserve.io/v1beta1
    kind: InferenceService
    metadata:
      name: hf-tiny-sentiment
    spec:
      predictor:
        model:
          modelFormat:
            name: huggingface
          args:
            - --backend=huggingface
            - --model_id=sshleifer/tiny-distilroberta-base
            - --task=fill_mask
          resources:
            requests:
              cpu: 100m
              memory: 600Mi
              nvidia.com/gpu: 1
            limits:
              cpu: "1"
              memory: 1Gi
              nvidia.com/gpu: 1
    EOF

    kubectl logs deployment/hf-tiny-sentiment-predictor-00001-deployment | head -n 21
    ```
    Assert the output is similar to:
    ```log
    Defaulted container "kserve-container" out of: kserve-container, queue-proxy
    INFO 04-21 16:26:54 [importing.py:44] Triton is installed but 0 active driver(s) found (expected 1). Disabling Triton to prevent runtime errors.
    INFO 04-21 16:26:54 [importing.py:68] Triton not installed or not compatible; certain GPU-related functions will not be available.
    W0421 16:26:54.899000 1 prod_venv/lib/python3.12/site-packages/torch/utils/cpp_extension.py:117] No CUDA runtime is found, using CUDA_HOME='/usr/local/cuda'
    `torch_dtype` is deprecated! Use `dtype` instead!
    [2026-04-21 16:26:56] INFO __main__.py:299: Loading encoder model for task 'fill_mask' in torch.float32
    [2026-04-21 16:26:59] INFO encoder_model.py:184: Successfully loaded tokenizer
    Some weights of the model checkpoint at sshleifer/tiny-distilroberta-base were not used when initializing RobertaForMaskedLM: ['roberta.pooler.dense.bias', 'roberta.pooler.dense.weight']
    - This IS expected if you are initializing RobertaForMaskedLM from the checkpoint of a model trained on another task or with another architecture (e.g. initializing a BertForSequenceClassification model from a BertForPreTraining model).
    - This IS NOT expected if you are initializing RobertaForMaskedLM from the checkpoint of a model that you expect to be exactly identical (initializing a BertForSequenceClassification model from a BertForSequenceClassification model).
    [2026-04-21 16:27:03] INFO encoder_model.py:207: Successfully loaded huggingface model from path sshleifer/tiny-distilroberta-base
    [2026-04-21 16:27:03] INFO model_server.py:423: Registering model: hf-tiny-sentiment
    [2026-04-21 16:27:03] INFO model_server.py:301: Setting max asyncio worker threads as 32
    [2026-04-21 16:27:03] INFO server.py:120: OpenAI endpoints registered
    [2026-04-21 16:27:03] INFO server.py:130: Time series endpoints not registered
    [2026-04-21 16:27:03] INFO server.py:181: Starting uvicorn with 1 workers
    [2026-04-21 16:27:03] INFO server.py:83: Started server process [1]
    [2026-04-21 16:27:03] INFO on.py:48: Waiting for application startup.
    [2026-04-21 16:27:03] INFO server.py:70: Starting gRPC server with 4 workers
    [2026-04-21 16:27:03] INFO server.py:71: Starting gRPC server on [::]:8081
    [2026-04-21 16:27:03] INFO on.py:62: Application startup complete.
    [2026-04-21 16:27:03] INFO server.py:215: Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
    ```
