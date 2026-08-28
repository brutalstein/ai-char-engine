from __future__ import annotations

import math
from dataclasses import dataclass

from ..providers.base import EffectiveSettings
from .hardware import HardwareProfile

# --- model variants (keys must match comfy/registry.json "models") -----------
# GGUF quantizations of Qwen-Image-Edit-2509. Real 8 GB smoke testing selected
# Q3_K_M + CPU VAE decode as the safe target-machine default. Q4_K_S remains an
# optional/tuned model for machines where measured headroom supports it.
QWEN_EDIT_2509_GGUF_Q4KS = "qwen_image_edit_2509_gguf_q4ks"
QWEN_EDIT_2509_GGUF_Q3KM = "qwen_image_edit_2509_gguf_q3km"

# --- explicit-adult profile: LUSTIFY! SDXL v4 -------------------------------
# One fp16 SDXL checkpoint (no quant tiers). Identity is supplied by IP-Adapter
# Plus (ViT-H) from 1-2 trusted references, so this path shares the same 8 GB
# server flags as the Qwen path (--lowvram / --reserve-vram / --cpu-vae): the
# checkpoint + CLIP-Vision + IP-Adapter fit only with sequential CPU offload and
# a CPU VAE decode. Priorities: identity > photorealism > reliability > speed.
LUSTIFY_SDXL_V4 = "lustify_sdxl_v4"

# SDXL likes ~30 steps of a 2nd-order sampler; DPM++ 2M / Karras is the most
# broadly reliable photoreal combination for this model family. CFG 5.0 sits in
# the middle of LUSTIFY's recommended 3-7 band: enough prompt adherence without
# the contrast/plastic look higher CFG gives on skin.
SDXL_STEPS = 30
SDXL_CFG = 5.0
SDXL_SAMPLER_NAME = "dpmpp_2m"
SDXL_SCHEDULER = "karras"

# SDXL native buckets, every side a multiple of 64, each <= 1 MP so an 8 GB card
# never has to tile. Portrait is the safe default for a single-subject photo.
SDXL_BUCKETS: dict[str, tuple[int, int]] = {
    "portrait": (832, 1216),
    "square": (1024, 1024),
    "full_body": (832, 1216),
    "landscape": (1216, 832),
}

# A short, model-appropriate negative. SDXL does not need SD1.5-length lists; this
# steers away from non-photographic renders, gross anatomy failures, and - as a
# deliberate safety measure - youthful appearance.
SDXL_NEGATIVE_BASELINE = (
    "cartoon, anime, illustration, 3d render, cgi, painting, drawing, sketch, "
    "deformed, disfigured, bad anatomy, extra limbs, extra fingers, fused fingers, "
    "mutated hands, malformed, watermark, signature, text, logo, blurry, lowres, "
    "low quality, jpeg artifacts, plastic skin, airbrushed, "
    "child, childlike, teen, teenager, underage, shota, loli"
)

# IP-Adapter identity weight by scene. A tight portrait can carry a strong face
# lock; a full-body / wide scene needs a lower weight so the model still owns
# body proportions, wardrobe and environment.
_IPADAPTER_WEIGHT = {"portrait": 0.75, "square": 0.72, "full_body": 0.55, "landscape": 0.55}
# Practical default reference count for IP-Adapter identity: 1-2 images. More than
# two dilutes the identity embedding rather than strengthening it.
ADULT_MAX_REFERENCES = 2


@dataclass(frozen=True)
class ModelSamplerProfile:
    steps: int
    cfg: float
    sampler: str
    scheduler: str


# The Lightning-8-step LoRA is part of the workflow, so every quant samples the
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
    vram_headroom_mb: int
    max_pixels: int
    # Reserved for a future workflow that actually implements an upscale pass.
    # Keep empty today so generation metadata never claims an operation that did not run.
    upscale_budgets: tuple[str, ...]
    usable: bool = True


PROFILES: dict[str, HardwarePolicyProfile] = {
    "rtx_5070_laptop_8gb": HardwarePolicyProfile(
        name="rtx_5070_laptop_8gb",
        default_model=QWEN_EDIT_2509_GGUF_Q3KM,
        low_vram_model=QWEN_EDIT_2509_GGUF_Q3KM,
        server_args=("--lowvram", "--use-pytorch-cross-attention",
                     "--reserve-vram", "0.9", "--cpu-vae"),
        vram_floor_mb=3000,
        vram_headroom_mb=1200,
        max_pixels=1_048_576,
        upscale_budgets=(),
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
        upscale_budgets=(),
    ),
    "blackwell_12gb_plus": HardwarePolicyProfile(
        name="blackwell_12gb_plus",
        default_model=QWEN_EDIT_2509_GGUF_Q4KS,
        low_vram_model=QWEN_EDIT_2509_GGUF_Q3KM,
        server_args=("--normalvram", "--use-pytorch-cross-attention"),
        vram_floor_mb=4000,
        vram_headroom_mb=2000,
        max_pixels=1_500_000,
        upscale_budgets=(),
    ),
    "nvidia_generic": HardwarePolicyProfile(
        name="nvidia_generic",
        default_model=QWEN_EDIT_2509_GGUF_Q3KM,
        low_vram_model=QWEN_EDIT_2509_GGUF_Q3KM,
        server_args=("--lowvram", "--use-pytorch-cross-attention", "--cpu-vae"),
        vram_floor_mb=3400,
        vram_headroom_mb=1400,
        max_pixels=1_048_576,
        upscale_budgets=(),
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


def adult_ipadapter_weight(aspect: str, scene_tags: tuple[str, ...] = ()) -> float:
    return _IPADAPTER_WEIGHT.get(_aspect_from_scene(aspect, scene_tags), 0.7)


def resolve_adult_settings(
    hw: HardwareProfile,
    *,
    aspect: str = "portrait",
    scene_tags: tuple[str, ...] = (),
    free_vram_mb: int | None = None,
) -> EffectiveSettings:
    """Deterministic LUSTIFY SDXL settings for the local explicit-adult profile.

    One checkpoint, one sampler profile; the only scene-dependent knobs are the
    resolution bucket and the IP-Adapter identity weight. Server flags come from
    the shared hardware profile because the ComfyUI server is process-global.
    """
    profile = profile_for(hw)
    w, h = SDXL_BUCKETS[_aspect_from_scene(aspect, scene_tags)]
    w, h = _fit_pixels(w, h, min(profile.max_pixels, 1_048_576))
    return EffectiveSettings(
        model_id=LUSTIFY_SDXL_V4,
        steps=SDXL_STEPS,
        cfg=SDXL_CFG,
        sampler=SDXL_SAMPLER_NAME,
        scheduler=SDXL_SCHEDULER,
        width=w,
        height=h,
        batch_size=1,
        upscale=False,
        vram_flags=profile.server_args,
        ipadapter_weight=adult_ipadapter_weight(aspect, scene_tags),
    )
