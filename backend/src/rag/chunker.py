"""
Chunk NIST 800-53 controls for embedding.

Strategy:
    One chunk per control (including enhancements like SI-2(1)).
    The embedding payload is `{id}: {name}\n\n{statement}\n\n{discussion}`
    — that's what semantic similarity is computed against.
    Each chunk carries metadata so the retriever can return
    "SI-2: Flaw Remediation" with the matching prose, not anonymous text.
"""

from dataclasses import dataclass


@dataclass
class NistChunk:
    """A single chunk ready for embedding."""
    chunk_id: str           # globally unique id, == control id for now
    control_id: str         # e.g. "SI-2"
    control_name: str       # e.g. "Flaw Remediation"
    family: str             # e.g. "System and Information Integrity"
    text: str               # the actual text to embed


def chunk_controls(controls: list[dict]) -> list[NistChunk]:
    """Convert raw NIST control dicts into chunks ready for embedding."""
    chunks: list[NistChunk] = []
    for c in controls:
        cid = c.get("id", "")
        if not cid:
            continue
        text = _compose_text(c)
        if not text.strip():
            continue
        chunks.append(NistChunk(
            chunk_id=cid,
            control_id=cid,
            control_name=c.get("name", ""),
            family=c.get("family", ""),
            text=text,
        ))
    return chunks


def _compose_text(control: dict) -> str:
    """Build the text we want the embedding model to see."""
    parts = [f"{control.get('id', '')}: {control.get('name', '')}".strip(": ")]
    statement = control.get("statement") or ""
    discussion = control.get("discussion") or ""
    if statement:
        parts.append(statement)
    if discussion:
        parts.append(discussion)
    return "\n\n".join(p for p in parts if p)
