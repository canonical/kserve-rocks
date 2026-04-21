## Testing

### Prerequisites

* an NVIDIA-compatible GPU (necessary only for testing the serving runtime, not for building the rock)

### Instructions

This rock can be tested locally by building it from source (on CPU) and running it as a serving runtime in the KServe charm (on GPU) following [the upstream usage example](https://kserve.github.io/website/docs/model-serving/predictive-inference/frameworks/huggingface/overview). In particular:

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
        && ./get_helm.sh
        $$ rm ./get_helm.sh
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

    juju deploy --trust --channel latest/edge knative-serving --config istio.gateway.namespace=kubeflow --config istio.gateway.name=test-gateway --config custom_images="{\"serving_runtimes__huggingfaceserver__multinode\": \"${your_image_registry_name}/huggingfaceserver:local\"}"
    juju wait-for application --query='status=="active"' knative-serving

    juju deploy --trust --channel latest/edge kserve-controller --config deployment-mode=knative
    juju wait-for application --query='status=="blocked"' kserve-controller

    juju integrate kserve-controller istio-pilot
    juju integrate kserve-controller knative-serving
    juju wait-for application --query='status=="active"' kserve-controller
    ```

1. Test a corresponding serving runtime is successfully initialized ([example](https://kserve.github.io/website/docs/model-serving/predictive-inference/frameworks/huggingface/fill-mask)):
    ```bash
    kubectl apply -f - <<EOF
    apiVersion: serving.kserve.io/v1beta1
    kind: InferenceService
    metadata:
      name: huggingface-bert
    spec:
      predictor:
        model:
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

    kubectl describe inferenceservices/huggingface-tiny-sentiment
    ```
