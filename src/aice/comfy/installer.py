from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import config as cfgmod
from . import hardware as hw
from . import models as modelmod
from . import policy as policymod

Progress = Callable[[str], None]
MIN_FREE_GB_FRESH = 40
_WINDOWS = os.name == "nt"


class InstallError(RuntimeError):
    pass


_TRANSIENT = (
    "could not resolve host", "temporary failure", "connection reset", "timed out",
    "connection timed out", "failed to connect", "network is unreachable",
    "unable to access", "ssl", "recv failure", "gnutls_handshake",
)


def _run(cmd: list[str], *, cwd: Path | None = None, log: Progress | None = None,
         retries: int = 3) -> str:
    if log:
        log("$ " + " ".join(str(c) for c in cmd))
    last = ""
    for attempt in range(1, retries + 1):
        proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
        if proc.returncode == 0:
            return proc.stdout
        last = (proc.stdout[-2000:] + proc.stderr[-2000:]).strip()
        if attempt < retries and any(t in last.lower() for t in _TRANSIENT):
            wait = 3 * attempt
            if log:
                log(f"  transient failure, retry {attempt + 1}/{retries} in {wait}s")
            time.sleep(wait)
            continue
        break
    raise InstallError(f"command failed: {' '.join(map(str, cmd))}\n{last}")


def _git_sha(repo: Path) -> str:
    try:
        return _run(["git", "-C", str(repo), "rev-parse", "HEAD"]).strip()
    except InstallError:
        return ""


def _ensure_pinned_repo(url: str, target: Path, pin: str, *, log: Progress | None = None) -> str:
    """Ensure target is an exact detached checkout of the tested revision."""
    target = target.resolve()
    if target.exists() and not (target / ".git").exists():
        raise InstallError(f"refusing to overwrite non-git directory: {target}")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--filter=blob:none", "--no-checkout", url, str(target)], log=log)
    current = _git_sha(target)
    if current == pin:
        return current
    _run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", pin], log=log)
    _run(["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"], log=log)
    current = _git_sha(target)
    if current != pin:
        raise InstallError(f"repository pin mismatch for {target.name}: expected {pin}, got {current or 'unknown'}")
    return current


def _venv_base_python() -> list[str]:
    if _WINDOWS and shutil.which("py"):
        for ver in ("-3.12", "-3.13", "-3.11"):
            probe = subprocess.run(["py", ver, "-c", "import sys"], capture_output=True)
            if probe.returncode == 0:
                return ["py", ver]
    exe = sys.executable
    if "conda" in exe.lower() or sys.version_info[:2] not in {(3, 11), (3, 12), (3, 13)}:
        for name in ("python3.12", "python3.13", "python3.11", "python3"):
            found = shutil.which(name)
            if found:
                return [found]
    return [exe]


def extra_model_paths_yaml(models_dir: Path) -> str:
    m = str(models_dir).replace("\\", "/")
    return (
        "# written by aice comfy setup\n"
        "aice:\n"
        f"  base_path: {m}\n"
        "  checkpoints: checkpoints\n"
        "  diffusion_models: diffusion_models\n"
        "  unet: unet\n"
        "  text_encoders: text_encoders\n"
        "  clip: text_encoders\n"
        "  vae: vae\n"
        "  loras: loras\n"
        "  upscale_models: upscale_models\n"
    )


