## Summary of upstream dockerfiles

The kserve server rocks in this repo build images for the upstream dockerfiles located [here](https://github.com/kserve/kserve/tree/master/python).  These server images all have the following common traits:

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

When you install a local package using `poetry install`, poetry installs the root package (eg: the package you have code for locally) as editable (equivalent to doing `pip -e /my/local/package`), while the package's dependencies are installed as non-editable (default `pip` behaviour). Normally, packages.  Packages normally are installed by copying their code to `/usr/local/lib/python3.10/dist-packages`, but editable packages are not copied to this directory and instead just point to your local folder where you installed them from.  Because we are in the rock's build environment when we do `poetry install`, this means the package is installed pointing to its location in the build environment (eg: `/root/parts/mypart/build/mycode`) and not the final rock environment.  The result of this is the package is not actually included in the final rock.  

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
