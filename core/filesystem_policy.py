from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


_DOT_SEGMENTS = {".", ".."}


def validate_filesystem_identifier(identifier: str, label: str = "filesystem identifier") -> str:
    text = _required_text(identifier, label)
    if _looks_absolute(text):
        raise ValueError(f"{label} must not be absolute")
    if "/" in text or "\\" in text:
        raise ValueError(f"{label} must not contain path separators")
    if text in _DOT_SEGMENTS:
        raise ValueError(f"{label} must not be a dot segment")
    return text


def resolve_identifier_path(root: Path, identifier: str, label: str = "filesystem identifier") -> Path:
    validated = validate_filesystem_identifier(identifier, label)
    return _confined_path(Path(root).resolve(), validated, label)


def resolve_relative_path(root: Path, relative_path: str, label: str) -> Path:
    text = _required_text(relative_path, label)
    if _looks_absolute(text):
        raise ValueError(f"{label} must be relative")
    normalized = PurePosixPath(text.replace("\\", "/"))
    if any(part in _DOT_SEGMENTS for part in normalized.parts):
        raise ValueError(f"{label} must not contain dot segments")
    return _confined_path(Path(root).resolve(), normalized.as_posix(), label)


def resolve_confined_absolute_path(root: Path, candidate: Path | str, label: str) -> Path:
    path = Path(candidate)
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    resolved_root = Path(root).resolve()
    resolved_candidate = path.resolve()
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise ValueError(f"{label} must stay within {resolved_root}")
    return resolved_candidate


def _confined_path(root: Path, relative_path: str, label: str) -> Path:
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"{label} must stay within {root}")
    return candidate


def _looks_absolute(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
    text = value.strip()
    if text != value:
        raise ValueError(f"{label} must not include surrounding whitespace")
    return text
