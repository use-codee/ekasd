import json
import shutil
from unittest.mock import patch

import pytest

from backend.app.data.repository import DEFAULT_DIRECTORY, FileRepository
from backend.app.services.analytics import DataError


def test_file_repository_validates_and_aggregates_once():
    with patch("socket.socket", side_effect=AssertionError("network forbidden")):
        repo = FileRepository()
    assert len(repo.forecasts) == 14287
    assert len(repo.hourly) == 744
    assert repo.provenance["raw_chunks"] == 64


@pytest.mark.parametrize("failure", ["missing", "checksum", "schema", "utc"])
def test_corrupt_startup_files_fail_clearly(tmp_path, failure):
    shutil.copytree(DEFAULT_DIRECTORY, tmp_path / "processed")
    path = tmp_path / "processed/forecasts.csv"
    if failure == "missing":
        path.unlink()
    elif failure == "checksum":
        path.write_bytes(b"damaged")
    else:
        content = (
            path.read_text().replace("publishTime", "wrong", 1)
            if failure == "schema"
            else path.read_text().replace("Z", "")
        )
        path.write_text(content)
        import hashlib

        manifest_path = path.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["artifacts"][path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        manifest_path.write_text(json.dumps(manifest))
    with pytest.raises((DataError, ValueError)):
        FileRepository(tmp_path / "processed")


def test_default_path_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert FileRepository().provenance["raw_chunks"] == 64
