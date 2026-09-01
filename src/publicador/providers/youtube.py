"""Publicador do YouTube via Data API v3 (upload resumable, streaming de disco)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from publicador.oauth_tokens import carregar_credenciais_youtube
from publicador.providers.base import PublishResult

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 8 * 1024 * 1024
_TITULO_MAX = 100
_CARACTERES_PROIBIDOS = re.compile(r"[<>]")


def _sanitizar_titulo(titulo: str) -> str:
    return _CARACTERES_PROIBIDOS.sub("", titulo)[:_TITULO_MAX]


class YouTubeProvider:
    def __init__(
        self,
        tokens_path: Path,
        client_secret_path: Path,
        privacy_status: str,
    ) -> None:
        self._tokens_path = tokens_path
        self._client_secret_path = client_secret_path
        self._privacy_status = privacy_status

    def publish(self, file_path: Path, title: str, caption: str) -> PublishResult:
        try:
            creds = carregar_credenciais_youtube(
                self._tokens_path, self._client_secret_path
            )
            youtube = build("youtube", "v3", credentials=creds)

            corpo = {
                "snippet": {
                    "title": _sanitizar_titulo(title),
                    "description": caption,
                },
                "status": {"privacyStatus": self._privacy_status},
            }
            media = MediaFileUpload(
                str(file_path),
                chunksize=_CHUNK_SIZE,
                resumable=True,
                mimetype="video/mp4",
            )
            requisicao = youtube.videos().insert(
                part="snippet,status", body=corpo, media_body=media
            )

            resposta = None
            while resposta is None:
                status, resposta = requisicao.next_chunk()
                if status:
                    logger.info(
                        "Upload YouTube %s: %d%%",
                        file_path.name,
                        int(status.progress() * 100),
                    )

            video_id = resposta["id"]
            logger.info("Publicado no YouTube: %s (id=%s)", file_path.name, video_id)
            return PublishResult(status="sucesso", platform_id=video_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao publicar %s no YouTube", file_path.name)
            return PublishResult(status="falha", error=str(exc))
