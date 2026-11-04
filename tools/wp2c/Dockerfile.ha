# syntax=docker/dockerfile:1
# The pinned Assist class imports need two source-only CPython 3.14 extensions.
# Compile them during setup against the same bookworm ABI as the runtime.
FROM python:3.14.2-slim-bookworm@sha256:e87711ef5c86aaeaa7031718a69db79d334d94c545c709583f651b8185870941 AS ui-wheels
RUN --mount=type=secret,id=proxy_ca,required=true \
    apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca update \
    && apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca install --no-install-recommends -y g++ \
    && PIP_CERT=/run/secrets/proxy_ca python -m pip install --index-url https://pypi.org/simple --no-cache-dir --no-compile \
      "pybind11==3.0.4" "setuptools==82.0.1" "wheel==0.46.3" \
    && PIP_CERT=/run/secrets/proxy_ca python -m pip wheel --index-url https://pypi.org/simple --no-cache-dir \
      --no-deps --no-build-isolation --wheel-dir /wheels "pymicro-vad==1.0.1" "pyspeex-noise==1.0.2"

# The full official HA appliance image exceeds the disposable runner's disk budget.
FROM python:3.14.2-slim-bookworm@sha256:e87711ef5c86aaeaa7031718a69db79d334d94c545c709583f651b8185870941
ARG HA_VERSION=2026.10.4
ARG HA_SHA256=71843060980a763187d856a8ff170640f1e287a7b741334cd838c81404f1f452
# Keep filesystem changes before dependency installation: vfs duplicates each layer.
COPY libsqlite3.so.0 /opt/wp2c/lib/libsqlite3.so.0
COPY requirements-ha-ui.txt /opt/wp2c/requirements-ha-ui.txt
COPY --from=ui-wheels /wheels /opt/wp2c/wheels
ENV LD_LIBRARY_PATH=/opt/wp2c/lib
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /config
RUN --mount=type=secret,id=proxy_ca,required=true \
    apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca update \
    && apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca install --no-install-recommends -y libturbojpeg0 \
    && rm -rf /var/lib/apt/lists/* \
    && PIP_CERT=/run/secrets/proxy_ca python -m pip download --index-url https://pypi.org/simple --no-deps --no-cache-dir \
      --dest /tmp/wp2c-wheel "homeassistant==${HA_VERSION}" \
    && echo "${HA_SHA256}  /tmp/wp2c-wheel/homeassistant-${HA_VERSION}-py3-none-any.whl" | sha256sum --check --strict \
    && PIP_CERT=/run/secrets/proxy_ca python -m pip install --index-url https://pypi.org/simple --no-cache-dir --no-compile \
      --find-links /opt/wp2c/wheels --requirement /opt/wp2c/requirements-ha-ui.txt \
      "/tmp/wp2c-wheel/homeassistant-${HA_VERSION}-py3-none-any.whl" \
      "home-assistant-frontend==20260930.5" "mypy==2.4.1" "coverage==7.17.1" \
      "ast-serialize==0.13.1" "librt==0.16.0" "mypy_extensions==1.1.0" \
      "pathspec==1.1.1" "typing_extensions==4.16.0" \
    && rm -rf /tmp/wp2c-wheel /opt/wp2c/wheels
ENTRYPOINT ["python", "-m", "homeassistant", "--config", "/config", "--skip-pip"]
