"""Immutable accepted contribution artifacts associated with the parent project."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from core.atomic_json_file import read_json_file, write_json_atomically
from core.delivery_management.evidence import AcceptedContribution
from core.delivery_management.store import ManagementStore
from core.project_setup.architecture import content_hash


@dataclass(frozen=True)
class AuthorityArtifact:
    path: str
    sha256: str


@dataclass(frozen=True)
class AuthorityStore:
    records: ManagementStore

    def save(self, contribution: AcceptedContribution) -> AuthorityArtifact:
        value = contribution.to_dict()
        path = self.records.directory(contribution.project_id) / "authority" / (content_hash(value) + ".json")
        if path.exists():
            if content_hash(read_json_file(path)) != content_hash(value):
                raise ValueError("immutable accepted authority artifact changed")
        else:
            write_json_atomically(path, value)
        return AuthorityArtifact(str(path), sha256(path.read_bytes()).hexdigest())
