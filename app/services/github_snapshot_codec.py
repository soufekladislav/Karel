"""Lossless, bounded GitHub read-cache codec for MariaDB TEXT.

The public GitHub API can return >100 kB for even a mid-sized repository.
MySQL/MariaDB TEXT stores at most 65,535 bytes, so a successful commit can
otherwise leave invalid/truncated JSON on permissive servers.

Small snapshots stay legacy JSON. Large snapshots use compact zlib/base64
inside an integrity-checked JSON envelope. Existing schemas and DB columns
do not change, and the caller never claims success before the encoded
snapshot has passed a local round-trip check.
"""
from __future__ import annotations

import base64
import hashlib
import json
import zlib

MAX_STORED_BYTES = 55_000
MAX_DECODED_BYTES = 2_000_000
COMPRESSED_SCHEMA = "karel.github.cache.zlib.v1"


class GitHubSnapshotCodecError(ValueError):
    """No raw repository content, credentials or traceback in user-facing text."""


def encode_snapshot(snapshot: dict) -> str:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("repository"), str):
        raise GitHubSnapshotCodecError("GitHub nevrátil ověřitelná data repozitáře.")
    raw = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_DECODED_BYTES:
        raise GitHubSnapshotCodecError("GitHub snímek přesahuje bezpečný limit 2 MB.")
    if len(raw) <= MAX_STORED_BYTES:
        stored = raw.decode("utf-8")
    else:
        envelope = {
            "schema": COMPRESSED_SCHEMA,
            "payload": base64.b64encode(zlib.compress(raw, level=9)).decode("ascii"),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        stored = json.dumps(envelope, ensure_ascii=True, separators=(",", ":"))
    if len(stored.encode("utf-8")) > MAX_STORED_BYTES:
        raise GitHubSnapshotCodecError(
            "GitHub data jsou příliš rozsáhlá pro současné úložiště. "
            "Původní snímek nebyl přepsán; správce musí rozšířit úložiště."
        )
    # Fail before database commit if encoding/decoding was not perfectly lossless.
    if decode_snapshot(stored) != snapshot:
        raise GitHubSnapshotCodecError("Uložený GitHub snímek neprošel ověřením integrity.")
    return stored


def decode_snapshot(encoded: str | None) -> dict:
    if not encoded:
        return {}
    try:
        if len(encoded.encode("utf-8")) > MAX_DECODED_BYTES:
            return {}
        wrapper = json.loads(encoded)
        if not isinstance(wrapper, dict):
            return {}
        if wrapper.get("schema") != COMPRESSED_SCHEMA:
            # Backward compatibility for all existing legacy snapshots.
            return wrapper if isinstance(wrapper.get("repository"), str) and wrapper.get("repository") else {}
        packed = base64.b64decode(wrapper["payload"], validate=True)
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(packed, MAX_DECODED_BYTES + 1)
        if len(raw) > MAX_DECODED_BYTES or not decompressor.eof or decompressor.unconsumed_tail:
            return {}
        if decompressor.flush():
            return {}
        if hashlib.sha256(raw).hexdigest() != wrapper["sha256"]:
            return {}
        snapshot = json.loads(raw)
        if not isinstance(snapshot, dict) or not snapshot.get("repository"):
            return {}
        return snapshot
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, zlib.error):
        return {}
