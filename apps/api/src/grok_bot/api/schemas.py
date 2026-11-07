from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=200)


class PropertyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    address_line1: str = Field(min_length=1, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=120)
    region: str = Field(min_length=1, max_length=120)
    postal_code: str = Field(min_length=1, max_length=20)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    timezone: str

    @field_validator("timezone")
    @classmethod
    def iana_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be an IANA name") from exc
        return value


class PropertyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address_line1: str | None = Field(default=None, min_length=1, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    region: str | None = Field(default=None, min_length=1, max_length=120)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def iana_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be an IANA name") from exc
        return value

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class UnitWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)


class UnitPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
