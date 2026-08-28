from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

_ASSET_ROOT = Path(__file__).resolve().parents[1] / "workflows"


class WorkflowError(RuntimeError):
    pass


class WorkflowAdapter:
    """Versioned API graph + semantic slots.

    Calling code never depends on node ids. Profiles may represent reference-driven
    edit workflows or no-reference bootstrap workflows with the same adapter.
    """

    def __init__(self, name: str = "qwen_edit_identity"):
        base = _ASSET_ROOT / name
        try:
            self.graph: dict[str, Any] = json.loads((base / "workflow_api.json").read_text("utf-8"))
            self.profile: dict[str, Any] = json.loads((base / "profile.json").read_text("utf-8"))
        except FileNotFoundError as exc:
            raise WorkflowError(f"workflow asset {name!r} not found: {exc}") from None
        self.name = name

    @property
    def version(self) -> str:
        return str(self.profile.get("version", "0"))

    @property
    def requires_references(self) -> bool:
        return bool(self.profile.get("requires_references", bool(self.profile.get("reference_slots"))))

    def workflow_hash(self) -> str:
        blob = json.dumps(self.graph, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    def missing_nodes(self, object_info_keys: set[str]) -> list[str]:
        required = set(self.profile.get("required_class_types", []))
        present_in_graph = {n["class_type"] for n in self.graph.values()}
        need = required | present_in_graph
        return sorted(n for n in need if n not in object_info_keys)

    def validate(self, object_info_keys: set[str]) -> None:
        missing = self.missing_nodes(object_info_keys)
        if missing:
            raise WorkflowError(
                "ComfyUI is missing node types required by workflow "
                f"{self.name} v{self.version}: {', '.join(missing)}. "
                "Run `aice comfy setup` to install/repair custom nodes."
            )

    def render(
        self,
        *,
        positive: str,
        negative: str = "",
        model_path: str,
        width: int,
        height: int,
        seed: int,
        steps: int,
        cfg: float,
        sampler: str,
        scheduler: str,
        reference_names: list[str] | None = None,
        lora_name: str | None = None,
        ipadapter_weight: float | None = None,
        ipadapter_file: str | None = None,
        clip_vision_file: str | None = None,
        output_prefix: str = "AICE",
    ) -> dict[str, Any]:
        reference_names = list(reference_names or [])
        if self.requires_references and not reference_names:
            raise WorkflowError(f"workflow {self.name} requires at least one reference image")

        graph = copy.deepcopy(self.graph)
        slots = self.profile.get("slots", {})
        ref_slots = self.profile.get("reference_slots", [])
        enc_nodes = self.profile.get("text_encoder_nodes", [])
        values: dict[str, Any] = {
            "model_path": model_path,
            "positive_prompt": positive,
            "negative_prompt": negative,
            "width": int(width),
            "height": int(height),
            "seed": int(seed),
            "steps": int(steps),
            "cfg": float(cfg),
            "sampler": sampler,
            "scheduler": scheduler,
            "output_prefix": output_prefix,
        }
        if lora_name is not None:
            values["lora_name"] = lora_name
        if ipadapter_weight is not None:
            values["ipadapter_weight"] = float(ipadapter_weight)
        if ipadapter_file is not None:
            values["ipadapter_file"] = ipadapter_file
        if clip_vision_file is not None:
            values["clip_vision_file"] = clip_vision_file

        for key, value in values.items():
            spec = slots.get(key)
            if not spec:
                continue
            node = graph.get(spec["node"])
            if node is None:
                raise WorkflowError(f"slot {key!r} points at missing node {spec['node']}")
            node["inputs"][spec["input"]] = value

        keep = min(len(reference_names), len(ref_slots))
        for i, slot in enumerate(ref_slots):
            if i < keep:
                graph[slot["load"]]["inputs"]["image"] = reference_names[i]
            else:
                graph.pop(slot["load"], None)
                graph.pop(slot["scale"], None)
                for enc in enc_nodes:
                    if enc in graph:
                        graph[enc]["inputs"].pop(slot["enc_input"], None)
        return graph
