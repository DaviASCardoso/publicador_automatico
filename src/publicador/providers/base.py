"""Abstração comum a qualquer plataforma de publicação.

Adicionar uma plataforma nova é escrever uma classe que implementa
`PublisherProvider` — nada mais no resto do daemon precisa mudar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel


class PublishResult(BaseModel):
    status: Literal["sucesso", "falha"]
    platform_id: str | None = None
    error: str | None = None


class PublisherProvider(Protocol):
    def publish(self, file_path: Path, title: str, caption: str) -> PublishResult: ...
