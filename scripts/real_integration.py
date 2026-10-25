"""Run an offline, actual TranslateGemma → XeLaTeX acceptance sample."""

import json
import os
from pathlib import Path

from kizunapdf.config import Settings
from kizunapdf.core.export import export_result, rebuild
from kizunapdf.core.jobs import JobManager
from kizunapdf.core.render import render_page

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
# Deny Python internet socket connections during processing as an offline regression.
import socket

attempts = []
_original_connect = socket.socket.connect


def deny_network(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        attempts.append(str(address))
        raise RuntimeError("Unexpected network access during local processing")
    return _original_connect(sock, address)


socket.socket.connect = deny_network
settings = Settings(
    data_dir=Path(os.environ.get("KIZUNAPDF_ACCEPTANCE_DIR", ".runtime/acceptance-jobs")).resolve()
)
manager = JobManager(settings)
job = manager.create(Path("tests/fixtures/generated/native.pdf"))
state = manager.process(job["id"])
print(json.dumps(state, indent=2), flush=True)
work = manager.folder(job["id"])
if not state["output_available"]:
    raise SystemExit(1)
export_result(work, Path("output/acceptance"), "native")
report = rebuild(work / "reconstruction.zip", Path("output/acceptance/rebuilt.pdf"), settings)
print("Rebuilt:", report.status, flush=True)
render_page(work / "original.pdf", 0, 110).save("output/acceptance/original.png")
render_page(work / "translated.pdf", 0, 110).save("output/acceptance/translated.png")
print((work / "manifest.json").read_text(), flush=True)
print("Internet socket attempts:", attempts, flush=True)
manager.pool.shutdown(wait=False)
