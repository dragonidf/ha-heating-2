"""Build a self-contained test component without installing it into any HA."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile

ROOT=Path(__file__).resolve().parents[2]

def build(destination:Path)->dict:
    if destination.is_symlink():
        raise ValueError("Linked package destination forbidden")
    destination=destination.resolve()
    if (destination.parent!=Path(tempfile.gettempdir()).resolve()
            or not destination.name.startswith("heating-wp2c-package-")
            or destination.is_symlink() or destination.exists() and any(destination.iterdir())):
        raise ValueError("Empty disposable package directory required")
    assets=ROOT/"frontend/dist/assets"
    if not (assets/"panel.js").is_file():
        raise ValueError("Build the reviewed frontend and native panel first")
    if not (ROOT/"packages/ha_native/fixture.json").is_file():
        raise ValueError("Export synthetic fixtures first")
    destination.mkdir(exist_ok=True)
    target=destination/"custom_components/heating_ai"
    files=[]
    sources=[(ROOT/"ha_sdk/heating_ai",target),(ROOT/"packages",target/"core"),(assets,target/"assets")]
    for source,output in sources:
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError("Linked package source forbidden")
            if not path.is_file() or "__pycache__" in path.parts or path.suffix==".pyc":
                continue
            relative=path.relative_to(source)
            if source.name=="heating_ai" and relative.parts[0] in ("core","assets"):
                continue
            data=path.read_bytes()
            converted=data
            if source.name=="packages" and path.suffix==".py":
                converted=data.replace(b"from packages.",b"from custom_components.heating_ai.core.")
            result=output/relative
            result.parent.mkdir(parents=True,exist_ok=True)
            result.write_bytes(converted)
            files.append({"source":str(path.relative_to(ROOT)),"source_sha256":sha256(data).hexdigest(),
                          "artifact":str(result.relative_to(destination)),"sha256":sha256(converted).hexdigest()})
    report={"schema":1,"ha_version":"2026.10.4","scope":"isolated synthetic test only; physical authority false",
            "vendor_transform":"absolute Python import prefix only; accepted algorithms unchanged","files":files}
    (destination/"BUILD-MANIFEST.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();report=build(args.output)
    print(json.dumps({"output":str(args.output),"files":len(report["files"]),"ha_version":report["ha_version"]}))
