import difflib
import hashlib

import yaml
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import YamlLexer
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.models import SemanticView, SemanticViewVersion, User


class YamlValidationError(ValueError):
    pass


def validate_yaml(raw: bytes) -> tuple[str, list[str]]:
    """Return (status, warnings). Raises YamlValidationError on hard failure."""
    if len(raw) > settings.max_yaml_bytes:
        raise YamlValidationError(
            f"File too large ({len(raw)} bytes; max {settings.max_yaml_bytes})."
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise YamlValidationError("File is not valid UTF-8 text.")
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise YamlValidationError(f"YAML parse error: {e}")
    if not isinstance(doc, dict):
        raise YamlValidationError("Top level of a semantic model must be a mapping.")

    warnings = []
    if "name" not in doc:
        warnings.append("Missing top-level 'name' key.")
    if not any(k in doc for k in ("tables", "logical_tables", "semantic_view")):
        warnings.append(
            "No 'tables' (or 'logical_tables') key found — is this a Cortex semantic model?"
        )
    return ("warnings" if warnings else "valid", warnings)


def add_version(
    db: DbSession, view: SemanticView, raw: bytes, change_note: str, user: User
) -> SemanticViewVersion:
    status, warnings = validate_yaml(raw)  # raises on hard failure

    next_num = (
        db.scalar(
            select(func.coalesce(func.max(SemanticViewVersion.version_number), 0)).where(
                SemanticViewVersion.semantic_view_id == view.id
            )
        )
        + 1
    )
    rel_path = f"semantic_views/{view.id}/v{next_num}.yaml"
    abs_path = settings.data_dir / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(raw)

    version = SemanticViewVersion(
        semantic_view_id=view.id,
        version_number=next_num,
        file_path=rel_path,
        content_sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        change_note=change_note.strip(),
        created_by=user.id,
        validation_status=status,
        validation_messages=warnings,
    )
    db.add(version)
    db.flush()
    view.current_version_id = version.id
    db.commit()
    return version


def read_version_bytes(version: SemanticViewVersion) -> bytes:
    return (settings.data_dir / version.file_path).read_bytes()


def highlight_yaml(raw: bytes) -> str:
    return highlight(raw.decode("utf-8", errors="replace"), YamlLexer(), HtmlFormatter())


def unified_diff_html(old: bytes, new: bytes, old_label: str, new_label: str) -> list[dict]:
    """Return diff lines as [{'kind': 'add'|'del'|'ctx', 'text': ...}] for template rendering."""
    lines = difflib.unified_diff(
        old.decode("utf-8", errors="replace").splitlines(),
        new.decode("utf-8", errors="replace").splitlines(),
        fromfile=old_label,
        tofile=new_label,
        lineterm="",
    )
    out = []
    for line in lines:
        kind = "ctx"
        if line.startswith("+") and not line.startswith("+++"):
            kind = "add"
        elif line.startswith("-") and not line.startswith("---"):
            kind = "del"
        out.append({"kind": kind, "text": line})
    return out
