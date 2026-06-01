from datetime import date
from pydantic import BaseModel, field_validator, model_validator
from src.config.settings import Settings
from validation import (
    validate_name,
    validate_gender,
    validate_birth_date,
)


class ProfileCreateSchema(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str

    @field_validator("first_name", "last_name")
    @classmethod
    def check_names(cls, value: str) -> str:
        validate_name(value)
        return value

    @field_validator("gender")
    @classmethod
    def check_gender(cls, value: str) -> str:
        validate_gender(value)
        return value

    @field_validator("date_of_birth")
    @classmethod
    def check_birth_date(cls, value: date) -> date:
        validate_birth_date(value)
        return value

    @field_validator("info")
    @classmethod
    def check_info(cls, value: str) -> str:
        if not value or value.isspace():
            raise ValueError("Info cannot be empty or consist only of spaces.")
        return value


class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: str

    @model_validator(mode="after")
    def set_avatar_url(self) -> "ProfileResponseSchema":
        settings = Settings()
        if not self.avatar.startswith("http"):
            self.avatar = f"{settings.S3_STORAGE_URL}/{self.avatar}"
        return self

    class Config:
        from_attributes = True
