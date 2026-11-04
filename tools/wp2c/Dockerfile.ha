# syntax=docker/dockerfile:1
# The full official HA appliance image exceeds the disposable runner's disk budget.
FROM python:3.14.2-slim-bookworm@sha256:e87711ef5c86aaeaa7031718a69db79d334d94c545c709583f651b8185870941
ARG HA_VERSION=2026.10.4
ARG HA_SHA256=71843060980a763187d856a8ff170640f1e287a7b741334cd838c81404f1f452
# Keep filesystem changes before dependency installation: vfs duplicates each layer.
COPY libsqlite3.so.0 /opt/wp2c/lib/libsqlite3.so.0
ENV LD_LIBRARY_PATH=/opt/wp2c/lib
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /config
RUN --mount=type=secret,id=proxy_ca,required=true \
    PIP_CERT=/run/secrets/proxy_ca python -m pip download --index-url https://pypi.org/simple --no-deps --no-cache-dir \
      --dest /tmp/wp2c-wheel "homeassistant==${HA_VERSION}" \
    && echo "${HA_SHA256}  /tmp/wp2c-wheel/homeassistant-${HA_VERSION}-py3-none-any.whl" | sha256sum --check --strict \
    && PIP_CERT=/run/secrets/proxy_ca python -m pip install --index-url https://pypi.org/simple --no-cache-dir --no-compile \
      "/tmp/wp2c-wheel/homeassistant-${HA_VERSION}-py3-none-any.whl" \
      "home-assistant-frontend==20260930.5" "mypy==2.4.1" "coverage==7.17.1" \
      "ast-serialize==0.13.1" "librt==0.16.0" "mypy_extensions==1.1.0" \
      "pathspec==1.1.1" "typing_extensions==4.16.0" \
    && rm -rf /tmp/wp2c-wheel
ENTRYPOINT ["python", "-m", "homeassistant", "--config", "/config", "--skip-pip"]
