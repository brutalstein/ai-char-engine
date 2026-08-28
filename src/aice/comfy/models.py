from __future__ import annotations

import hashlib
import json
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_REGISTRY = Path(__file__).with_name("registry.json")


@dataclass(frozen=True)
class ModelSpec:
    key: str
    filename: str
    dest_subdir: str
    url: str
    size_bytes: int
    sha256: str | None
    license: str
    required: bool

    def dest(self, models_dir: Path) -> Path:
        return Path(models_dir) / self.dest_subdir / self.filename


def load_registry(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or _REGISTRY).read_text(encoding="utf-8"))


def model_specs(registry: dict[str, Any] | None = None) -> dict[str, ModelSpec]:
    reg = registry or load_registry()
    out: dict[str, ModelSpec] = {}
    for key, m in reg.get("models", {}).items():
        out[key] = ModelSpec(
            key=key,
            filename=m["filename"],
            dest_subdir=m["dest_subdir"],
            url=m["url"],
            size_bytes=int(m["size_bytes"]),
            sha256=m.get("sha256"),
            license=m["license"],
            required=bool(m.get("required", False)),
        )
    return out


def capability_model_keys(capability: str, registry: dict[str, Any] | None = None) -> list[str]:
    reg = registry or load_registry()
    keys = reg.get("capability_models", {}).get(capability, [])
    return [str(k) for k in keys]


def capability_missing(models_dir: Path, capability: str,
                       registry: dict[str, Any] | None = None) -> list[str]:
    reg = registry or load_registry()
    specs = model_specs(reg)
    keys = capability_model_keys(capability, reg)
    return [key for key in keys if key not in specs or not verify(specs[key].dest(models_dir), specs[key])[0]]


def capability_ready(models_dir: Path, capability: str,
                     registry: dict[str, Any] | None = None) -> bool:
    keys = capability_model_keys(capability, registry)
    return bool(keys) and not capability_missing(models_dir, capability, registry)


def model_profiles(registry: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Machine-readable per-model profiles (see registry.json ``model_profiles``)."""
    reg = registry or load_registry()
    return {str(k): dict(v) for k, v in reg.get("model_profiles", {}).items()}


def model_profile_state(models_dir: Path, model_id: str,
                        registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """A profile enriched with live installed/missing state and the resolved local path."""
    reg = registry or load_registry()
    profile = dict(model_profiles(reg).get(model_id, {}))
    if not profile:
        return {"model_id": model_id, "known": False}
    capability = str(profile.get("capability", ""))
    missing = capability_missing(models_dir, capability, reg) if capability else ["*"]
    key = str(profile.get("model_key", model_id))
    specs = model_specs(reg)
    local_path = str(specs[key].dest(models_dir)) if key in specs else None
    return {
        **profile,
        "known": True,
        "installed": not missing,
        "missing_models": missing,
        "local_path": local_path,
    }


def sha256_file(path: Path, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify(path: Path, spec: ModelSpec, *, check_hash: bool = False) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing"
    actual = path.stat().st_size
    if spec.size_bytes and actual != spec.size_bytes:
        return False, f"size {actual} != expected {spec.size_bytes}"
    if check_hash and spec.sha256:
        digest = sha256_file(path)
        if digest != spec.sha256:
            return False, f"sha256 mismatch ({digest[:12]}...)"
    return True, "ok"


def presence(models_dir: Path, registry: dict[str, Any] | None = None) -> dict[str, bool]:
    specs = model_specs(registry)
    return {key: verify(spec.dest(models_dir), spec)[0] for key, spec in specs.items()}


def missing_required(models_dir: Path, registry: dict[str, Any] | None = None) -> list[str]:
    specs = model_specs(registry)
    return [k for k, s in specs.items() if s.required and not verify(s.dest(models_dir), s)[0]]


def required_bytes(registry: dict[str, Any] | None = None, *, keys: list[str] | None = None) -> int:
    specs = model_specs(registry)
    chosen = keys if keys is not None else [k for k, s in specs.items() if s.required]
    return sum(specs[k].size_bytes for k in chosen if k in specs)


def free_disk_bytes(path: Path) -> int:
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def download(
    spec: ModelSpec,
    dest: Path,
    *,
    progress: Callable[[int, int], None] | None = None,
    resume: bool = True,
    check_hash: bool = True,
) -> Path:
    """Resumable download to ``dest``. Skips work when an intact file already exists."""

    dest = Path(dest)
    if verify(dest, spec, check_hash=False)[0]:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    attempts = 8
    for attempt in range(1, attempts + 1):
        have = part.stat().st_size if (resume and part.exists()) else 0
        if have and spec.size_bytes and have >= spec.size_bytes:
            part.unlink()
            have = 0
        req = urllib.request.Request(spec.url, headers={"User-Agent": "aice-comfy/1"})
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                mode = "ab" if have else "wb"
                if have and resp.status != 206:
                    have, mode = 0, "wb"
                total = spec.size_bytes or (int(resp.headers.get("Content-Length", 0)) + have)
                done = have
                with part.open(mode) as fh:
                    while True:
                        block = resp.read(4 * 1024 * 1024)
                        if not block:
                            break
                        fh.write(block)
                        done += len(block)
                        if progress:
                            progress(done, total)
            if not total or done >= total:
                break
            if attempt == attempts:
                break
            time.sleep(3 * attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            if attempt == attempts:
                raise OSError(f"{spec.filename}: download failed after {attempts} tries ({exc})") from None
            time.sleep(3 * attempt)

    if spec.size_bytes and part.stat().st_size != spec.size_bytes:
        raise OSError(f"{spec.filename}: downloaded {part.stat().st_size} != {spec.size_bytes}")
    part.replace(dest)
    good, why = verify(dest, spec, check_hash=check_hash)
    if not good:
        dest.unlink(missing_ok=True)
        raise OSError(f"{spec.filename}: verification failed after download ({why})")
    return dest
