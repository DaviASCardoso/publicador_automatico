"""Configuração validada com Pydantic.

Um erro de digitação do usuário em config.json nunca pode derrubar o daemon:
`load_config` retorna `None` em qualquer falha de leitura/validação e o chamador
mantém a última configuração válida em memória.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)

_HORARIO_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


PlataformaConhecida = Literal["youtube", "tiktok"]


class AppConfig(BaseModel):
    horario_publicacao: str
    plataformas_ativas: list[PlataformaConhecida] = Field(
        default_factory=lambda: ["youtube", "tiktok"], min_length=1
    )
    privacy_status_youtube: Literal["private", "unlisted", "public"] = "private"
    retencao_postados_dias: int = Field(default=7, ge=0)
    tiktok_direct_post_enabled: bool = False
    tiktok_privacy_level: (
        Literal[
            "PUBLIC_TO_EVERYONE",
            "MUTUAL_FOLLOW_FRIENDS",
            "FOLLOWER_OF_CREATOR",
            "SELF_ONLY",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def _valida_horario(self) -> AppConfig:
        if not _HORARIO_RE.match(self.horario_publicacao):
            raise ValueError('horario_publicacao deve estar no formato "HH:MM"')
        return self

    @model_validator(mode="after")
    def _valida_tiktok_privacy(self) -> AppConfig:
        if self.tiktok_direct_post_enabled and not self.tiktok_privacy_level:
            raise ValueError(
                "tiktok_privacy_level é obrigatório quando "
                "tiktok_direct_post_enabled=true"
            )
        return self


def load_config(path: Path) -> AppConfig | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Não foi possível ler %s: %s", path, exc)
        return None

    try:
        return AppConfig.model_validate_json(raw)
    except ValidationError as exc:
        logger.error(
            "config.json inválido, mantendo a última configuração válida:\n%s", exc
        )
        return None
