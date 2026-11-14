"""Remote-only helpers for the independently executable audit scripts."""
import base64
import io
import json
import os
import time
from pathlib import Path

import httpx
from PIL import Image, ImageStat

BASE = os.environ["AUDIT_API"].rstrip("/")
CASE = os.environ.get("AUDIT_CASE_ID", "manual")
TRACE = Path(os.environ.get("AUDIT_RESULTS", "/tmp/audit/results")) / "http"
TRACE.mkdir(parents=True, exist_ok=True)


def invoke(language, op, body):
    sent = {**body, "case_id": CASE}
    response = httpx.post(f"{BASE}/invoke/{language}/{op}", json=sent, timeout=65)
    payload = response.json()
    with (TRACE / f"{CASE}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"request": sent, "language": language, "operation": op,
                            "http_status": response.status_code, "response": payload}) + "\n")
    assert response.status_code == 200, (response.status_code, response.text[:1000])
    assert not payload.get("harness_error"), payload
    return payload


def value(language, op, body):
    payload = invoke(language, op, body)
    assert payload["ok"], payload
    return payload["value"]


def codes(v):
    return sorted((i["code"], i["path"]) for i in v.get("issues", []))


def validate_png(b64):
    png = base64.b64decode(b64)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    layer = Image.open(io.BytesIO(png)).convert("RGBA")
    image = Image.new("RGBA", layer.size, (255,255,255,255))
    image.alpha_composite(layer)
    image = image.convert("RGB")
    assert image.width >= 400 and image.height >= 300, image.size
    assert max(ImageStat.Stat(image).stddev) > 5, "blank chart"
    return image


def expect_exception(language, op, body, message=None):
    r = invoke(language, op, body)
    assert not r["ok"], r
    if message:
        assert message.lower() in r["message"].lower(), r
    return r
