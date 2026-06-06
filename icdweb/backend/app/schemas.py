"""API request/response schemas (Pydantic).

These mirror the icdgen domain model but live separately so the wire contract
can evolve without touching the core library. Conversion helpers translate
between these DTOs and the frozen icdgen dataclasses.

Validation here is intentionally light (types/enums only). Authoritative
validation is always the XSD/jsonschema in icdgen.loader, so the form editor
and a hand-authored file go through the identical gate.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from icdgen.signal_codec import (
    interface_from_json_dict,
    interface_to_json_dict,
    signal_from_json_dict,
    signal_to_json_dict,
)
from icdgen.model import (
    IcdModel,
    Interface,
    Metadata,
    RevisionEntry,
    Signal,
)

BusType = Literal["ARINC429", "MIL-STD-1553", "ARINC664", "CAN", "DISCRETE", "ANALOG"]
Dal = Literal["A", "B", "C", "D", "E"]
DataType = Literal[
    "bool", "uint8", "int8", "uint16", "int16",
    "uint32", "int32", "uint64", "int64", "float32", "float64",
]
Direction = Literal["TX", "RX"]


class SignalDTO(BaseModel):
    name: str
    dataType: DataType
    direction: Direction
    units: str = ""
    rangeMin: float = 0.0
    rangeMax: float = 0.0
    updateRateHz: float = 1.0
    scaling: float = 1.0
    offset: float = 0.0
    encoding: Optional[str] = None
    description: Optional[str] = None
    optional: bool = False


class InterfaceDTO(BaseModel):
    id: str
    name: str
    busType: BusType
    dal: Dal
    sourceLru: str
    destinationLru: str
    owningDocument: str
    description: Optional[str] = None
    signals: list[SignalDTO] = Field(default_factory=list)


class RevisionEntryDTO(BaseModel):
    revision: str
    date: str
    author: str
    description: str


class MetadataDTO(BaseModel):
    documentId: str
    documentTitle: str
    program: str
    revision: str
    revisionDate: str
    author: str
    revisionHistory: list[RevisionEntryDTO] = Field(default_factory=list)


class IcdDTO(BaseModel):
    schemaVersion: str = "1.0"
    metadata: MetadataDTO
    interfaces: list[InterfaceDTO] = Field(default_factory=list)


# -------- DTO <-> domain conversions --------
def dto_to_model(dto: IcdDTO) -> IcdModel:
    metadata = Metadata(
        document_id=dto.metadata.documentId,
        document_title=dto.metadata.documentTitle,
        program=dto.metadata.program,
        revision=dto.metadata.revision,
        revision_date=dto.metadata.revisionDate,
        author=dto.metadata.author,
        revision_history=tuple(
            RevisionEntry(e.revision, e.date, e.author, e.description)
            for e in dto.metadata.revisionHistory
        ),
    )
    interfaces = tuple(
        interface_from_json_dict(i.model_dump()) for i in dto.interfaces
    )
    return IcdModel(schema_version=dto.schemaVersion, metadata=metadata,
                    interfaces=interfaces)


def model_to_dto(model: IcdModel) -> IcdDTO:
    return IcdDTO(
        schemaVersion=model.schema_version,
        metadata=MetadataDTO(
            documentId=model.metadata.document_id,
            documentTitle=model.metadata.document_title,
            program=model.metadata.program,
            revision=model.metadata.revision,
            revisionDate=model.metadata.revision_date,
            author=model.metadata.author,
            revisionHistory=[
                RevisionEntryDTO(revision=e.revision, date=e.date,
                                 author=e.author, description=e.description)
                for e in model.metadata.revision_history
            ],
        ),
        interfaces=[
            InterfaceDTO(**interface_to_json_dict(i)) for i in model.interfaces
        ],
    )
