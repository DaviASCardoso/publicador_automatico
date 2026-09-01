"""Carregamento e renovação de tokens OAuth do YouTube e do TikTok.

Os tokens vivem em /opt/publicador/data, fora da pasta compartilhada via Samba.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def _salvar_json(path: Path, dados: dict) -> None:
    path.write_text(json.dumps(dados), encoding="utf-8")
    os.chmod(path, 0o600)


def carregar_credenciais_youtube(
    tokens_path: Path, client_secret_path: Path
) -> Credentials:
    """Sempre renova o access token: o daemon publica no máximo 1x/dia, então o
    access token guardado quase sempre já expirou (validade de ~1h)."""
    tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
    client_info = json.loads(client_secret_path.read_text(encoding="utf-8"))
    client = client_info.get("installed", client_info.get("web", {}))

    creds = Credentials(
        token=None,
        refresh_token=tokens["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        scopes=[YOUTUBE_UPLOAD_SCOPE],
    )
    creds.refresh(GoogleAuthRequest())
    _salvar_json(tokens_path, {"refresh_token": creds.refresh_token})
    return creds


class TikTokTokens:
    """Guarda o access_token em memória e persiste em disco a cada renovação,
    já que o TikTok rotaciona o refresh_token a cada uso."""

    def __init__(self, tokens_path: Path, app_credentials_path: Path) -> None:
        self._tokens_path = tokens_path
        self._app = json.loads(app_credentials_path.read_text(encoding="utf-8"))
        self._dados = json.loads(tokens_path.read_text(encoding="utf-8"))

    @property
    def access_token(self) -> str:
        return self._dados["access_token"]

    def renovar(self) -> None:
        resposta = requests.post(
            TIKTOK_TOKEN_URL,
            data={
                "client_key": self._app["client_key"],
                "client_secret": self._app["client_secret"],
                "grant_type": "refresh_token",
                "refresh_token": self._dados["refresh_token"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resposta.raise_for_status()
        novo = resposta.json()
        self._dados["access_token"] = novo["access_token"]
        self._dados["refresh_token"] = novo["refresh_token"]
        _salvar_json(self._tokens_path, self._dados)
        logger.info("Token do TikTok renovado com sucesso")
