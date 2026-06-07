"""API request/response schemas (Pydantic).

These mirror the icdgen domain model but live separately so the wire contract
can evolve without touching the core library. Validation here is intentionally
LOOSE (the authoritative validator is the XSD/jsonschema in icdgen.loader):
busType is freeform, signalType may be blank, and numeric signal fields are
optional — so a partially-complete ICD round-trips through the API.
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
    PriorRevision,
    RevisionEntry,
    Signal,
)

# Dal stays enumerated; busType is freeform; signalType may be blank.
Dal = Literal["A", "B", "C", "D", "E"]


class SignalDTO(BaseModel):
    name: str
    signalType: str = ""                   # blank allowed (in-progress)
    updateRateHz: Optional[float] = None   # optional + non-negative (loader checks)
    units: str = ""
    rangeMin: Optional[float] = None
    rangeMax: Optional[float] = None
    scaling: float = 1.0
    offset: float = 0.0
    description: Optional[str] = None
    definition: Optional[str] = None
    dataBits: Optional[int] = None
    xmitBits: Optional[int] = None
    xmitBytes: Optional[int] = None
    prTicket: Optional[str] = None


class PacketDTO(BaseModel):
    name: str
    description: Optional[str] = None
    signals: list[SignalDTO] = Field(default_factory=list)


class InterfaceDTO(BaseModel):
    id: str
    name: str
    busType: str                            # freeform
    dal: Dal
    sourceLru: str
    destinationLru: str
    owningDocument: str
    description: Optional[str] = None
    packets: list[PacketDTO] = Field(default_factory=list)


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


class PriorRevisionDTO(BaseModel):
    revision: str
    source: str


class IcdDTO(BaseModel):
    schemaVersion: str = "1.0"
    metadata: MetadataDTO
    priorRevisions: list[PriorRevisionDTO] = Field(default_factory=list)
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
    prior = tuple(
        PriorRevision(revision=p.revision, source=p.source)
        for p in dto.priorRevisions
    )
    return IcdModel(schema_version=dto.schemaVersion, metadata=metadata,
                    interfaces=interfaces, prior_revisions=prior)


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
        priorRevisions=[
            PriorRevisionDTO(revision=p.revision, source=p.source)
            for p in model.prior_revisions
        ],
        interfaces=[
            InterfaceDTO(**interface_to_json_dict(i)) for i in model.interfaces
        ],
    )