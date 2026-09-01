"""Caminhos fixos usados pelo daemon.

A pasta compartilhada via Samba (`SHARE_ROOT`) é onde o usuário mexe pela rede:
vídeos, config.json, legenda.txt e o log. Tudo em `APP_DATA_DIR` é interno do
daemon (credenciais, ledger, estado) e fica fora da pasta compartilhada de
propósito, para não expor tokens OAuth via Samba.
"""

from pathlib import Path

SHARE_ROOT = Path("/srv/publicador")
A_POSTAR = SHARE_ROOT / "a postar"
POSTADOS = SHARE_ROOT / "postados"
FALHAS = SHARE_ROOT / "falhas"
CONFIG_PATH = SHARE_ROOT / "config.json"
LEGENDA_PATH = SHARE_ROOT / "legenda.txt"
LOG_PATH = SHARE_ROOT / "publicador.log"

APP_DATA_DIR = Path("/opt/publicador/data")
LEDGER_PATH = APP_DATA_DIR / "ledger.jsonl"
STATE_PATH = APP_DATA_DIR / "state.json"
TOKENS_YOUTUBE_PATH = APP_DATA_DIR / "tokens_youtube.json"
TOKENS_TIKTOK_PATH = APP_DATA_DIR / "tokens_tiktok.json"
CLIENT_SECRET_PATH = APP_DATA_DIR / "client_secret.json"
TIKTOK_APP_CREDENTIALS_PATH = APP_DATA_DIR / "tiktok_app.json"

# Arquivos que cada plataforma precisa ter presentes para poder publicar.
# Usado para detectar credencial faltando ANTES de tentar o upload.
CREDENCIAIS_POR_PLATAFORMA: dict[str, list[Path]] = {
    "youtube": [CLIENT_SECRET_PATH, TOKENS_YOUTUBE_PATH],
    "tiktok": [TIKTOK_APP_CREDENTIALS_PATH, TOKENS_TIKTOK_PATH],
}
