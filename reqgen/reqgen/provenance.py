"""Provenance for reqgen.

A generated requirements module traces to THREE anchors:
  * the reqgen tool version,
  * the SHA-256 of the exact ICD source file it read,
  * the SHA-256 of the exact config file that drove generation.

Two inputs (ICD + config), both hashed, so a generated requirement is
reproducible from a known ICD and a known config. No timestamp in artifacts.
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
