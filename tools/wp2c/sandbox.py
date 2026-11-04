#!/usr/bin/env python3
"""Disposable native HA runner. It cannot select an existing HA or Docker endpoint."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
HA_VERSION = "2026.10.4"
BASE_IMAGE = "python:3.14.2-slim-bookworm@sha256:e87711ef5c86aaeaa7031718a69db79d334d94c545c709583f651b8185870941"
IMAGE = "wp2c-ha:2026.10.4"
BROWSER_IMAGE = "mcr.microsoft.com/playwright:v1.64.1-noble@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f"
SQLITE_URL = "https://www.sqlite.org/2026/sqlite-amalgamation-3510300.zip"
SQLITE_SHA = "acb1e6f5d832484bf6d32b681e858c38add8b2acdfd42ac5df24b8afb46552b4"
LABEL = "org.heating-ai.wp2c.run"


def docker(*args: str, data: str | None = None, capture: bool = True) -> str:
    env = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(key, None)
    env["BUILDX_CONFIG"] = str(Path(tempfile.gettempdir()) / "wp2c-buildx")
    result = subprocess.run(
        ["docker", "--host=unix:///var/run/docker.sock", *args],
        input=data, text=True, stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None, env=env, check=False,
    )
    if result.returncode:
        # Arguments can include disposable credentials; never include them in errors.
        raise RuntimeError(f"Local Docker {args[0]} failed: {((result.stdout or '') + (result.stderr or ''))[-12000:]}")
    return result.stdout or ""


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not str(value.get("name", "")).startswith("wp2c-"):
        raise ValueError("Expected this harness's newly provisioned sandbox state")
    return value


def build() -> None:
    """Fetch official sources only during setup; runtime has no network route."""
    with tempfile.TemporaryDirectory(prefix="wp2c-build-") as directory:
        path = Path(directory)
        archive = urllib.request.urlopen(SQLITE_URL, timeout=60).read()
        if hashlib.sha256(archive).hexdigest() != SQLITE_SHA:
            raise ValueError("Official SQLite source checksum mismatch")
        with zipfile.ZipFile(io.BytesIO(archive)) as source:
            for filename in ("sqlite3.c", "sqlite3.h"):
                (path / filename).write_bytes(source.read(f"sqlite-amalgamation-3510300/{filename}"))
        subprocess.run(
            ["cc", "-O2", "-fPIC", "-shared", "-DSQLITE_THREADSAFE=1", "-DSQLITE_ENABLE_FTS5",
             "-DSQLITE_ENABLE_RTREE", "-DSQLITE_ENABLE_COLUMN_METADATA",
             "-o", str(path / "libsqlite3.so.0"), str(path / "sqlite3.c"), "-lm"], check=True,
        )
        shutil.copyfile(HERE / "Dockerfile.ha", path / "Dockerfile")
        shutil.copyfile(HERE / "requirements-ha-ui.txt", path / "requirements-ha-ui.txt")
        docker("pull", BASE_IMAGE, capture=False)
        docker("build", "--secret", "id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt", "--tag", IMAGE, str(path), capture=False)


def up(state_path: Path, package: Path | None) -> None:
    if state_path.exists():
        raise ValueError("Refusing to replace an existing sandbox state file")
    name = "wp2c-" + uuid.uuid4().hex[:12]
    state = {"name": name, "config_volume": name + "-config", "data_volume": name + "-data", "image": IMAGE}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    save(state_path, state)
    for key in ("config_volume", "data_volume"):
        docker("volume", "create", "--label", f"{LABEL}={name}", state[key])
    docker(
        "create", "--name", name, "--label", f"{LABEL}={name}", "--network", "none",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "256",
        "--mount", f"type=volume,src={state['config_volume']},dst=/config",
        "--mount", f"type=volume,src={state['data_volume']},dst=/tmp",
        "-e", "HEATING_AI_TEST_SANDBOX=1",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        *[arg for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy") for arg in ("-e", key + "=")],
        IMAGE,
    )
    with tempfile.TemporaryDirectory(prefix="wp2c-config-") as directory:
        path = Path(directory)
        (path / ".storage").mkdir()
        # Suppress HA's optional onboarding cloud defaults while exercising genuine user onboarding.
        save(path / ".storage/onboarding", {"version": 4, "minor_version": 1, "key": "onboarding", "data": {"done": ["core_config", "analytics", "integration"]}})
        (path / "configuration.yaml").write_text(
            "homeassistant:\n  name: Synthetic WP2C\n  latitude: 0\n  longitude: 0\n"
            "  elevation: 0\n  time_zone: UTC\n  unit_system: metric\n"
            "  auth_providers:\n    - type: homeassistant\n"
            "http:\n  server_host: 127.0.0.1\n  server_port: 8123\n"
            "frontend:\napi:\nconfig:\nlogger:\n  default: warning\n"
        )
        (path / ".heating-ai-isolated-test").write_text("synthetic-only\n")
        save(path / ".wp2c-secrets.json", {
            "admin_user": "synthetic_admin", "admin_password": secrets.token_urlsafe(32),
            "reader_user": "synthetic_reader", "reader_password": secrets.token_urlsafe(32),
        })
        if package:
            component = package / "custom_components/heating_ai"
            if not (component / "manifest.json").is_file():
                raise ValueError("package-dir must contain custom_components/heating_ai/manifest.json")
            shutil.copytree(component, path / "custom_components/heating_ai")
        docker("cp", str(path) + "/.", name + ":/config")
    docker("cp", str(HERE / "native_checks.py"), name + ":/tmp/native_checks.py")
    normalize(state)
    docker("start", name)
    result = docker("exec", name, "python", "/tmp/native_checks.py", "bootstrap")
    save(state_path.with_name(state_path.stem + "-bootstrap.json"), json.loads(result))
    print(result, end="")
    proof(state_path)


def normalize(state: dict) -> None:
    # docker cp preserves source ownership; runtime drops DAC_OVERRIDE and CHOWN.
    script = "import os\nfor base in ('/config','/data'):\n for root,dirs,files in os.walk(base):\n  for p in [root]+[os.path.join(root,n) for n in dirs+files]: os.chown(p,0,0,follow_symlinks=False)\n"
    docker("run", "--rm", "--name", state["name"] + "-permissions", "--label", f"{LABEL}={state['name']}",
           "--network", "none", "--security-opt", "no-new-privileges",
           "--mount", f"type=volume,src={state['config_volume']},dst=/config",
           "--mount", f"type=volume,src={state['data_volume']},dst=/data",
           "--entrypoint", "python", BASE_IMAGE, "-c", script)


def proof(state_path: Path) -> None:
    state = load(state_path)
    details = json.loads(docker("inspect", state["name"]))[0]
    host = details["HostConfig"]
    assert host["NetworkMode"] == "none"
    assert not host["PortBindings"] and not host["Privileged"]
    assert host["CapDrop"] == ["ALL"]
    assert not host.get("Devices") and not host.get("DeviceRequests")
    assert all(m["Type"] == "volume" and m["Name"] in (state["config_volume"], state["data_volume"]) for m in details["Mounts"])
    image = json.loads(docker("image", "inspect", details["Image"]))[0]
    checks = json.loads(docker("exec", state["name"], "python", "/tmp/native_checks.py", "isolation"))
    report = {
        "qualification": "PASS_ISOLATED", "run": state["name"], "ha_version": HA_VERSION,
        "image_id": image["Id"], "image_repo_digests": image.get("RepoDigests", []), "base_image": BASE_IMAGE,
        "network_mode": host["NetworkMode"], "port_bindings": host["PortBindings"],
        "privileged": host["Privileged"], "cap_drop": host["CapDrop"],
        "devices": host.get("Devices", []), "device_requests": host.get("DeviceRequests"),
        "mounts": [{"name": m["Name"], "destination": m["Destination"]} for m in details["Mounts"]],
        "sqlite_source": {"url": SQLITE_URL, "sha256": SQLITE_SHA}, "native_checks": checks,
        "physical": "NOT_TESTED", "production": "NOT_ACCESSED", "g1": "B01-B08 BLOCKED",
    }
    save(state_path.with_name(state_path.stem + "-isolation.json"), report)
    print(json.dumps(report, indent=2))


def checks(state_path: Path, mode: str) -> None:
    state = load(state_path)
    docker("cp", str(HERE / "native_checks.py"), state["name"] + ":/tmp/native_checks.py")
    normalize(state)
    result = docker("exec", state["name"], "python", "/tmp/native_checks.py", mode)
    save(state_path.with_name(state_path.stem + "-" + mode + ".json"), json.loads(result))
    print(result, end="")


def typecheck(state_path: Path) -> None:
    state = load(state_path)
    result = docker("exec", state["name"], "python", "-m", "mypy", "--strict", "--explicit-package-bases", "--follow-imports=silent", "/config/custom_components/heating_ai")
    state_path.with_name(state_path.stem + "-sdk-mypy.log").write_text(result)
    print(result, end="")


def migration(state_path: Path) -> None:
    state = load(state_path)
    docker("stop", state["name"])
    script = """import json
