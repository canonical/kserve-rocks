ARG BASE_IMAGE=base-pmmlserver:v0.10.0_22.04_1
FROM $BASE_IMAGE
# Provide Default Entrypoint for Pebble
ENTRYPOINT [ "/bin/pebble", "enter", "--verbose", "--args", "pmml-server" ]