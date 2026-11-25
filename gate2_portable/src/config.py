"""Minimal settings for the bundled core: only what src/pricesheet reads."""
import os
from types import SimpleNamespace


def get_settings():
    return SimpleNamespace(
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        review_nguoi_xu_ly_password="",  # empty = review roles disabled
        review_ke_toan_password="",
    )
