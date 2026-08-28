from __future__ import annotations

import random
import time
from dataclasses import replace
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
from .base import (
    GenerationRequest,
    GenerationResult,
    ImageProvider,
    ProgressCallback,
    ProviderCapabilities,
    emit_progress,
)
from .router import BackendProbe

_BOOTSTRAP_MODEL = "qwen_image_t2i_gguf_q3km"
_BOOTSTRAP_LORA = "qwen_image_t2i_lightning_8step"

# Local explicit-adult profile (see comfy/registry.json capability "adult_explicit").
_ADULT_MODEL = "lustify_sdxl_v4"
_ADULT_IPADAPTER = "ip_adapter_plus_sdxl_vith"
_ADULT_CLIP_VISION = "clip_vision_vith"
_ADULT_NODE = "ComfyUI_IPAdapter_plus"
_ADULT_WORKFLOW = "lustify_sdxl_adult"


class ComfyUIProvider(ImageProvider):
    name = "comfyui"

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        runtime: ComfyRuntime | None = None,
        hardware: hwmod.HardwareProfile | None = None,
        workflow: WorkflowAdapter | None = None,
    ):
        self.cfg = config or cfgmod.load_config()
        self.runtime = runtime or ComfyRuntime(self.cfg)
        self.hw = hardware or hwmod.load_cached() or hwmod.detect()
        self.workflow = workflow or WorkflowAdapter("qwen_edit_identity")
        self.models_dir = Path(self.cfg["models_dir"])

    def _base_available(self) -> tuple[bool, str]:
        if not self.runtime.is_installed():
            return False, "ComfyUI runtime not installed"
        if not policymod.profile_for(self.hw).usable:
            return False, "no usable GPU detected"
        return True, "ready"

    def available(self) -> tuple[bool, str]:
        ok, why = self._base_available()
        if not ok:
            return ok, why
        missing = modelmod.capability_missing(self.models_dir, "identity")
        if missing:
            return False, f"missing identity model files: {', '.join(missing)}"
        return True, "ready"

    def bootstrap_available(self) -> tuple[bool, str]:
        ok, why = self._base_available()
        if not ok:
            return ok, why
        missing = modelmod.capability_missing(self.models_dir, "bootstrap")
        if missing:
            return False, f"local bootstrap not installed: {', '.join(missing)}"
        return True, "ready"

    def _adult_node_present(self) -> bool:
        nodes = self.cfg.get("pins", {}).get("custom_nodes", []) or []
        return any(str(n.get("name")) == _ADULT_NODE for n in nodes)

    def adult_available(self) -> tuple[bool, str]:
        """Readiness of the local explicit-adult profile (LUSTIFY SDXL + IP-Adapter)."""
        ok, why = self._base_available()
        if not ok:
            return ok, why
        missing = modelmod.capability_missing(self.models_dir, "adult_explicit")
        if missing:
            return False, f"local adult model not installed: {', '.join(missing)}"
        if not self._adult_node_present():
            return False, f"required custom node missing: {_ADULT_NODE}"
        return True, "ready"

    def capabilities(self) -> ProviderCapabilities:
        bootstrap, _ = self.bootstrap_available()
        adult, _ = self.adult_available()
        return ProviderCapabilities(
            provider=self.name,
            bootstrap_without_reference=bootstrap,
            identity_generation=True,
            reference_expansion=True,
            targeted_repair=True,
            multi_reference=True,
            max_references=3,
            local=True,
            privacy="localhost_only",
            adult_explicit_generation=adult,
        )

    def available_for(self, req: GenerationRequest) -> tuple[bool, str]:
        if req.operation == "bootstrap":
            return self.bootstrap_available()
        if req.explicit == "explicit":
            return self.adult_available()
        return super().available_for(req)

    def probe(self) -> BackendProbe:
        installed = self.runtime.is_installed()
        missing = modelmod.capability_missing(self.models_dir, "identity") if installed else ["*"]
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

    def generate(self, req: GenerationRequest, *, progress: ProgressCallback | None = None) -> GenerationResult:
        started = time.monotonic()
        try:
            return self._generate_once(req, started, progress)
        except (ComfyError, WorkflowError) as exc:
            emit_progress(progress, "recovering", backend=self.name, reason=str(exc))
            recovered = self._recover()
            if recovered is None:
                emit_progress(progress, "provider_failed", backend=self.name, error=str(exc))
                return GenerationResult(
                    backend=self.name,
                    status="failed",
                    error=str(exc),
                    duration_s=time.monotonic() - started,
                )
            try:
                result = self._generate_once(req, started, progress)
                result.warnings.append(f"recovered after: {exc}")
                return result
            except (ComfyError, WorkflowError) as exc2:
                emit_progress(progress, "provider_failed", backend=self.name, error=str(exc2))
                return GenerationResult(
                    backend=self.name,
                    status="failed",
                    error=str(exc2),
                    duration_s=time.monotonic() - started,
                )

    def _recover(self) -> str | None:
        try:
            if not self.runtime.health(timeout=3.0):
                self.runtime.restart(policymod.server_args(self.hw), timeout=240)
                return "restarted server"
            self.runtime.client().free()
            time.sleep(2.0)
            return "freed VRAM"
        except (ComfyError, OSError):
            return None

    def _workflow_and_model(self, req: GenerationRequest):
        """Return (workflow, override_spec | None, lora_filename | None).

        ``override_spec`` forces a specific checkpoint/unet for a non-default
        operation (bootstrap or explicit-adult); ``None`` keeps the tuned Qwen
        identity model resolved by policy.
        """
        if req.operation == "bootstrap":
            ok, why = self.bootstrap_available()
            if not ok:
                raise WorkflowError(why)
            specs = modelmod.model_specs()
            return (
                WorkflowAdapter("qwen_text_to_image"),
                specs[_BOOTSTRAP_MODEL],
                specs[_BOOTSTRAP_LORA].filename,
            )
        if req.explicit == "explicit":
            ok, why = self.adult_available()
            if not ok:
                raise WorkflowError(why)
            return WorkflowAdapter(_ADULT_WORKFLOW), modelmod.model_specs()[_ADULT_MODEL], None
        return self.workflow, None, None

    def _generate_once(
        self,
        req: GenerationRequest,
        started: float,
        progress: ProgressCallback | None,
    ) -> GenerationResult:
        ready, why = self.available_for(req)
        if not ready:
            raise WorkflowError(why)

        is_adult = req.explicit == "explicit"
        emit_progress(progress, "local_backend_starting", backend=self.name,
                      operation=req.operation, explicit=is_adult)
        self.runtime.start(policymod.server_args(self.hw), wait=True, timeout=240)
        client = self.runtime.client()
        free_vram = hwmod.free_vram_from_system_stats(client.system_stats())

        max_refs = policymod.ADULT_MAX_REFERENCES if is_adult else (2 if req.repair_of else 3)
        identity_refs = list(req.capped_reference_inputs(max_refs))
        ref_metadata = [ref.as_dict() for ref in identity_refs]
        upload_paths: list[Path] = []
        edit_target_name: str | None = None
        if req.repair_of is not None and not is_adult:
            upload_paths.append(Path(req.repair_of))
        upload_paths.extend(ref.path for ref in identity_refs)

        workflow, override_spec, bootstrap_lora = self._workflow_and_model(req)
        if is_adult:
            specs = modelmod.model_specs()
            spec = specs[_ADULT_MODEL]
            ip_spec, cv_spec = specs[_ADULT_IPADAPTER], specs[_ADULT_CLIP_VISION]
            settings = policymod.resolve_adult_settings(
                self.hw, aspect=req.aspect, scene_tags=tuple(req.scene_tags),
                free_vram_mb=free_vram,
            )
            negative = policymod.SDXL_NEGATIVE_BASELINE + (f"; {req.negative}" if req.negative else "")
        else:
            ip_spec = cv_spec = None
            negative = req.negative
            settings = policymod.resolve_settings(
                self.hw,
                aspect=req.aspect,
                budget=req.budget,
                scene_tags=tuple(req.scene_tags),
                ref_count=len(upload_paths),
                free_vram_mb=free_vram,
                tuned_model=self.cfg.get("tuned", {}).get("default_model"),
            )
            if override_spec is not None:
                settings = replace(settings, model_id=override_spec.key)
                spec = override_spec
            else:
                spec = modelmod.model_specs()[settings.model_id]

        emit_progress(
            progress,
            "settings_resolved",
            backend=self.name,
            model=settings.model_id,
            width=settings.width,
            height=settings.height,
            reference_count=len(identity_refs),
            operation=req.operation,
            explicit=is_adult,
        )
        model_dest = spec.dest(self.models_dir)
        if not modelmod.verify(model_dest, spec)[0]:
            raise WorkflowError(f"model {settings.model_id} not installed ({spec.filename})")

        uploaded: list[str] = []
        if upload_paths:
            emit_progress(progress, "references_uploading", backend=self.name, count=len(upload_paths))
            uploaded = [client.upload_image(path)["ref"] for path in upload_paths]
            if req.repair_of is not None and not is_adult:
                edit_target_name = uploaded[0]

        render_refs = list(uploaded)
        if is_adult and len(render_refs) == 1:
            # The IP-Adapter ImageBatch node needs two inputs; feed the lone
            # reference twice (an identical embed, no identity change).
            render_refs = render_refs * 2

        seed = req.seed if req.seed is not None else random.randint(1, 2**31 - 1)
        emit_progress(progress, "workflow_preparing", backend=self.name, workflow=workflow.name)
        graph = workflow.render(
            positive=req.prompt,
            negative=negative,
            model_path=spec.filename,
            width=settings.width,
            height=settings.height,
            seed=seed,
            steps=settings.steps,
            cfg=settings.cfg,
            sampler=settings.sampler,
            scheduler=settings.scheduler,
            reference_names=render_refs,
            lora_name=bootstrap_lora,
            ipadapter_weight=settings.ipadapter_weight if is_adult else None,
            ipadapter_file=ip_spec.filename if ip_spec else None,
            clip_vision_file=cv_spec.filename if cv_spec else None,
            output_prefix=f"AICE_{req.character}_{'adult' if is_adult else req.operation}",
        )
        workflow.validate(client.object_info_keys())

        prompt_id = client.submit(graph)
        emit_progress(progress, "workflow_submitted", backend=self.name, prompt_id=prompt_id)
        emit_progress(progress, "rendering", backend=self.name, operation=req.operation)
        history = client.wait(prompt_id, timeout=600, poll=1.5, alive=self.runtime.alive)
        images = client.image_outputs(history)
        if not images:
            raise ComfyError("workflow finished with no image output")

        emit_progress(progress, "output_fetching", backend=self.name)
        out_dir = Path(req.out_dir) if req.out_dir else (cfgmod.comfy_home() / "output")
        out_dir.mkdir(parents=True, exist_ok=True)
        img = images[0]
        data = client.fetch_image(img["filename"], img.get("subfolder", ""), img.get("type", "output"))
        out_path = out_dir / f"{Path(img['filename']).stem}.png"
        out_path.write_bytes(data)

        result = GenerationResult(
            backend=self.name,
            output_path=out_path,
            model_id=settings.model_id,
            workflow_version=workflow.version,
            seed=seed,
            duration_s=time.monotonic() - started,
            effective_settings={**settings.as_dict(), "operation": req.operation,
                                "explicit": req.explicit},
            warnings=[],
            reproducibility={
                "operation": req.operation,
                "explicit": req.explicit,
                "model_file": spec.filename,
                "model_sha256": spec.sha256,
                "workflow": workflow.name,
                "workflow_hash": workflow.workflow_hash(),
                "reference_ids": [row["id"] for row in ref_metadata],
                "reference_roles": [row["role"] for row in ref_metadata],
                "reference_origins": [row.get("origin_provider", "unknown") for row in ref_metadata],
                "reference_names": uploaded[1:] if edit_target_name else uploaded,
                "edit_target_name": edit_target_name,
                "output_sha256": sha256_file(out_path),
                "free_vram_mb_at_start": free_vram,
                "generated_at": utc_now(),
                **({
                    "identity_method": "ip-adapter-plus-sdxl-vit-h",
                    "ipadapter_file": ip_spec.filename,
                    "ipadapter_sha256": ip_spec.sha256,
                    "clip_vision_file": cv_spec.filename,
                    "ipadapter_weight": settings.ipadapter_weight,
                } if is_adult else {}),
            },
        )
        emit_progress(
            progress,
            "provider_complete",
            backend=self.name,
            output_path=str(out_path),
            duration_s=round(result.duration_s, 2),
            operation=req.operation,
        )
        return result
