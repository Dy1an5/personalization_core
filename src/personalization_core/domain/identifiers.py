from typing import Annotated

from pydantic import RootModel, StringConstraints

from .base import DomainModel

SmallerStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
    ),
]

BiggerStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
    ),
]


class TenantId(RootModel[SmallerStr]):
    pass


class Namespace(RootModel[SmallerStr]):
    pass


class SubjectId(RootModel[BiggerStr]):
    pass


class SubjectRef(DomainModel):
    tenant_id: TenantId
    namespace: Namespace
    subject_id: SubjectId


class EntityRef(DomainModel):
    subject: SubjectRef
    entity_type: SmallerStr
    external_id: BiggerStr
