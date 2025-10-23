from __future__ import annotations

from pathlib import Path

from ops.tools.verify_vendor import VendoredFile


def test_vendored_file_hash_matches(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("hello", encoding="utf-8")
    vf = VendoredFile(
        path=target, digest="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
    ok, _ = vf.check()
    assert ok


def test_vendored_file_hash_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("hello", encoding="utf-8")
    vf = VendoredFile(path=target, digest="deadbeef")
    ok, message = vf.check()
    assert not ok
    assert "hash mismatch" in message


def test_vendored_file_missing(tmp_path: Path) -> None:
    vf = VendoredFile(path=tmp_path / "missing.txt", digest="deadbeef")
    ok, message = vf.check()
    assert not ok
    assert "missing" in message
