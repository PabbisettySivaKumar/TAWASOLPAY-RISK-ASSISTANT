"""
Chunk NIST 800-53 controls for embedding.

Strategy:
    One chunk per control (or sub-control if a control is very long).
    Each chunk carries metadata: control_id, control_name, family.
    This lets the retriever return "SI-2: Flaw Remediation" with the
    matching prose, not anonymous text.
"""

from dataclasses import dataclass


@dataclass
class NistChunk:
    """A single chunk ready for embedding."""
    chunk_id: str           # e.g. "SI-2" or "SI-2-a"
    control_id: str         # e.g. "SI-2"
    control_name: str       # e.g. "Flaw Remediation"
    family: str             # e.g. "System and Information Integrity"
    text: str               # the actual text to embed


def chunk_controls(controls: list[dict]) -> list[NistChunk]:
    """Convert raw NIST control dicts into chunks ready for embedding."""
    # TODO: implement — one chunk per control, combining statement+discussion
    raise NotImplementedError
