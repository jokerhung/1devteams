import time

import yaml

from app.core.config import BACKEND_ROOT


class ModelsCatalog:
    def __init__(self):
        self.observed: dict[str, list[dict]] = {}
        self.cached: dict = {}
        self.expires = 0.0

    def observe(self, runtime: str, models: list[dict]) -> None:
        self.observed[runtime] = models
        self.expires = 0

    def get(self) -> dict:
        if time.monotonic() < self.expires:
            return self.cached
        data = yaml.safe_load((BACKEND_ROOT / "config/models_catalog.yaml").read_text(encoding="utf-8"))
        for runtime, models in self.observed.items():
            known = {item["id"]: item for item in data.get(runtime, [])}
            for item in models:
                key = item.get("modelId") or item.get("value") or item.get("id")
                if key:
                    known[key] = {"id": key, "label": item.get("name", key)}
            data[runtime] = list(known.values())
        self.cached, self.expires = data, time.monotonic() + 600
        return data
