"""Provenance for reqgen.

A generated requirements module traces to three anchors: the reqgen tool
version, the SHA-256 of the ICD source file it read, and the SHA-256 of the
config file that drove generation. Both inputs are hashed, so a generated
requirement is reproducible from a known ICD and a known config. No timestamps
in artifacts.
"""
from __future__ import annotations

from dataclasses import dataclass

TOOL_NAME = "reqgen"
TOOL_VERSION = "0.1.0"


@dataclass(frozen=True)
class ReqProvenance:
    tool_name: str
    tool_version: str
    icd_hash: str
    config_hash: str

    @classmethod
    def create(cls, icd_hash: str, config_hash: str) -> "ReqProvenance":
        return cls(TOOL_NAME, TOOL_VERSION, icd_hash, config_hash)

    def banner_lines(self) -> list[str]:
        return [
            f"{self.tool_name} v{self.tool_version}",
            f"ICD SHA-256:    {self.icd_hash}",
            f"Config SHA-256: {self.config_hash}",
            "Generated requirements. Do NOT edit here; revise the ICD or the "
            "reqgen config and regenerate.",
        ]
