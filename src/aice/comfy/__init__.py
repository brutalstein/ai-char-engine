"""Local ComfyUI runtime + HTTP API integration.

This package is deliberately stdlib-only (urllib, http.client, subprocess, socket).
It manages a *separate* ComfyUI install under ``~/.aice/runtime`` and never imports
torch or ComfyUI into the aice process.
"""
