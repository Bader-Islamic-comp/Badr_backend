"""Explicit synthetic-only configuration. No production mode exists yet."""
from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class Settings:
    demo_mode: bool = False
    demo_token: str = field(default="", repr=False)

    @classmethod
    def from_environment(cls):
        return cls(os.getenv("COMPANION_DEMO_MODE") == "true", os.getenv("COMPANION_DEMO_TOKEN", ""))

    def require_demo(self):
        if not self.demo_mode or len(self.demo_token) < 24 or not self.demo_token.isascii():
            raise RuntimeError("Synthetic demo requires COMPANION_DEMO_MODE=true and an ASCII operator token of at least 24 characters.")

