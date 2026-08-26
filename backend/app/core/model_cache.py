from __future__ import annotations

import os
from pathlib import Path

from .config import get_settings


def configure_local_model_cache() -> Path:
    root = Path(get_settings().local_model_cache_dir).expanduser().resolve()
    huggingface_home = root / "huggingface"
    hub_cache = huggingface_home / "hub"
    transformers_cache = root / "transformers"
    torch_cache = root / "torch"
    tiktoken_cache = root / "tiktoken"

    for path in [root, huggingface_home, hub_cache, transformers_cache, torch_cache, tiktoken_cache]:
        path.mkdir(parents=True, exist_ok=True)

    os.environ["HF_HOME"] = str(huggingface_home)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hub_cache)
    os.environ["HF_HUB_CACHE"] = str(hub_cache)
    os.environ["TRANSFORMERS_CACHE"] = str(transformers_cache)
    os.environ["TORCH_HOME"] = str(torch_cache)
    os.environ["TIKTOKEN_CACHE_DIR"] = str(tiktoken_cache)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    return root
