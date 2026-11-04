"""Private JSON storage with restrictive permissions and a single writer lock."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from datetime import datetime, timezone
from uuid import uuid4


class LocalError(Exception):
    """A user-facing failure with a stable, non-sensitive message."""


def now():
    return datetime.now(timezone.utc).isoformat()


class PrivateStore:
    DIRECTORIES = ("inbox", "state", "resources", "resources/drafts", "audit")

    def __init__(self, root, project_root):
        chosen = Path(root).expanduser()
        if chosen.is_symlink():
            raise LocalError("private root must not be a symbolic link")
        self.root = chosen.resolve()
        project = Path(project_root).resolve()
        if self.root.is_relative_to(project) or project.is_relative_to(self.root):
            raise LocalError("private root must be separate from the project tree")
        if any((p / ".git").exists() for p in [self.root, *self.root.parents]):
            raise LocalError("private root must be outside Git working trees")

    @staticmethod
    def _directory(path):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise LocalError("private directory must be an owned, real directory")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise LocalError("private directories require owner-only permissions")

    def _path(self, relative):
        name = PurePosixPath(relative)
        if name.is_absolute() or ".." in name.parts or not name.parts:
            raise LocalError("invalid private relative path")
        self._directory(self.root)
        current = self.root
        for part in name.parts[:-1]:
            current = current / part
            self._directory(current)
        target = current / name.name
        if target.exists() or target.is_symlink():
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise LocalError("private files must be owned regular files")
            if info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
                raise LocalError("private files require one link and owner-only permissions")
        return target

    def initialize(self, settings):
        if self.root.exists():
            self._directory(self.root)
            if any(self.root.iterdir()):
                raise LocalError("initialization requires a new or empty private directory")
        else:
            self.root.mkdir(mode=0o700)
        for relative in self.DIRECTORIES:
            (self.root / relative).mkdir(mode=0o700)
        self.write_json("settings.json", settings)
        self.write_json("state/tasks.json", {"schema_version": 1, "tasks": []})
        with self.lock():
            self.audit("initialized")

    def write_text(self, relative, text):
        target = self._path(relative)
        descriptor, temporary = tempfile.mkstemp(prefix=".write-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def write_json(self, relative, value):
        text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if len(text) > 4_000_000:
            raise LocalError("private JSON exceeds the supported size; archive before adding more records")
        self.write_text(relative, text)

    def read_json(self, relative, limit=4_000_000):
        target = self._path(relative)
        with target.open("r", encoding="utf-8") as stream:
            text = stream.read(limit + 1)
        if len(text) > limit:
            raise LocalError("private JSON exceeds the supported size")
        try:
            return json.loads(text)
        except (ValueError, UnicodeError):
            raise LocalError("private JSON is invalid") from None

    @contextmanager
    def lock(self):
        self._path("settings.json")
        target = self._path(".writer-lock")
        descriptor = os.open(target, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LocalError("private store is busy; retry after the current command finishes") from None
            yield
        finally:
            os.close(descriptor)

    def audit(self, action, **fields):
        record = {"time": now(), "action": action, **fields}
        target = self._path("audit/events.jsonl")
        descriptor = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def capture(self, text):
        if not text.strip() or len(text) > 20_000:
            raise LocalError("capture requires 1 to 20000 characters of nonblank text")
        with self.lock():
            capture_id = uuid4().hex
            relative = "inbox/" + capture_id + ".json"
            self.write_json(relative, {"id": capture_id, "created_at": now(),
                                      "classification": "unclassified", "text": text})
            self.audit("captured", capture_id=capture_id)
        return {"status": "saved", "id": capture_id, "private_file": relative,
                "classification": "unclassified"}
