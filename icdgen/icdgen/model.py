"""Immutable domain model for ICD interface definitions.

The model is deliberately decoupled from the XML/JSON wire format so that the
artifact generators consume a single canonical object regardless of input
syntax. Dataclasses are frozen to reinforce the determinism requirement: once
loaded, the model cannot be mutated by a generator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Data-type representations come from the field registry (single source of
# truth). Re-exported here so generators can keep importing them from model.
from .fields import C_TYPE_MAP, SIMULINK_TYPE_MAP  # noqa: F401,E402


@dataclass(frozen=True)
class Signal:
    name: str
    signal_type: str          # data type incl. "enum" (was data_type)
    update_rate_hz: float
    units: str = ""
    range_min: float = 0.0
    range_max: float = 0.0
    scaling: float = 1.0
    offset: float = 0.0
    description: Optional[str] = None
    definition: Optional[str] = None
    data_bits: Optional[int] = None
    xmit_bits: Optional[int] = None
    xmit_bytes: Optional[int] = None

    @property
    def c_type(self) -> str:
        return C_TYPE_MAP[self.signal_type]

    @property
    def simulink_type(self) -> str:
        return SIMULINK_TYPE_MAP[self.signal_type]


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
class IcdModel:
    schema_version: str
    metadata: Metadata
    interfaces: tuple[Interface, ...]

    def all_signals(self):
        """Yield (interface, packet, signal) triples in document order."""
        for iface in self.interfaces:
            for pkt in iface.packets:
                for sig in pkt.signals:
                    yield iface, pkt, sig
