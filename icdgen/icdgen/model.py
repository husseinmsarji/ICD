"""Immutable domain model for ICD interface definitions.

The model is decoupled from the YAML wire format so generators consume a
single canonical object. Dataclasses are frozen to reinforce determinism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .fields import C_TYPE_MAP, SIMULINK_TYPE_MAP  # noqa: F401,E402


@dataclass(frozen=True)
class Signal:
    name: str
    signal_type: str = ""          # data type incl. "enum"; blank = in-progress
    update_rate_hz: Optional[float] = None
    units: str = ""
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    scaling: float = 1.0
    offset: float = 0.0
    description: Optional[str] = None
    definition: Optional[str] = None
    data_bits: Optional[int] = None
    xmit_bits: Optional[int] = None
    xmit_bytes: Optional[int] = None
    pr_ticket: Optional[str] = None

    @property
    def has_concrete_type(self) -> bool:
        """True when signal_type maps to a real C/Simulink type."""
        return self.signal_type in C_TYPE_MAP

    @property
    def c_type(self) -> str:
        # Blank/unknown type -> placeholder so an in-progress header still
        # renders. A warning is raised at load time (loader._semantic_checks).
        return C_TYPE_MAP.get(self.signal_type, "uint8_t")

    @property
    def simulink_type(self) -> str:
        return SIMULINK_TYPE_MAP.get(self.signal_type, "uint8")


@dataclass(frozen=True)
class Packet:
    name: str
    signals: tuple[Signal, ...]
    description: Optional[str] = None


@dataclass(frozen=True)
class Interface:
    id: str
    name: str
    bus_type: str
    dal: str
    source_lru: str
    destination_lru: str
    owning_document: str
    packets: tuple[Packet, ...]
    description: Optional[str] = None


@dataclass(frozen=True)
class RevisionEntry:
    revision: str
    date: str
    author: str
    description: str


@dataclass(frozen=True)
class Metadata:
    document_id: str
    document_title: str
    program: str
    revision: str
    revision_date: str
    author: str
    revision_history: tuple[RevisionEntry, ...]


@dataclass(frozen=True)
class PriorRevision:
    """Maps a revision letter to the source file that defined the ICD at that
    revision. Used to auto-compute a per-revision change summary for the
    document header. Structural (not registry-driven)."""
    revision: str
    source: str


@dataclass(frozen=True)
class IcdModel:
    schema_version: str
    metadata: Metadata
    interfaces: tuple[Interface, ...]
    prior_revisions: tuple[PriorRevision, ...] = ()

    def all_signals(self):
        """Yield (interface, packet, signal) triples in document order."""
        for iface in self.interfaces:
            for pkt in iface.packets:
                for sig in pkt.signals:
                    yield iface, pkt, sig