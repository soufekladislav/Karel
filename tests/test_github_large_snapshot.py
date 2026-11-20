"""Regression for GitHub Ema: 67 Issues + 19 PR exceed MariaDB TEXT.

The JSON cache MUST be lossless, small enough for existing storage, and
backwards compatible with older rows. Never silently claim synchronization.
"""
import base64
import json
import random
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import GitHubRepoLink, Project, User
from app.services.github_snapshot_store import upsert_snapshot
from app.services.github_snapshot_codec import (
    COMPRESSED_SCHEMA, MAX_STORED_BYTES, GitHubSnapshotCodecError,
    decode_snapshot, encode_snapshot,
)
from app.services.project_presentation import github_connection_state


def ema_sample():
    # Non-repetitive issue bodies and distinct titles emulate a genuine repo.
    issues=[{
        "number": i+1, "title": f"Issue #{i+1} – dokumentace, integrační testy a kalendář",
        "state": "open" if i%3==0 else "closed",
        "url": f"https://github.com/soufekladislav/Ema/issues/{i+1}",
        "body_excerpt": "".join(chr(65+(j*7+i*13)%26) for j in range(1400)),
        "labels": ["P0","workflow","ux"],"created_at":"2026-11-19T19:20:00Z",
    } for i in range(67)]
    prs=[{
        "number":i+1,"title":f"PR #{i+1}: integrace dat","state":"closed",
        "url":f"https://github.com/soufekladislav/Ema/pull/{i+1}",
        "body_excerpt": "".join(chr(65+(j*11+i*5)%26) for j in range(1400)),
    } for i in range(19)]
    return {
        "schema":"karel.github.snapshot.v1",
        "repository":"soufekladislav/Ema",
        "html_url":"https://github.com/soufekladislav/Ema",
        "fetched_at":"2026-11-19T20:05:53Z",
        "counts":{"issues_loaded":67,"open_issues":23,"prs_loaded":19,
                  "open_prs":0,"projects_loaded":0,"workflow_runs":12},
        "issues":issues,"pull_requests":prs,
        "projects_v2":[],"projects_v2_status":"requires_token",
        "workflow_runs":[],"actions_status":"unavailable",
        "source_tree":[f"app/source/module_{i}.py" for i in range(400)],
        "commits":[],"documentation_paths":[],
        "partial":{"issues":False,"prs":False,"tree":False},
    }


class GithubLargeCacheTests(unittest.TestCase):
    def test_ema_roundtrip_preserves_every_issue_and_pr(self):
        snap=ema_sample()
        self.assertGreater(len(json.dumps(snap,ensure_ascii=False).encode('utf8')),65535)
        encoded=encode_snapshot(snap)
        self.assertLessEqual(len(encoded.encode('utf-8')),MAX_STORED_BYTES)
        self.assertEqual(json.loads(encoded)["schema"],COMPRESSED_SCHEMA)
        self.assertEqual(decode_snapshot(encoded),snap)
        self.assertEqual(len(decode_snapshot(encoded)["issues"]),67)
        self.assertEqual(len(decode_snapshot(encoded)["pull_requests"]),19)

    def test_legacy_json_stays_compatible_and_truncated_payload_fails(self):
        small={"schema":"karel.github.snapshot.v1",
               "repository":"soufekladislav/Boban","counts":{"issues_loaded":1}}
        legacy=json.dumps(small)
        self.assertEqual(decode_snapshot(legacy),small)
        self.assertEqual(decode_snapshot(legacy[:19]),{})
        self.assertEqual(decode_snapshot(''),{})

    def test_corrupted_compressed_bytes_never_claim_success(self):
        stored=json.loads(encode_snapshot(ema_sample()))
        stored["sha256"]="0"*64
        self.assertEqual(decode_snapshot(json.dumps(stored)),{})
        stored.pop("payload")
        self.assertEqual(decode_snapshot(json.dumps(stored)),{})

    def test_storage_rejects_incompressible_overflow_without_partial_write(self):
        # Pseudorandom textual bytes are far less compressible than normal
        # human issue descriptions. Do not silently write invalid TEXT.
        rnd=random.Random(9036)
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        random_content="".join(rnd.choice(alphabet) for _ in range(160000))
        bad={"repository":"soufekladislav/large","issue_bodies":random_content}
        with self.assertRaises(GitHubSnapshotCodecError):
            encode_snapshot(bad)

    def test_db_roundtrip_and_status_are_verified(self):
        engine=create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        with sessionmaker(bind=engine)() as db:
            user=User(email='owner@local.cz',password_hash='x',role='user')
            db.add(user);db.flush()
            project=Project(owner_id=user.id,name='Ema')
            db.add(project);db.flush()
            snap=ema_sample()
            upsert_snapshot(db,project.id,user.id,snap)
            link=db.scalar(select(GitHubRepoLink).where(GitHubRepoLink.project_id==project.id))
            self.assertEqual(github_connection_state(link,True)['kind'],'synced')
            self.assertEqual(decode_snapshot(link.snapshot_json)['counts']['issues_loaded'],67)
            # A damaged pre-existing row must not display made-up counts.
            link.snapshot_json='{"schema":"karel.github.snapshot.v1","reposito'
            db.commit()
            self.assertEqual(github_connection_state(link,True)['kind'],'pending')
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
