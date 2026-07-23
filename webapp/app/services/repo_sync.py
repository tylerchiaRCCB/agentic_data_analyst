"""Sync pipeline repo files (semantic models + domain docs) into the webapp DB.

On every list-page load, scan context/semantic_models/*.yaml and upsert
SemanticView rows so they appear in the run picker without manual creation.
Edits in the webapp write back to the repo file on disk.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.models import SemanticView, SemanticViewVersion

_SKIP_FILES = {"_TEMPLATE.yaml"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def list_repo_models() -> list[dict]:
    """Return [{name, path, domain_doc}] for each semantic model YAML in the repo."""
    models_dir = settings.semantic_models_dir
    if not models_dir.is_dir():
        return []
    results = []
    for p in sorted(models_dir.glob("*.yaml")):
        if p.name in _SKIP_FILES or p.name.endswith(".example.yaml"):
            continue
        domain_name = p.stem  # e.g. "tpo_insights"
        domain_doc = settings.domains_dir / f"{domain_name}.md"
        if not domain_doc.exists():
            # Try hyphenated variant (tpo-insights.md vs tpo_insights.md)
            domain_doc = settings.domains_dir / f"{domain_name.replace('_', '-')}.md"
        results.append({
            "name": domain_name,
            "yaml_path": p,
            "domain_doc": domain_doc if domain_doc.exists() else None,
        })
    return results


def sync_repo_to_db(db: DbSession) -> None:
    """Ensure every repo semantic model has a corresponding SemanticView row.

    Creates missing rows and updates the current version if the file changed.
    Does NOT delete DB rows for removed files (old runs reference them).
    """
    for model in list_repo_models():
        name = model["name"]
        yaml_path: Path = model["yaml_path"]
        raw = yaml_path.read_bytes()
        file_hash = _sha256(raw)

        view = db.scalar(select(SemanticView).where(SemanticView.name == name))
        if view is None:
            view = SemanticView(name=name, description=f"Auto-imported from {yaml_path.name}")
            db.add(view)
            db.flush()

        # Auto-populate snowflake_ref from YAML base_table if not already set
        if not view.snowflake_ref:
            try:
                import yaml
                doc = yaml.safe_load(raw)
                if isinstance(doc, dict):
                    for tbl in doc.get("tables") or []:
                        bt = tbl.get("base_table") or {}
                        if bt.get("database") and bt.get("schema"):
                            sv_name = (doc.get("name") or name).upper()
                            view.snowflake_ref = f"{bt['database']}.{bt['schema']}.{sv_name}"
                            break
            except Exception:
                pass

        # Check if current version matches the file on disk
        if view.current_version and view.current_version.content_sha256 == file_hash:
            continue  # file unchanged

        # Create a new version from the repo file
        next_num = 1
        if view.versions:
            next_num = max(v.version_number for v in view.versions) + 1

        # Store version file in the webapp's data dir
        rel_path = f"semantic_views/{view.id}/v{next_num}.yaml"
        abs_path = settings.data_dir / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(raw)

        version = SemanticViewVersion(
            semantic_view_id=view.id,
            version_number=next_num,
            file_path=rel_path,
            content_sha256=file_hash,
            size_bytes=len(raw),
            change_note="Synced from repo",
            validation_status="valid",
            validation_messages=[],
        )
        db.add(version)
        db.flush()
        view.current_version_id = version.id

    db.commit()


def save_yaml_to_repo(name: str, raw: bytes) -> Path:
    """Write YAML back to the repo's semantic_models directory."""
    dest = settings.semantic_models_dir / f"{name}.yaml"
    dest.write_bytes(raw)
    return dest


def read_domain_doc(name: str) -> str | None:
    """Read domain context markdown from repo, or None if not found."""
    for variant in (name, name.replace("_", "-")):
        path = settings.domains_dir / f"{variant}.md"
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return None


def save_domain_doc(name: str, content: str) -> Path:
    """Write domain context markdown back to the repo."""
    # Prefer existing filename convention
    for variant in (name, name.replace("_", "-")):
        path = settings.domains_dir / f"{variant}.md"
        if path.exists():
            path.write_text(content, encoding="utf-8")
            return path
    # New file: use the model name as-is
    path = settings.domains_dir / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
