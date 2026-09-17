"""PriceWatch data loader.

Loads scored price-verdict items from the split directories under
``data/pricewatch_split/{train,val,test}/items.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from skillopt.datasets.base import SplitDataLoader


class PriceWatchDataLoader(SplitDataLoader):
    """Load PriceWatch verdict items from a JSON file in each split dir."""

    def load_split_items(self, split_path: str) -> list[dict]:
        path = Path(split_path) / "items.json"
        if not path.exists():
            raise FileNotFoundError(f"No items.json in {split_path}")
        return json.loads(path.read_text(encoding="utf-8"))