from pathlib import Path
root=Path('/config');secret=json.loads((root/'.wp2c-secrets.json').read_text())
p=root/'.storage/core.config_entries';value=json.loads(p.read_text())
entry=next(e for e in value['data']['entries'] if e['entry_id']==secret['entry_id'])
assert entry['domain']=='heating_ai' and entry['version']==1
entry['minor_version']=0;entry['options']['simulation_enabled']=True
entry['data']={'schema_version':0,'synthetic':True};p.write_text(json.dumps(value))
config=root/'configuration.yaml';text=config.read_text()
if 'recorder:' not in text:text+='recorder:\\n  db_url: sqlite:////config/wp2c-synthetic-recorder.sqlite3\\n  commit_interval: 1\\n  include:\\n    entities:\\n      - sensor.wp2c_synthetic_recorded\\nhistory:\\n'
config.write_text(text)
"""
    docker("run", "--rm", "--name", state["name"] + "-migration-prepare", "--label", f"{LABEL}={state['name']}", "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--mount", f"type=volume,src={state['config_volume']},dst=/config", "--entrypoint", "python", BASE_IMAGE, "-c", script)
    docker("start", state["name"])
    checks(state_path, "migration")


def browser(state_path: Path, project: str, image: str, output: Path) -> None:
    state = load(state_path)
    name = state["name"] + "-browser-" + project
    # Mountpoints must exist before /work becomes read-only (fresh CI checkout).
    for directory in ("test-results", "playwright-report-native"):
        (ROOT / "frontend" / directory).mkdir(exist_ok=True)
    # Read disposable credentials into memory; never place them in argv, environment selectors or reports.
    credentials = json.loads(docker("exec", state["name"], "python", "-c", "from pathlib import Path;print(Path('/config/.wp2c-secrets.json').read_text())"))
    payload = json.dumps({"user": credentials["admin_user"], "password": credentials["admin_password"], "project": project})
    docker("create", "--name", name, "--label", f"{LABEL}={state['name']}",
           "--network", "container:" + state["name"], "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "512",
           "--user", f"{os.getuid()}:{os.getgid()}",
           "--mount", f"type=bind,src={ROOT / 'frontend'},dst=/work,readonly",
           "--tmpfs", "/work/test-results:rw,mode=1777", "--tmpfs", "/work/playwright-report-native:rw,mode=1777",
           "--workdir", "/work", "-e", "CI=1", "-e", "TEST_HA_BASE_URL=http://127.0.0.1:8123",
           "-e", "GIO_USE_PROXY_RESOLVER=dummy",
           "-e", "NO_PROXY=127.0.0.1,localhost", "-e", "no_proxy=127.0.0.1,localhost",
           *[arg for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy") for arg in ("-e", key + "=")],
           "--entrypoint", "node", image, "-e", "setInterval(()=>{},1000)")
    try:
        docker("start", name)
        details = json.loads(docker("inspect", name))[0]
        ha_id = json.loads(docker("inspect", state["name"]))[0]["Id"]
        assert details["HostConfig"]["NetworkMode"] in ("container:" + state["name"], "container:" + ha_id)
        assert not details["HostConfig"]["PortBindings"] and not details["HostConfig"]["Privileged"]
        runner = """let input='';process.stdin.on('data',b=>input+=b);process.stdin.on('end',()=>{const p=JSON.parse(input);const r=require('node:child_process').spawnSync('npm',['run','test:browser:native','--','--project=native-'+p.project+'-*'],{encoding:'utf8',env:{...process.env,TEST_HA_USER:p.user,TEST_HA_PASSWORD:p.password}});const clean=s=>(s||'').split(p.password).join('<synthetic-password-redacted>');process.stdout.write(clean(r.stdout));process.stderr.write(clean(r.stderr));console.log('WP2C_BROWSER_EXIT='+r.status);});"""
        result = docker("exec", "-i", name, "node", "-e", runner, data=payload)
        output.mkdir(parents=True, exist_ok=True)
        (output / (project + ".log")).write_text(result.replace(credentials["admin_password"], "<synthetic-password-redacted>"))
        with tempfile.TemporaryDirectory(prefix="wp2c-browser-results-") as directory:
            docker("cp", name + ":/work/test-results/.", directory)
            report_path = Path(directory) / "native-results.json"
            stats = json.loads(report_path.read_text())["stats"] if report_path.exists() else {}
            complete = (stats.get("expected", 0) >= 14 and stats["unexpected"] == 0
                        and stats["skipped"] == 0 and stats.get("flaky", 0) == 0)
            for source in Path(directory).rglob("*"):
                if source.is_file() and source.suffix in (".png", ".json", ".md"):
                    target = output / project / source.relative_to(directory)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if source.suffix == ".png":
                        shutil.copyfile(source, target)
                    else:
                        target.write_text(source.read_text().replace(credentials["admin_password"], "<synthetic-password-redacted>"))
        image_details = json.loads(docker("image", "inspect", image))[0]
        save(output / (project + "-isolation.json"), {"qualification": "PASS_ISOLATED" if "WP2C_BROWSER_EXIT=0" in result and complete else "FAILED_ISOLATED", "browser_image": image, "browser_image_id": details["Image"], "browser_repo_digests": image_details.get("RepoDigests", []), "network_mode": details["HostConfig"]["NetworkMode"], "port_bindings": details["HostConfig"]["PortBindings"], "privileged": False, "traces": "disabled", "credentials": "ephemeral synthetic, excluded", "browser_stats": stats})
        print(result, end="")
        if "WP2C_BROWSER_EXIT=0" not in result or not complete:
            raise AssertionError("Native browser suite failed; sanitized results retained")
    finally:
        docker("rm", "--force", name)


def stop(state_path: Path) -> None:
    state = load(state_path)
    name = state["name"]
    owned = docker("container", "ls", "--all", "--filter", f"label={LABEL}={name}", "--format", "{{.Names}}").splitlines()
    for container in sorted(owned, key=lambda item: item == name):
        if container != name and not container.startswith(name + "-"):
            raise ValueError("Unexpected owned-container name; refusing teardown")
        details = json.loads(docker("inspect", container))[0]
        if details["Config"]["Labels"].get(LABEL) != name:
            raise ValueError("Container ownership label mismatch; refusing teardown")
        docker("rm", "--force", container)
    for key in ("config_volume", "data_volume"):
        details = json.loads(docker("volume", "inspect", state[key]))[0]
        if details["Labels"].get(LABEL) != name:
            raise ValueError("Volume ownership label mismatch; refusing teardown")
        docker("volume", "rm", state[key])
    save(state_path.with_name(state_path.stem + "-teardown.json"), {"run": name, "container_removed": True, "volumes_removed": True})
    state_path.unlink()
    print("Removed this run's disposable container and two volumes.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "up", "proof", "checks", "restart", "migration", "browser", "typecheck", "stop"))
    parser.add_argument("--state", type=Path, default=Path("/tmp/wp2c-sandbox.json"))
    parser.add_argument("--package-dir", type=Path)
    parser.add_argument("--project", choices=("chromium", "webkit"), default="chromium")
    parser.add_argument("--browser-image", default=BROWSER_IMAGE)
    parser.add_argument("--output", type=Path, default=Path("/tmp/wp2c-browser-results"))
    args = parser.parse_args()
    if args.action == "build":
        build()
    elif args.action == "up":
        up(args.state, args.package_dir)
    elif args.action == "proof":
        proof(args.state)
    elif args.action == "checks":
        checks(args.state, "integration")
    elif args.action == "typecheck":
        typecheck(args.state)
    elif args.action == "migration":
        migration(args.state)
    elif args.action == "browser":
        browser(args.state, args.project, args.browser_image, args.output)
    elif args.action == "restart":
        state = load(args.state)
        docker("restart", state["name"])
        checks(args.state, "restart")
    else:
        stop(args.state)


if __name__ == "__main__":
    main()
