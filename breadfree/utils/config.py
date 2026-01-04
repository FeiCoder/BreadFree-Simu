"""
配置加载器：在候选路径查找 `config.yaml` 并缓存加载结果。
用法：
from breadfree.utils.config import get, get_config
cfg = get_config()
symbol = get('symbol', '518850')
"""
from __future__ import annotations

import os
from typing import Any, Dict
import yaml

_loaded_config: Dict[str, Any] | None = None
_loaded_path: str | None = None


def _search_config_paths() -> list[str]:
    here = os.path.dirname(__file__)
    candidates = [
        os.path.normpath(os.path.join(here, "..", "config.yaml")),
        os.path.normpath(os.path.join(here, "..", "..", "config.yaml")),
        os.path.normpath(os.path.join(here, "..", "..", "breadfree", "config.yaml")),
    ]
    seen = set()
    out = []
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def load_config() -> dict:
    global _loaded_config, _loaded_path
    if _loaded_config is not None:
        return _loaded_config

    for p in _search_config_paths():
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    cfg = yaml.safe_load(f) or {}
                    _loaded_config = cfg
                    _loaded_path = p
                    return _loaded_config
            except Exception:
                continue

    _loaded_config = {}
    return _loaded_config


def get_config() -> dict:
    return load_config()


def get(key: str, default: Any = None) -> Any:
    cfg = load_config()
    return cfg.get(key, default)


def get_loaded_path() -> str | None:
    load_config()
    return _loaded_path
