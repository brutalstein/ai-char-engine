from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

from ..comfy import config as cfgmod
from ..comfy import hardware as hwmod
from ..comfy import models as modelmod
from ..comfy import policy as policymod
from ..comfy.client import ComfyError
from ..comfy.runtime import ComfyRuntime
from ..comfy.workflow import WorkflowAdapter, WorkflowError
from ..utils import sha256_file, utc_now
from .base import GenerationRequest, GenerationResult, ImageProvider
from .router import BackendProbe

_MAX_RECOVERIES = 1


class ComfyUIProvider(ImageProvider):
    name = "comfyui"

    def __init__(self, *, config: dict[str, Any] | None = None,
                 runtime: ComfyRuntime | None = None,
                 hardware: hwmod.HardwareProfile | None = None,
                 workflow: WorkflowAdapter | None = None):
        self.cfg = config or cfgmod.load_config()
        self.runtime = runtime or ComfyRuntime(self.cfg)
        self.hw = hardware or hwmod.load_cached() or hwmod.detect()
        self.workflow = workflow or WorkflowAdapter("qwen_edit_identity")
        self.models_dir = Path(self.cfg["models_dir"])

    # -- routing support -------------------------------------------
    def available(self) -> tuple[bool, str]:
        if not self.runtime.is_installed():
            return False, "ComfyUI runtime not installed"
        if not policymod.profile_for(self.hw).usable:
            return False, "no usable GPU detected"
        missing = modelmod.missing_required(self.models_dir)
        if missing:
            return False, f"missing model files: {', '.join(missing)}"
        return True, "ready"

    def probe(self) -> BackendProbe:
        installed = self.runtime.is_installed()
        missing = modelmod.missing_required(self.models_dir) if installed else ["*"]
        nodes_ok = bool(self.cfg.get("pins", {}).get("custom_nodes"))
        status = self.runtime.status() if installed else {"healthy": False}
        free_vram = None
        if status.get("healthy"):
            free_vram = hwmod.free_vram_from_system_stats(self.runtime.system_stats())
        return BackendProbe(
            installed=installed,
            configured=bool(self.cfg.get("pins")),
            validated=bool(self.cfg.get("validated")),
            models_present=not missing,
            nodes_present=nodes_ok,
            server_ok=bool(status.get("healthy")),
            can_start=installed,
            free_vram_mb=free_vram,
            vram_floor_mb=policymod.profile_for(self.hw).vram_floor_mb,
        )

    # -- generation ----------------------------------------------
    def generate(self, req: GenerationRequest) -> GenerationResult:
        started = time.monotonic()
        try:
            return self._generate_once(req, started)
        except (ComfyError, WorkflowError) as exc:
            recovered = self._recover(exc)
            if recovered is None:
                return GenerationResult(
                    backend=self.name, status="failed", error=str(exc),
                    duration_s=time.monotonic() - started,
                )
            try:
                result = self._generate_once(req, started)
                result.warnings.append(f"recovered after: {exc}")
                return result
            except (ComfyError, WorkflowError) as exc2:
                return GenerationResult(
                    backend=self.name, status="failed", error=str(exc2),
                    duration_s=time.monotonic() - started,
                )

    def _recover(self, exc: Exception) -> str | None:
        """One bounded recovery attempt: free VRAM, restart once if the server died."""
        try:
            if not self.runtime.health(timeout=3.0):
                self.runtime.restart(policymod.server_args(self.hw), timeout=240)
                return "restarted server"
            self.runtime.client().free()
            time.sleep(2.0)
            return "freed VRAM"
        except (ComfyError, OSError):
            return None

    def _generate_once(self, req: GenerationRequest, started: float) -> GenerationResult:
        self.runtime.start(policymod.server_args(self.hw), wait=True, timeout=240)
        client = self.runtime.client()

        free_vram = hwmod.free_vram_from_system_stats(client.system_stats())
        refs = list(req.capped_references())
        settings = policymod.resolve_settings(
            self.hw, aspect=req.aspect, budget=req.budget,
            scene_tags=tuple(req.scene_tags), ref_count=len(refs), free_vram_mb=free_vram,
            tuned_model=self.cfg.get("tuned", {}).get("default_model"),
        )
        spec = modelmod.model_specs()[settings.model_id]
        model_dest = spec.dest(self.models_dir)
        if not modelmod.verify(model_dest, spec)[0]:
            raise WorkflowError(f"model {settings.model_id} not installed ({spec.filename})")

        uploaded = [client.upload_image(Path(p))["name"] for p in refs]
        seed = req.seed if req.seed is not None else random.randint(1, 2**31 - 1)

        graph = self.workflow.render(
            positive=req.prompt, negative=req.negative, model_path=spec.filename,
            width=settings.width, height=settings.height, seed=seed, steps=settings.steps,
            cfg=settings.cfg, sampler=settings.sampler, scheduler=settings.scheduler,
            reference_names=uploaded,
            output_prefix=f"AICE_{req.character}",
        )
        self.workflow.validate(client.object_info_keys())

        prompt_id = client.submit(graph)
        history = client.wait(prompt_id, timeout=600, poll=1.5, alive=self.runtime.alive)
        images = client.image_outputs(history)
        if not images:
            raise ComfyError("workflow finished with no image output")

        out_dir = Path(req.out_dir) if req.out_dir else (cfgmod.comfy_home() / "output")
        out_dir.mkdir(parents=True, exist_ok=True)
        img = images[0]
        data = client.fetch_image(img["filename"], img.get("subfolder", ""), img.get("type", "output"))
        out_path = out_dir / f"{Path(img['filename']).stem}.png"
        out_path.write_bytes(data)

        return GenerationResult(
            backend=self.name,
            output_path=out_path,
            model_id=settings.model_id,
            workflow_version=self.workflow.version,
            seed=seed,
            duration_s=time.monotonic() - started,
            effective_settings=settings.as_dict(),
            warnings=[],
            reproducibility={
                "model_file": spec.filename,
                "model_sha256": spec.sha256,
                "workflow": self.workflow.name,
                "workflow_hash": self.workflow.workflow_hash(),
                "reference_names": uploaded,
                "output_sha256": sha256_file(out_path),
                "free_vram_mb_at_start": free_vram,
                "generated_at": utc_now(),
            },
        )
