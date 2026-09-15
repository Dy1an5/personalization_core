from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class FrozenDomainModel(DomainModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )
