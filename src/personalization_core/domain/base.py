from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class FrozenDomainModel(DomainModel):
    model_config = ConfigDict(
        frozen=True,
    )


class StrictFrozenDomainModel(FrozenDomainModel):
    model_config = ConfigDict(strict=True)
