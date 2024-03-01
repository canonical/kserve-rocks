# kserve's server rocks

## Summary of upstream's dockerfiles

The kserve server images are a collection of different inference server runtimes, such as sklearn or paddle.  This repo includes rocks for the upstream server images located [here](https://github.com/kserve/kserve/tree/master/python).  These server images all have the following common traits:

* they are implemented as python packages and use [poetry](https://python-poetry.org/) to manage their dependencies
* each server installs its own server-specific package (ex: [sklearn](https://github.com/kserve/kserve/tree/master/python/sklearnserver))
* they all install a common [kserve](https://github.com/kserve/kserve/tree/master/python/kserve) package

The Dockerfile for each of these images takes advantage of how each server is defined as a poetry package, using `poetry install` in the Dockerfile directly.

## Implementation details of the ROCKs in this repo

The ROCKs for the kserve servers require some atypical workarounds, mostly due to the upstream project using poetry to install its dependencies.  These are documented here in detail, and briefly noted in the rockcraft.yaml files in this repository.

### Installing Python/pip via overlay-packages

We use overlay-packages to get a python3.10 that we can `pip install` packages into.  For some reason if we add python3.10 as a build-package, the python packages we `pip install`/`poetry install` are not added to this python but to a different one.  This problem will first show up when calling `pip install poetry; poetry config ...`, where `pip install poetry` will work fine buy `poetry config ...` will return with command not found.  

As a workaround, we use python/pip from the `overlay-packages`, which somehow makes this work as desired.

### Moving packages installed during the build to the final rock

By listing `python3.10` and `python3-pip` in `overlay-packages`, rockcraft will promote python/pip to the final rock but it **does not automatically migrate any python packages we have installed**.  As a workaround, we copy the installed packages manually by copying the contents of `/usr/local/lib/python3.10/dist-packages` to `$CRAFT_PART_INSTALL/usr/local/lib/python3.10/dist-packages` (which will be rendered to `/usr/local/lib/python3.10/dist-packages` in the final rock.


### Installing kserve/server-specific package via a dummy poetry package

When you install a local package using `poetry install`, poetry installs the root package (eg: the package you have code for locally) as editable (equivalent to doing `pip -e /my/local/package`), while the package's dependencies are installed as non-editable (default `pip` behaviour).  Packages installed normally have their code put into `/usr/local/lib/python3.10/dist-packages`, but editable packages are not copied to this directory and instead just point to your local folder where you installed them from.  Because we are in the rock's build environment when we do `poetry install`, this means the package is installed pointing to its location in the build environment (eg: `/root/parts/mypart/build/mycode`) and not the final rock environment.  The result of this is the package is not actually included in the final rock.  

To work around this, we define a dummy poetry project that has two dependencies, the `kserve` and server-specific python code, for example:

```
[tool.poetry]
name = "workaround-for-editable-install"
version = "0.0.1"
description = ""
authors = ["none"]

[tool.poetry.dependencies]
python = ">=3.8,<3.12"
kserve = { path = "../python/kserve", develop = false }
sklearnserver = { path = "../python/sklearnserver", develop = false }
```

This tricks poetry into:
* installing the dummy package as editable
* installing the dummy package's dependencies (`kserve` and server-specific package) statically (copying the files into `.../dist-packages`).  

This workaround is equivalent to the upstream Dockerfile doing:

```
COPY kserve/pyproject.toml kserve/poetry.lock kserve/
RUN cd kserve && poetry install --no-root --no-interaction --no-cache
COPY kserve kserve
RUN cd kserve && poetry install --no-interaction --no-cache

COPY sklearnserver/pyproject.toml sklearnserver/poetry.lock sklearnserver/
RUN cd sklearnserver && poetry install --no-root --no-interaction --no-cache
COPY sklearnserver sklearnserver
RUN cd sklearnserver && poetry install --no-interaction --no-cache
```

where, for each of `kserve` and `sklearnserver`, they copy the poetry project (.toml, poetry.lock, and source code) into the image and then install via poetry.  Why they do each `poetry install` in two parts is not clear, but it seems like they first install dependencies without the local package (via `--no-root`) and then install the local package.  

### Ensuring the entrypoint/rock internals are as similar to upstream as possible

The upstream install procedure results in `python` being executable, but our rock builds with `python3.10` being the executable.  To address this, we add a symbolic link to `$CRAFT_PART_INSTALL`

## Integration testing the server images

### Prerequisites

* docker
* Google Cloud CLI tools ([installation guide](https://cloud.google.com/sdk/docs/install))

### Instructions

For every inference server provided, upstream maintains an example usage in their [Model Serving Runtimes docs](https://kserve.github.io/website/master/modelserving/v1beta1/serving_runtime/).  Each example includes a model for the given server, for example the [`Scikit-learn`](https://kserve.github.io/website/master/modelserving/v1beta1/sklearn/v2/#deploy-the-model-with-rest-endpoint-through-inferenceservice/) runtime has a provided model at `gs://kfserving-examples/models/sklearn/1.0/model`.  

While the upstream examples show how to use these models in kserve itself, we can use the same models to test the inference server rocks directly.  For example, we can do:

Launch the server with:
```
# download the model locally
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
