"""Autorização OAuth do YouTube e do TikTok — rode isto UMA VEZ via SSH.

O notebook é headless (sem navegador), então o fluxo abre um servidor local na
própria máquina e espera o redirect de autorização chegar por lá. Para isso
funcionar, abra em outro terminal do seu PC Windows um túnel SSH apontando
para a mesma porta ANTES de rodar este script:

    ssh -L 8921:localhost:8921 usuario@notebook

Com o túnel aberto, este script imprime uma URL — abra essa URL num navegador
do seu PC Windows. O navegador vai bater em localhost:8921 do seu PC, que o
túnel SSH encaminha para o servidor que este script abriu no notebook, e o
código de autorização é capturado automaticamente (sem precisar copiar e
colar nada).

Pré-requisitos (ver TUTORIAL.md):
  - /opt/publicador/data/client_secret.json (credencial OAuth do Google)
  - /opt/publicador/data/tiktok_app.json com {"client_key": "...",
    "client_secret": "..."}
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from publicador import paths  # noqa: E402

_PORTA_CALLBACK = 8921
_YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_TIKTOK_SCOPES = "user.info.basic,video.upload"
_TIKTOK_REDIRECT_URI = f"http://localhost:{_PORTA_CALLBACK}/callback"
_TIMEOUT_SEGUNDOS = 300


def _autorizar_youtube() -> None:
    print("\n=== Autorizando YouTube ===")
    print(
        f"Túnel necessário: ssh -L {_PORTA_CALLBACK}:localhost:{_PORTA_CALLBACK} "
        "usuario@notebook\n"
    )
    flow = InstalledAppFlow.from_client_secrets_file(
        str(paths.CLIENT_SECRET_PATH), scopes=_YOUTUBE_SCOPES
    )
    creds = flow.run_local_server(
        host="localhost", port=_PORTA_CALLBACK, open_browser=False
    )

    paths.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    paths.TOKENS_YOUTUBE_PATH.write_text(
        json.dumps({"refresh_token": creds.refresh_token}), encoding="utf-8"
    )
    paths.TOKENS_YOUTUBE_PATH.chmod(0o600)
    print(f"Tokens do YouTube salvos em {paths.TOKENS_YOUTUBE_PATH}")


class _TikTokCallbackHandler(BaseHTTPRequestHandler):
    codigo_recebido: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        query = parse_qs(urlparse(self.path).query)
        if "code" in query:
            _TikTokCallbackHandler.codigo_recebido = query["code"][0]
            corpo = b"Autorizacao recebida, pode fechar esta aba."
        else:
            corpo = b"Nenhum codigo de autorizacao recebido."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _autorizar_tiktok() -> None:
    print("\n=== Autorizando TikTok ===")
    app_credentials = json.loads(
        paths.TIKTOK_APP_CREDENTIALS_PATH.read_text(encoding="utf-8")
    )
    client_key = app_credentials["client_key"]
    client_secret = app_credentials["client_secret"]

    url_autorizacao = (
        "https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={client_key}"
        f"&scope={_TIKTOK_SCOPES}"
        "&response_type=code"
        f"&redirect_uri={_TIKTOK_REDIRECT_URI}"
        "&state=bootstrap"
    )
    print(
        f"Túnel necessário (pode reaproveitar o mesmo do YouTube): "
        f"ssh -L {_PORTA_CALLBACK}:localhost:{_PORTA_CALLBACK} usuario@notebook\n\n"
        "Abra esta URL no navegador do seu PC Windows:\n"
        f"{url_autorizacao}\n"
    )

    servidor = HTTPServer(("localhost", _PORTA_CALLBACK), _TikTokCallbackHandler)
    thread = threading.Thread(target=servidor.handle_request)
    thread.start()
    thread.join(timeout=_TIMEOUT_SEGUNDOS)
    servidor.server_close()

    codigo = _TikTokCallbackHandler.codigo_recebido
    if not codigo:
        print(
            f"Não recebi o código de autorização do TikTok em "
            f"{_TIMEOUT_SEGUNDOS}s. Rode o script de novo."
        )
        return

    resposta = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": codigo,
            "grant_type": "authorization_code",
            "redirect_uri": _TIKTOK_REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resposta.raise_for_status()
    dados = resposta.json()

    paths.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    paths.TOKENS_TIKTOK_PATH.write_text(
        json.dumps(
            {
                "access_token": dados["access_token"],
                "refresh_token": dados["refresh_token"],
            }
        ),
        encoding="utf-8",
    )
    paths.TOKENS_TIKTOK_PATH.chmod(0o600)
    print(f"Tokens do TikTok salvos em {paths.TOKENS_TIKTOK_PATH}")


def main() -> None:
    if not paths.CLIENT_SECRET_PATH.exists():
        sys.exit(f"Faltando {paths.CLIENT_SECRET_PATH} — veja o TUTORIAL.md")
    if not paths.TIKTOK_APP_CREDENTIALS_PATH.exists():
        sys.exit(f"Faltando {paths.TIKTOK_APP_CREDENTIALS_PATH} — veja o TUTORIAL.md")

    _autorizar_youtube()
    _autorizar_tiktok()
    print("\nBootstrap concluído. Pode instalar e iniciar o systemd service agora.")


if __name__ == "__main__":
    main()
