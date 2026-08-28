from __future__ import annotations

import math
from dataclasses import dataclass

from ..providers.base import EffectiveSettings
from .hardware import HardwareProfile

# --- model variants (keys must match comfy/registry.json "models") -----------
# GGUF quant of Qwen-Image-Edit-2509 (city96 ComfyUI-GGUF) + a fused 8-step
# Lightning LoRA. Q4_K_S is the default; Q3_K_M is the tight-VRAM fallback.
QWEN_EDIT_2509_GGUF_Q4KS = "qwen_image_edit_2509_gguf_q4ks"
QWEN_EDIT_2509_GGUF_Q3KM = "qwen_image_edit_2509_gguf_q3km"


@dataclass(frozen=True)
class ModelSamplerProfile:
    steps: int
    cfg: float
    sampler: str
    scheduler: str


# The Lightning-8-step LoRA is baked into the workflow, so every quant samples the
# same way: 8 steps, CFG 1.0 (no true CFG), euler/simple.
MODEL_SAMPLER: dict[str, ModelSamplerProfile] = {
    QWEN_EDIT_2509_GGUF_Q4KS: ModelSamplerProfile(8, 1.0, "euler", "simple"),
    QWEN_EDIT_2509_GGUF_Q3KM: ModelSamplerProfile(8, 1.0, "euler", "simple"),
}

# ~1 MP buckets, every side a multiple of 32 (Qwen VAE stride).
BUCKETS: dict[str, tuple[int, int]] = {
    "portrait": (896, 1216),
    "square": (1024, 1024),
    "full_body": (832, 1216),
    "landscape": (1216, 832),
}


@dataclass(frozen=True)
class HardwarePolicyProfile:
    name: str
    default_model: str
    low_vram_model: str
    server_args: tuple[str, ...]
    vram_floor_mb: int
    vram_headroom_mb: int  # extra margin over floor before we drop to low_vram_model
    max_pixels: int
    upscale_budgets: tuple[str, ...]
    usable: bool = True


PROFILES: dict[str, HardwarePolicyProfile] = {
    # RTX 5070 Laptop, 8 GB: Q3_K_M GGUF default, VAE decode forced to CPU (the
    # GPU decode of a ~1 MP Qwen latent with the text encoder resident overflows
    # 8 GB and crashes the worker). Q4_K_S stays available for the quality budget.
    "rtx_5070_laptop_8gb": HardwarePolicyProfile(
        name="rtx_5070_laptop_8gb",
        default_model=QWEN_EDIT_2509_GGUF_Q3KM,
        low_vram_model=QWEN_EDIT_2509_GGUF_Q3KM,
        server_args=("--lowvram", "--use-pytorch-cross-attention",
                     "--reserve-vram", "0.9", "--cpu-vae"),
        vram_floor_mb=3000,
        vram_headroom_mb=1200,
        max_pixels=1_048_576,
        upscale_budgets=("quality",),
    ),
    "blackwell_8gb": HardwarePolicyProfile(
        name="blackwell_8gb",
        default_model=QWEN_EDIT_2509_GGUF_Q3KM,
        low_vram_model=QWEN_EDIT_2509_GGUF_Q3KM,
        server_args=("--lowvram", "--use-pytorch-cross-attention",
                     "--reserve-vram", "0.9", "--cpu-vae"),
        vram_floor_mb=3000,
        vram_headroom_mb=1200,
        max_pixels=1_048_576,
        upscale_budgets=("quality",),
    ),
    "blackwell_12gb_plus": HardwarePolicyProfile(
        name="blackwell_12gb_plus",
        default_model=QWEN_EDIT_2509_GGUF_Q4KS,
        low_vram_model=QWEN_EDIT_2509_GGUF_Q3KM,
        server_args=("--normalvram", "--use-pytorch-cross-attention"),
        vram_floor_mb=4000,
        vram_headroom_mb=2000,
        max_pixels=1_500_000,
        upscale_budgets=("balanced", "quality"),
    ),
    # Any other NVIDIA card: same GGUF path (pure-torch dequant, no Blackwell kernels needed).
    "nvidia_generic": HardwarePolicyProfile(
        name="nvidia_generic",
        default_model=QWEN_EDIT_2509_GGUF_Q3KM,
        low_vram_model=QWEN_EDIT_2509_GGUF_Q3KM,
        server_args=("--lowvram", "--use-pytorch-cross-attention", "--cpu-vae"),
        vram_floor_mb=3400,
        vram_headroom_mb=1400,
        max_pixels=1_048_576,
        upscale_budgets=("quality",),
    ),
    "cpu_or_unknown": HardwarePolicyProfile(
        name="cpu_or_unknown",
        default_model=QWEN_EDIT_2509_GGUF_Q3KM,
        low_vram_model=QWEN_EDIT_2509_GGUF_Q3KM,
        server_args=(),
        vram_floor_mb=999_999,
        vram_headroom_mb=0,
        max_pixels=768 * 768,
        upscale_budgets=(),
        usable=False,
    ),
}


