"""Loop principal do daemon.

Sem watchdog/inotify de propósito: sobre Samba/CIFS os eventos de escrita do
lado Windows não geram inotify confiável do lado Linux, e o requisito real é
simples ("reler config.json e legenda.txt a cada minuto"), então um
`time.sleep(60)` resolve sem a complexidade de um scheduler.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from publicador import ledger, paths, state
from publicador.config import AppConfig, load_config
from publicador.file_watcher import arquivo_esta_estavel, proximo_video
from publicador.logging_setup import setup_logging
from publicador.oauth_tokens import TikTokTokens
from publicador.providers.base import PublishResult
from publicador.providers.tiktok import TikTokProvider
from publicador.providers.youtube import YouTubeProvider

logger = logging.getLogger(__name__)

_TZ_SAO_PAULO = ZoneInfo("America/Sao_Paulo")
_INTERVALO_TICK_SEGUNDOS = 60


def _ler_legenda(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Não foi possível ler legenda.txt, mantendo a anterior: %s", exc)
        return None


def _purgar_postados(retencao_dias: int) -> None:
    if not paths.POSTADOS.exists():
        return
    limite = time.time() - retencao_dias * 86400
    for arquivo in paths.POSTADOS.iterdir():
        if not arquivo.is_file():
            continue
        try:
            if arquivo.stat().st_mtime < limite:
                arquivo.unlink()
                logger.info("Removido de postados/ por retenção: %s", arquivo.name)
        except OSError:
            logger.exception("Falha ao avaliar/remover %s de postados/", arquivo.name)


def _mover(origem: Path, destino_dir: Path) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / origem.name
    shutil.move(str(origem), str(destino))
    return destino


def _gravar_sidecar_falha(
    destino: Path, youtube: PublishResult, tiktok: PublishResult
) -> None:
    sidecar = destino.with_name(destino.name + ".json")
    sidecar.write_text(
        json.dumps(
            {"youtube": youtube.model_dump(), "tiktok": tiktok.model_dump()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _publicar(video: Path, config: AppConfig, legenda: str) -> None:
    hash_arquivo = ledger.calcular_hash(video)
    entrada_existente = ledger.buscar_publicacao(paths.LEDGER_PATH, hash_arquivo)
    if ledger.ja_publicado_com_sucesso(entrada_existente):
        logger.info(
            "%s já publicado antes (hash duplicado no ledger), movendo para "
            "postados/ sem republicar",
            video.name,
        )
        _mover(video, paths.POSTADOS)
        return

    titulo = video.stem

    youtube_provider = YouTubeProvider(
        tokens_path=paths.TOKENS_YOUTUBE_PATH,
        client_secret_path=paths.CLIENT_SECRET_PATH,
        privacy_status=config.privacy_status_youtube,
    )
    tokens_tiktok = TikTokTokens(
        paths.TOKENS_TIKTOK_PATH, paths.TIKTOK_APP_CREDENTIALS_PATH
    )
    tiktok_provider = TikTokProvider(
        tokens=tokens_tiktok,
        direct_post_enabled=config.tiktok_direct_post_enabled,
        privacy_level=config.tiktok_privacy_level,
    )

    resultado_youtube = youtube_provider.publish(video, titulo, legenda)
    resultado_tiktok = tiktok_provider.publish(video, titulo, legenda)

    ledger.registrar(
        paths.LEDGER_PATH,
        video.name,
        hash_arquivo,
        resultado_youtube,
        resultado_tiktok,
    )

    if resultado_youtube.status == "sucesso" and resultado_tiktok.status == "sucesso":
        _mover(video, paths.POSTADOS)
    else:
        destino = _mover(video, paths.FALHAS)
        _gravar_sidecar_falha(destino, resultado_youtube, resultado_tiktok)


def _tick(
    config_atual: AppConfig | None, legenda_atual: str | None
) -> tuple[AppConfig | None, str | None]:
    nova_config = load_config(paths.CONFIG_PATH)
    if nova_config is not None:
        config_atual = nova_config

    nova_legenda = _ler_legenda(paths.LEGENDA_PATH)
    if nova_legenda is not None:
        legenda_atual = nova_legenda

    if config_atual is None:
        logger.warning("Nenhuma configuração válida disponível ainda, aguardando")
        return config_atual, legenda_atual

    _purgar_postados(config_atual.retencao_postados_dias)

    agora = datetime.now(_TZ_SAO_PAULO)
    hora_atual = agora.strftime("%H:%M")

    # ">=" (não "==") para não perder o dia inteiro se o vídeo ainda estiver
    # sendo copiado ou faltando exatamente no minuto configurado: o daemon
    # continua tentando a cada tick até publicar (e marcar o estado) ou até
    # o dia virar.
    ja_publicou = state.ja_publicou_hoje(paths.STATE_PATH, agora.date())
    if hora_atual >= config_atual.horario_publicacao and not ja_publicou:
        video = proximo_video(paths.A_POSTAR)
        if video is None:
            logger.info(
                "Horário de publicação chegou, mas não há vídeos em 'a postar'"
            )
        elif not arquivo_esta_estavel(video):
            logger.info(
                "%s ainda parece estar sendo copiado, tentando de novo no "
                "próximo tick",
                video.name,
            )
        else:
            try:
                _publicar(video, config_atual, legenda_atual or "")
            except Exception:
                logger.exception("Erro inesperado ao publicar %s", video.name)
            state.marcar_publicado_hoje(paths.STATE_PATH, agora.date())

    return config_atual, legenda_atual


def main() -> None:
    setup_logging(paths.LOG_PATH)
    logger.info("Daemon publicador iniciado")

    config_atual: AppConfig | None = None
    legenda_atual: str | None = None

    while True:
        try:
            config_atual, legenda_atual = _tick(config_atual, legenda_atual)
        except Exception:
            logger.exception("Erro inesperado no tick do daemon")
        time.sleep(_INTERVALO_TICK_SEGUNDOS)


if __name__ == "__main__":
    main()