class ComfyInstaller:
    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or cfgmod.load_config()
        self.home = cfgmod.comfy_home()
        self.runtime_dir = Path(self.cfg["runtime_dir"])
        self.venv_dir = Path(self.cfg["venv_dir"])
        self.models_dir = Path(self.cfg["models_dir"])
        self.registry = modelmod.load_registry()

    @property
    def venv_python(self) -> Path:
        return self.venv_dir / ("Scripts/python.exe" if _WINDOWS else "bin/python")

    def _pip(self, *args: str, log: Progress | None = None) -> None:
        _run([str(self.venv_python), "-m", "pip", *args], log=log)

    def _default_model_keys(self, profile_name: str) -> list[str]:
        prof = policymod.PROFILES[profile_name]
        specs = modelmod.model_specs(self.registry)
        return list(dict.fromkeys(
            [k for k, s in specs.items() if s.required]
            + [prof.default_model, prof.low_vram_model]
        ))

    def preflight(self, model_keys: list[str] | None = None) -> dict[str, Any]:
        fresh = not (self.runtime_dir / "main.py").exists()
        free_gb = round(modelmod.free_disk_bytes(self.home) / 1e9, 1)
        specs = modelmod.model_specs(self.registry)
        chosen = model_keys or [k for k, s in specs.items() if s.required]
        unknown = [k for k in chosen if k not in specs]
        if unknown:
            raise InstallError(f"unknown model keys: {', '.join(unknown)}")
        missing_bytes = sum(
            specs[k].size_bytes for k in chosen
            if not modelmod.verify(specs[k].dest(self.models_dir), specs[k])[0]
        )
        # Download .part files become the final file by rename, so they do not require
        # double model space. Eight GB covers wheel/cache/extraction and operational slack.
        need_gb = round((missing_bytes + 8e9) / 1e9, 1)
        minimum_gb = max(MIN_FREE_GB_FRESH, need_gb + 5) if fresh else need_gb
        report = {
            "fresh_install": fresh,
            "free_gb": free_gb,
            "estimated_need_gb": need_gb,
            "selected_models": chosen,
            "missing_model_bytes": missing_bytes,
            "git": bool(shutil.which("git")),
            "nvidia_smi": bool(shutil.which("nvidia-smi")),
        }
        if not report["git"]:
            raise InstallError("git is required on PATH")
        if free_gb < minimum_gb:
            raise InstallError(
                f"insufficient disk: {free_gb} GB free, need ~{minimum_gb} GB including temporary headroom. "
                "Free space or set AICE_COMFY_HOME to another drive."
            )
        return report

    def ensure_comfyui(self, log: Progress | None = None) -> str:
        spec = self.registry["comfyui"]
        return _ensure_pinned_repo(spec["repo"], self.runtime_dir, spec["pin"], log=log)

    def ensure_venv(self, log: Progress | None = None) -> None:
        if self.venv_python.exists():
            return
        _run([*_venv_base_python(), "-m", "venv", str(self.venv_dir)], log=log)
        self._pip("install", "-U", "pip", "wheel", log=log)

    def torch_status(self) -> dict[str, Any]:
        if not self.venv_python.exists():
            return {"installed": False}
        try:
            out = _run([
                str(self.venv_python), "-c",
                "import torch,json;print(json.dumps({'v':torch.__version__,"
                "'cuda':torch.version.cuda,'avail':torch.cuda.is_available(),"
                "'dev':(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')}))",
            ])
            return {"installed": True, **json.loads(out.strip().splitlines()[-1])}
        except (InstallError, ValueError):
            return {"installed": False}

    def ensure_torch(self, log: Progress | None = None) -> dict[str, Any]:
        status = self.torch_status()
        if status.get("installed") and status.get("cuda"):
            return status
        t = self.registry["torch"]
        self._pip("install", "--index-url", t["index_url"], *t["packages"], log=log)
        return self.torch_status()

    def ensure_comfy_requirements(self, log: Progress | None = None) -> None:
        req = self.runtime_dir / "requirements.txt"
        if req.exists():
            self._pip("install", "-r", str(req), log=log)

    def ensure_custom_nodes(self, log: Progress | None = None) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        nodes_dir = self.runtime_dir / "custom_nodes"
        nodes_dir.mkdir(parents=True, exist_ok=True)
        for node in self.registry.get("custom_nodes", []):
            target = nodes_dir / node["name"]
            sha = _ensure_pinned_repo(node["repo"], target, node["pin"], log=log)
            req = target / "requirements.txt"
            if req.exists():
                self._pip("install", "-r", str(req), log=log)
            out.append({"name": node["name"], "sha": sha})
        return out

    def ensure_extra_model_paths(self) -> None:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        for sub in ("diffusion_models", "unet", "text_encoders", "vae", "loras",
                    "upscale_models", "checkpoints"):
            (self.models_dir / sub).mkdir(exist_ok=True)
        (self.runtime_dir / "extra_model_paths.yaml").write_text(
            extra_model_paths_yaml(self.models_dir), encoding="utf-8"
        )

    def ensure_models(self, keys: list[str] | None = None, *,
                      progress: Callable[[str, int, int], None] | None = None) -> list[str]:
        specs = modelmod.model_specs(self.registry)
        chosen = keys or [k for k, s in specs.items() if s.required]
        unknown = [k for k in chosen if k not in specs]
        if unknown:
            raise InstallError(f"unknown model keys: {', '.join(unknown)}")
        fetched: list[str] = []
        for key in chosen:
            spec = specs[key]
            dest = spec.dest(self.models_dir)
            if modelmod.verify(dest, spec)[0]:
                continue
            cb = (lambda d, t, _k=key: progress(_k, d, t)) if progress else None
            modelmod.download(spec, dest, progress=cb)
            fetched.append(key)
        return fetched

    def setup(self, *, model_keys: list[str] | None = None, log: Progress | None = None,
              model_progress: Callable[[str, int, int], None] | None = None) -> dict[str, Any]:
        old_pins = dict(self.cfg.get("pins", {}))
        profile_name = policymod.classify(hw.load_cached() or hw.detect())
        if model_keys is None:
            model_keys = self._default_model_keys(profile_name)
        else:
            model_keys = list(dict.fromkeys(model_keys))
        pre = self.preflight(model_keys)
        comfy_sha = self.ensure_comfyui(log)
        self.ensure_venv(log)
        torch = self.ensure_torch(log)
        self.ensure_comfy_requirements(log)
        nodes = self.ensure_custom_nodes(log)
        self.ensure_extra_model_paths()
        fetched = self.ensure_models(model_keys, progress=model_progress)

        new_pins = {
            "comfyui_sha": comfy_sha,
            "comfyui_version": self.registry["comfyui"].get("version", ""),
            "custom_nodes": nodes,
            "torch": torch.get("v", ""),
            "torch_cuda": torch.get("cuda", ""),
        }
        self.cfg["pins"] = new_pins
        self.cfg["profile"] = profile_name
        if old_pins and old_pins != new_pins:
            self.cfg["validated"] = False
        cfgmod.save_config(self.cfg)
        return {
            "preflight": pre,
            "comfyui_sha": comfy_sha,
            "comfyui_version": self.registry["comfyui"].get("version", ""),
            "torch": torch,
            "custom_nodes": nodes,
            "models_fetched": fetched,
            "profile": self.cfg["profile"],
            "validated": bool(self.cfg.get("validated")),
        }
