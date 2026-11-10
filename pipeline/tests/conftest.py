import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))

from statsapp_pipeline.common import Context  # noqa: E402


@pytest.fixture
def make_ctx(tmp_path):
    """A Context writing into a temporary copy of backend/data, with downloads switched off."""
    data = tmp_path / "data"
    data.mkdir()
    for name in ("contract.json", "sources.json"):
        shutil.copy(ROOT / "data" / name, data / name)
    (data / "manifest.json").write_text(json.dumps({"datasets": {}}))
    manual = tmp_path / "manual"

    def make(source, **kw):
        kw.setdefault("min_records", 1)
        return Context(source, data_dir=data, raw_dir=tmp_path / "raw", manual_dir=manual, offline=True, log=lambda *_: None, **kw)

    make.data = data
    make.manual = manual
    return make


def read_dataset(data_dir: Path, dataset_id: str, shard: str | None = None) -> dict:
    contract = json.loads((data_dir / "contract.json").read_text())
    rel = contract["datasets"][dataset_id]["file"].replace("{shard}", shard or "")
    return json.loads((data_dir / rel).read_text())


@pytest.fixture
def read():
    return read_dataset
