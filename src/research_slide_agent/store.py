"""Single-host durable queue and versioned specifications for Raspberry Pi."""

import hashlib
import json
import secrets
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager

from .config import Settings
from .files import MAX_TOTAL, validate_file
from .models import SlideSpec


class StateError(ValueError):
    pass


def uid():
    return uuid.uuid4().hex


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.root / "state.sqlite3"
        with self.connect() as con:
            con.execute("PRAGMA secure_delete=ON")
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects(
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0, spec TEXT, latest_pptx TEXT);
                CREATE TABLE IF NOT EXISTS specs(
                    project TEXT NOT NULL REFERENCES projects ON DELETE CASCADE,
                    version INTEGER NOT NULL, digest TEXT NOT NULL, body TEXT NOT NULL, template_sha TEXT,
                    PRIMARY KEY(project, version));
                -- Retain legacy approval/review tables and patch columns for existing databases.
                CREATE TABLE IF NOT EXISTS approvals(
                    project TEXT NOT NULL REFERENCES projects ON DELETE CASCADE,
                    version INTEGER NOT NULL, stage TEXT NOT NULL, target TEXT NOT NULL,
                    digest TEXT NOT NULL, approved_at REAL NOT NULL,
                    PRIMARY KEY(project, version, stage, target));
                CREATE TABLE IF NOT EXISTS files(
                    id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects ON DELETE CASCADE,
                    name TEXT NOT NULL, kind TEXT NOT NULL, size INTEGER NOT NULL, sha TEXT NOT NULL,
                    path TEXT NOT NULL, author TEXT, year INTEGER);
                CREATE TABLE IF NOT EXISTS reviews(
                    id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects ON DELETE CASCADE,
                    version INTEGER NOT NULL, stage TEXT NOT NULL, target TEXT NOT NULL,
                    digest TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS patches(
                    id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects ON DELETE CASCADE,
                    file_id TEXT NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS jobs(
                    id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects ON DELETE CASCADE,
                    owner TEXT NOT NULL, version INTEGER NOT NULL, digest TEXT NOT NULL,
                    payload TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    available REAL NOT NULL, lease REAL, lease_token TEXT, output TEXT, error TEXT,
                    created REAL NOT NULL, UNIQUE(project,digest));
                CREATE UNIQUE INDEX IF NOT EXISTS user_active ON jobs(owner)
                    WHERE state IN ('queued','running','validating');
            """)

        with self.connect() as con:
            if "template_sha" not in {row["name"] for row in con.execute("PRAGMA table_info(specs)")}:
                con.execute("ALTER TABLE specs ADD COLUMN template_sha TEXT")

    def source_metadata(self, owner, project, file_id, author, year):
        if not author or not author.strip() or len(author) > 80 or not 1800 <= year <= 2200:
            raise StateError("Valid author/year required")
        with self.connect() as con:
            p = self._project(con, owner, project)
            if p["spec"] and file_id in p["spec"]:
                raise StateError(
                    "SOURCE_ALREADY_REFERENCED: register a new corrected source and update the spec"
                )
            result = con.execute(
                "UPDATE files SET author=?,year=? WHERE id=? AND project=?", (author, year, file_id, project)
            )
            if not result.rowcount:
                raise StateError("FILE_NOT_FOUND")
        return {"source_id": file_id, "author": author, "year": year}

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA secure_delete=ON")
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _project(self, con, owner, project):
        row = con.execute("SELECT * FROM projects WHERE id=? AND owner=?", (project, owner)).fetchone()
        if row is None or row["expires"] <= time.time():
            raise StateError("PROJECT_NOT_FOUND_OR_EXPIRED")
        return dict(row)

    def project(self, owner, project):
        with self.connect() as con:
            result = self._project(con, owner, project)
        result["spec"] = json.loads(result["spec"]) if result["spec"] else None
        return result

    def create(self, owner):
        project = uid()
        with self.connect() as con:
            con.execute(
                "INSERT INTO projects(id,owner,created,expires) VALUES(?,?,?,?)",
                (project, owner, time.time(), time.time() + 7 * 86400),
            )
        (self.root / project).mkdir(mode=0o700)
        return self.project(owner, project)

    def save_spec(self, owner, project, spec: SlideSpec, expected_version: int):
        if spec.presentation_id != project or spec.template_id != "lab":
            raise StateError("Wrong project or template")
        with self.connect() as con:
            p = self._project(con, owner, project)
            if p["version"] != expected_version or spec.spec_version != expected_version + 1:
                raise StateError("SPEC_VERSION_CONFLICT")
            sources = {
                row["id"]: dict(row) for row in con.execute("SELECT * FROM files WHERE project=?", (project,))
            }
            for slide in spec.slides:
                refs = (
                    slide.source_references
                    + [r for b in slide.body_blocks for r in b.source_references]
                    + [c.source for c in slide.citations]
                )
                for ref in refs:
                    if ref.source_id not in sources:
                        raise StateError("Citation/source must refer to this project's uploaded files")
                for citation in slide.citations:
                    src = sources[citation.source.source_id]
                    if src["author"] != citation.author or src["year"] != citation.year:
                        raise StateError("SOURCE_METADATA_MISMATCH: confirm author and year in browser")
                for image in slide.image_references:
                    if image.source_id not in sources or sources[image.source_id]["kind"] not in {
                        "png",
                        "jpg",
                        "jpeg",
                    }:
                        raise StateError("Image source is unavailable")
            body = spec.model_dump_json()
            con.execute(
                "UPDATE projects SET version=?, spec=? WHERE id=?", (spec.spec_version, body, project)
            )
            con.execute(
                "INSERT INTO specs VALUES(?,?,?,?,?)",
                (
                    project,
                    spec.spec_version,
                    spec.digest(),
                    body,
                    hashlib.sha256(self.settings.template.read_bytes()).hexdigest(),
                ),
            )
        return {
            "spec_version": spec.spec_version,
            "digest": spec.digest(),
        }

    def register(self, owner, project, name, data, author=None, year=None):
        kind = validate_file(name, data)
        if author is not None and (not author.strip() or len(author) > 80):
            raise StateError("Invalid source author")
        if year is not None and not 1800 <= int(year) <= 2200:
            raise StateError("Invalid source year")
        file_id = uid()
        path = self.root / project / "inputs" / f"{file_id}.{kind}"
        with self.connect() as con:
            self._project(con, owner, project)
            files = con.execute("SELECT size FROM files WHERE project=?", (project,)).fetchall()
            if len(files) >= 10 or sum(r["size"] for r in files) + len(data) > MAX_TOTAL:
                raise StateError("PROJECT_FILE_LIMIT")
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(data)
            con.execute(
                "INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    file_id,
                    project,
                    name,
                    kind,
                    len(data),
                    hashlib.sha256(data).hexdigest(),
                    str(path.relative_to(self.root)),
                    author,
                    year,
                ),
            )
            if kind == "pptx":
                con.execute("UPDATE projects SET latest_pptx=? WHERE id=?", (file_id, project))
        return {"source_id": file_id, "name": name, "kind": kind, "sha256": hashlib.sha256(data).hexdigest()}

    def files(self, owner, project):
        with self.connect() as con:
            self._project(con, owner, project)
            return [
                dict(row)
                for row in con.execute(
                    "SELECT id,name,kind,size,sha,author,year FROM files WHERE project=?", (project,)
                )
            ]

    def file(self, owner, project, file_id):
        with self.connect() as con:
            self._project(con, owner, project)
            row = con.execute("SELECT * FROM files WHERE id=? AND project=?", (file_id, project)).fetchone()
            if not row:
                raise StateError("FILE_NOT_FOUND")
            result = dict(row)
        result["path"] = self.root / result["path"]
        return result

    def patch_plan(self, owner, project, file_id, changes):
        from .engine import LayoutError, inspect_pptx

        p = self.project(owner, project)
        if p["latest_pptx"] != file_id:
            raise StateError("Use the latest reuploaded PPTX")
        f = self.file(owner, project, file_id)
        if f["kind"] != "pptx" or not 1 <= len(changes) <= 40:
            raise StateError("Invalid patch")
        slides = inspect_pptx(f["path"])
        body = {"file_id": file_id, "file_sha256": f["sha"], "changes": []}
        for change in changes:
            if (
                set(change) != {"slide_number", "shape_id", "expected_sha256", "text"}
                or not isinstance(change["text"], str)
                or len(change["text"]) > 1800
            ):
                raise StateError("Patch must contain slide_number, shape_id, expected_sha256 and text")
            try:
                current = next(
                    s
                    for s in slides[change["slide_number"] - 1]["shapes"]
                    if s["shape_id"] == change["shape_id"]
                )
            except (IndexError, StopIteration, TypeError) as exc:
                raise StateError("Unknown patch target") from exc
            if change["slide_number"] < 1 or current["sha256"] != change["expected_sha256"]:
                raise LayoutError("EDIT_CONFLICT")
            body["changes"].append({**change, "previous_text": current["text"]})
        raw = json.dumps(body, sort_keys=True)
        patch_id = uid()
        with self.connect() as con:
            p = self._project(con, owner, project)
            if p["latest_pptx"] != file_id:
                raise StateError("PATCH_BASE_CHANGED")
            con.execute(
                "INSERT INTO patches VALUES(?,?,?,?,?,0)",
                (patch_id, project, file_id, raw, hashlib.sha256(raw.encode()).hexdigest()),
            )
        return {"patch_id": patch_id}

    def enqueue(self, owner, project, patch_id=None):
        with self.connect() as con:
            p = self._project(con, owner, project)
            if patch_id:
                patch = con.execute(
                    "SELECT * FROM patches WHERE id=? AND project=?", (patch_id, project)
                ).fetchone()
                if not patch or p["latest_pptx"] != patch["file_id"]:
                    raise StateError("PATCH_NOT_FOUND_OR_BASE_CHANGED")
                digest, payload = (
                    patch["digest"],
                    {"kind": "patch", "patch_id": patch_id, **json.loads(patch["body"])},
                )
            else:
                if not p["spec"]:
                    raise StateError("SPEC_REQUIRED")
                spec = SlideSpec.model_validate_json(p["spec"])
                digest = spec.digest()
                saved = con.execute(
                    "SELECT template_sha FROM specs WHERE project=? AND version=?", (project, p["version"])
                ).fetchone()
                if (
                    not saved
                    or saved["template_sha"]
                    != hashlib.sha256(self.settings.template.read_bytes()).hexdigest()
                ):
                    raise StateError("TEMPLATE_CHANGED_RESAVE_REQUIRED")
                payload = {
                    "kind": "generate",
                    "spec": json.loads(p["spec"]),
                    "template_sha256": hashlib.sha256(self.settings.template.read_bytes()).hexdigest(),
                }
            prior = con.execute(
                "SELECT * FROM jobs WHERE project=? AND digest=?", (project, digest)
            ).fetchone()
            if prior:
                return self._job_public(prior)
            if con.execute(
                "SELECT 1 FROM jobs WHERE owner=? AND state IN ('queued','running','validating')", (owner,)
            ).fetchone():
                raise StateError("USER_JOB_LIMIT")
            job = uid()
            con.execute(
                "INSERT INTO jobs(id,project,owner,version,digest,payload,state,available,created) VALUES(?,?,?,?,?,?,'queued',?,?)",
                (job, project, owner, p["version"], digest, json.dumps(payload), time.time(), time.time()),
            )
            row = con.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
            return self._job_public(row)

    @staticmethod
    def _job_public(row):
        return {k: row[k] for k in ("id", "project", "version", "state", "attempts", "error", "output")}

    def job(self, owner, job):
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=? AND owner=?", (job, owner)).fetchone()
            if not row:
                raise StateError("JOB_NOT_FOUND")
            self._project(con, owner, row["project"])
            return self._job_public(row)

    def retry(self, owner, job):
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=? AND owner=?", (job, owner)).fetchone()
            if not row:
                raise StateError("JOB_NOT_FOUND")
            self._project(con, owner, row["project"])
            if row["state"] != "failed" or row["attempts"] >= 3:
                raise StateError("RETRY_LIMIT_OR_NOT_FAILED")
            if con.execute(
                "SELECT 1 FROM jobs WHERE owner=? AND state IN ('queued','running','validating')", (owner,)
            ).fetchone():
                raise StateError("USER_JOB_LIMIT")
            con.execute(
                "UPDATE jobs SET state='queued',available=?,error=NULL WHERE id=?", (time.time(), job)
            )
        return self.job(owner, job)

    def claim(self):
        now = time.time()
        with self.connect() as con:
            expired = con.execute(
                "SELECT id,attempts FROM jobs WHERE state IN ('running','validating') AND lease<?", (now,)
            ).fetchall()
            for row in expired:
                con.execute(
                    "UPDATE jobs SET state=?,error='LEASE_EXPIRED',lease_token=NULL WHERE id=?",
                    ("failed" if row["attempts"] >= 3 else "queued", row["id"]),
                )
            con.execute(
                "UPDATE jobs SET state='failed',error='PROJECT_EXPIRED' WHERE project IN (SELECT id FROM projects WHERE expires<=?) AND state IN ('queued','running','validating')",
                (now,),
            )
            running = con.execute(
                "SELECT count(*) FROM jobs WHERE state IN ('running','validating')"
            ).fetchone()[0]
            if running >= self.settings.worker_limit:
                return None
            row = con.execute(
                "SELECT j.* FROM jobs j JOIN projects p ON p.id=j.project WHERE j.state='queued' AND j.available<=? AND p.expires>? ORDER BY j.created LIMIT 1",
                (now, now),
            ).fetchone()
            if row is None:
                return None
            token = secrets.token_hex(16)
            con.execute(
                "UPDATE jobs SET state='running',attempts=attempts+1,lease=?,lease_token=? WHERE id=?",
                (now + self.settings.lease_seconds, token, row["id"]),
            )
            result = dict(con.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())
            result["payload"] = json.loads(result["payload"])
            return result

    def finish(self, job, token, state, output=None, error=None, transient=False):
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM jobs WHERE id=? AND lease_token=? AND state IN ('running','validating')",
                (job, token),
            ).fetchone()
            if not row or row["lease"] <= time.time():
                raise StateError("WORKER_LEASE_LOST")
            self._project(con, row["owner"], row["project"])
            if transient and row["attempts"] < 3:
                state = "queued"
            con.execute(
                "UPDATE jobs SET state=?,output=?,error=?,available=? WHERE id=?",
                (
                    state,
                    json.dumps(output) if output else None,
                    error,
                    time.time() + 2 ** row["attempts"],
                    job,
                ),
            )

    def cleanup(self):
        removed = 0
        with self.connect() as con:
            for row in con.execute("SELECT id FROM projects WHERE expires<=?", (time.time(),)).fetchall():
                directory = self.root / row["id"]
                if directory.exists():
                    shutil.rmtree(directory)
                con.execute("DELETE FROM projects WHERE id=?", (row["id"],))
                removed += 1
        con = sqlite3.connect(self.db, timeout=30)
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            con.close()
        return {"removed_projects": removed}
