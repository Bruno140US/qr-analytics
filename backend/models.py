from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from urllib.parse import urlparse


class QRCode(BaseModel):
    id: int
    qr_id: str
    destination_url: str
    name: Optional[str] = None
    created_at: datetime


class QRCodeCreate(BaseModel):
    destination_url: str
    name: Optional[str] = None

    @field_validator("destination_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("URL de destino não pode ser vazia")
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL deve começar com http:// ou https://")
        if not parsed.netloc:
            raise ValueError("URL inválida")
        return v

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class QRCodeUpdate(BaseModel):
    destination_url: Optional[str] = None
    name: Optional[str] = None

    @field_validator("destination_url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("URL deve começar com http:// ou https://")
        return v

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class Scan(BaseModel):
    id: int
    qr_id: str
    timestamp: datetime
    ip: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    device: Optional[str] = None
    os: Optional[str] = None
    browser: Optional[str] = None