def classify(hw: HardwareProfile) -> str:
    if not hw.has_gpu:
        return "cpu_or_unknown"
    name = hw.gpu_name.lower()
    if hw.is_blackwell:
        if "5070" in name and "laptop" in name and hw.vram_total_mb <= 9216:
            return "rtx_5070_laptop_8gb"
        return "blackwell_8gb" if hw.vram_total_mb <= 9216 else "blackwell_12gb_plus"
    return "nvidia_generic"


def profile_for(hw: HardwareProfile) -> HardwarePolicyProfile:
    return PROFILES[classify(hw)]


def server_args(hw: HardwareProfile) -> tuple[str, ...]:
    return profile_for(hw).server_args


def _aspect_from_scene(aspect: str, scene_tags: tuple[str, ...]) -> str:
    tags = set(scene_tags)
    if {"full_body", "legs"} & tags:
        return "full_body"
    if aspect in BUCKETS:
        return aspect
    if "face" in tags and "upper_body" not in tags:
        return "portrait"
    return "portrait"


def _fit_pixels(w: int, h: int, max_pixels: int) -> tuple[int, int]:
    if w * h <= max_pixels:
        return w, h
    scale = math.sqrt(max_pixels / (w * h))
    return (max(256, int(w * scale) // 32 * 32), max(256, int(h * scale) // 32 * 32))


def resolve_settings(
    hw: HardwareProfile,
    *,
    aspect: str = "portrait",
    budget: str = "balanced",
    scene_tags: tuple[str, ...] = (),
    ref_count: int = 1,
    free_vram_mb: int | None = None,
    tuned_model: str | None = None,
) -> EffectiveSettings:
    profile = profile_for(hw)
    tight_vram = (
        free_vram_mb is not None
        and free_vram_mb < profile.vram_floor_mb + profile.vram_headroom_mb
    )
    use_low = budget == "economy" or tight_vram or ref_count >= 3 and budget != "quality"
    # A passing smoke/bench may pin a machine-measured default (comfy.json "tuned").
    base_model = tuned_model if tuned_model in MODEL_SAMPLER else profile.default_model
    model_id = profile.low_vram_model if use_low else base_model
    sampler = MODEL_SAMPLER[model_id]

    w, h = BUCKETS[_aspect_from_scene(aspect, scene_tags)]
    w, h = _fit_pixels(w, h, profile.max_pixels)

    return EffectiveSettings(
        model_id=model_id,
        steps=sampler.steps,
        cfg=sampler.cfg,
        sampler=sampler.sampler,
        scheduler=sampler.scheduler,
        width=w,
        height=h,
        batch_size=1,
        upscale=budget in profile.upscale_budgets,
        vram_flags=profile.server_args,
    )
