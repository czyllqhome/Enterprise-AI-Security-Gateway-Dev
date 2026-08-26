from __future__ import annotations

from pathlib import Path

import tiktoken

from app.core.model_cache import configure_local_model_cache


def main() -> None:
    cache_root = configure_local_model_cache()
    encoding = tiktoken.get_encoding("o200k_base")
    encoding.encode("Enterprise AI security scanner asset check.")
    print(f"Scanner tokenizer assets are ready under {Path(cache_root) / 'tiktoken'}")


if __name__ == "__main__":
    main()
