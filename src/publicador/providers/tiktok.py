"""Publicador do TikTok via Content Posting API.

Por padrão usa o escopo video.upload: o vídeo cai na caixa de entrada do app do
usuário para confirmação manual, porque o audit de direct post do TikTok leva
semanas e exige requisitos de UI que um daemon headless não cumpre. O direct
post (video.publish) fica atrás de `direct_post_enabled`, desligado por padrão.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path

import requests

from publicador.oauth_tokens import TikTokTokens
from publicador.providers.base import PublishResult

logger = logging.getLogger(__name__)

_API_BASE = "https://open.tiktokapis.com/v2"
_CHUNK_SIZE = 8 * 1024 * 1024
_MAX_REQUISICOES_POR_MINUTO = 6
_LEGENDA_MAX = 2200


class _LimitadorTaxa:
    """No máximo N chamadas por janela de 60s, por access token."""

    def __init__(self, max_por_minuto: int) -> None:
        self._max = max_por_minuto
        self._chamadas: deque[float] = deque()

    def aguardar_se_necessario(self) -> None:
        agora = time.monotonic()
        while self._chamadas and agora - self._chamadas[0] > 60:
            self._chamadas.popleft()
        if len(self._chamadas) >= self._max:
            espera = 60 - (agora - self._chamadas[0])
            if espera > 0:
                logger.info("Rate limit do TikTok atingido, aguardando %.1fs", espera)
                time.sleep(espera)
                agora = time.monotonic()
                while self._chamadas and agora - self._chamadas[0] > 60:
                    self._chamadas.popleft()
        self._chamadas.append(time.monotonic())


class TikTokProvider:
    def __init__(
        self,
        tokens_path: Path,
        app_credentials_path: Path,
        direct_post_enabled: bool,
        privacy_level: str | None,
    ) -> None:
        self._tokens_path = tokens_path
        self._app_credentials_path = app_credentials_path
        self._direct_post_enabled = direct_post_enabled
        self._privacy_level = privacy_level
        self._limitador = _LimitadorTaxa(_MAX_REQUISICOES_POR_MINUTO)

    def publish(self, file_path: Path, title: str, caption: str) -> PublishResult:
        try:
            # Carregado aqui dentro (não no __init__) para que credenciais
            # ausentes/inválidas virem PublishResult(status="falha") em vez
            # de derrubar o daemon.
            self._tokens = TikTokTokens(self._tokens_path, self._app_credentials_path)

            if self._direct_post_enabled:
                self._validar_privacy_level()

            tamanho = file_path.stat().st_size
            dados_init = self._iniciar_upload(tamanho, caption)
            self._enviar_chunks(dados_init["upload_url"], file_path, tamanho)

            identificador = dados_init.get("publish_id", "")
            destino = "direct post" if self._direct_post_enabled else "caixa de entrada"
            logger.info(
                "Publicado no TikTok (%s): %s (id=%s)",
                destino,
                file_path.name,
                identificador,
            )
            return PublishResult(status="sucesso", platform_id=identificador)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao publicar %s no TikTok", file_path.name)
            return PublishResult(status="falha", error=str(exc))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._tokens.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def _post_json(self, url: str, corpo: dict) -> dict:
        self._limitador.aguardar_se_necessario()
        resposta = requests.post(url, headers=self._headers(), json=corpo, timeout=60)
        if resposta.status_code == 401:
            self._tokens.renovar()
            self._limitador.aguardar_se_necessario()
            resposta = requests.post(
                url, headers=self._headers(), json=corpo, timeout=60
            )
        resposta.raise_for_status()
        payload = resposta.json()
        erro = payload.get("error", {})
        if erro.get("code") not in (None, "ok"):
            raise RuntimeError(f"Erro da API do TikTok em {url}: {erro}")
        return payload["data"]

    def _validar_privacy_level(self) -> None:
        dados = self._post_json(f"{_API_BASE}/post/publish/creator_info/query/", {})
        opcoes = dados.get("privacy_level_options", [])
        if self._privacy_level not in opcoes:
            raise ValueError(
                f"tiktok_privacy_level={self._privacy_level!r} não está entre as "
                f"opções permitidas para esta conta: {opcoes}"
            )

    def _iniciar_upload(self, tamanho: int, caption: str) -> dict:
        total_chunks = max(1, (tamanho + _CHUNK_SIZE - 1) // _CHUNK_SIZE)
        chunk_size = min(_CHUNK_SIZE, tamanho)
        source_info = {
            "source": "FILE_UPLOAD",
            "video_size": tamanho,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        }

        if self._direct_post_enabled:
            url = f"{_API_BASE}/post/publish/video/init/"
            corpo = {
                "post_info": {
                    "title": caption[:_LEGENDA_MAX],
                    "privacy_level": self._privacy_level,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": source_info,
            }
        else:
            url = f"{_API_BASE}/post/publish/inbox/video/init/"
            corpo = {"source_info": source_info}

        return self._post_json(url, corpo)

    def _enviar_chunks(self, upload_url: str, file_path: Path, tamanho: int) -> None:
        with file_path.open("rb") as f:
            enviado = 0
            while enviado < tamanho:
                bloco = f.read(_CHUNK_SIZE)
                if not bloco:
                    break
                inicio = enviado
                fim = enviado + len(bloco) - 1
                self._limitador.aguardar_se_necessario()
                resposta = requests.put(
                    upload_url,
                    data=bloco,
                    headers={
                        "Content-Range": f"bytes {inicio}-{fim}/{tamanho}",
                        "Content-Type": "video/mp4",
                    },
                    timeout=120,
                )
                resposta.raise_for_status()
                enviado += len(bloco)
