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
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from publicador import ledger, paths, state
from publicador.config import AppConfig, load_config
from publicador.file_watcher import arquivo_esta_estavel, proximo_video
from publicador.logging_setup import setup_logging
from publicador.providers.base import PublisherProvider, PublishResult
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


def _gravar_sidecar_falha(destino: Path, resultados: dict[str, PublishResult]) -> None:
    sidecar = destino.with_name(destino.name + ".json")
    sidecar.write_text(
        json.dumps(
            {p: r.model_dump() for p, r in resultados.items()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _resultado_anterior(
    entrada_existente: dict | None, plataforma: str
) -> PublishResult | None:
    """Reaproveita o resultado de uma tentativa anterior (do ledger) se ela
    já tinha tido sucesso nessa plataforma — evita reenviar/duplicar."""
    if entrada_existente is None:
        return None
    dados = entrada_existente.get(plataforma, {})
    if dados.get("status") != "sucesso":
        return None
    return PublishResult.model_validate(dados)


def _credenciais_faltando(plataforma: str) -> list[Path]:
    return [
        caminho
        for caminho in paths.CREDENCIAIS_POR_PLATAFORMA[plataforma]
        if not caminho.exists()
    ]


def _construir_provider(plataforma: str, config: AppConfig) -> PublisherProvider:
    if plataforma == "youtube":
        return YouTubeProvider(
            tokens_path=paths.TOKENS_YOUTUBE_PATH,
            client_secret_path=paths.CLIENT_SECRET_PATH,
            privacy_status=config.privacy_status_youtube,
        )
    if plataforma == "tiktok":
        return TikTokProvider(
            tokens_path=paths.TOKENS_TIKTOK_PATH,
            app_credentials_path=paths.TIKTOK_APP_CREDENTIALS_PATH,
            direct_post_enabled=config.tiktok_direct_post_enabled,
            privacy_level=config.tiktok_privacy_level,
        )
    raise ValueError(f"Plataforma desconhecida: {plataforma}")


def _publicar(video: Path, config: AppConfig, legenda: str) -> None:
    hash_arquivo = ledger.calcular_hash(video)
    entrada_existente = ledger.buscar_publicacao(paths.LEDGER_PATH, hash_arquivo)
    if ledger.ja_publicado_com_sucesso(entrada_existente, config.plataformas_ativas):
        logger.info(
            "%s já publicado antes (hash duplicado no ledger) em todas as "
            "plataformas ativas, movendo para postados/ sem republicar",
            video.name,
        )
        _mover(video, paths.POSTADOS)
        return

    titulo = video.stem
    resultados: dict[str, PublishResult] = {}

    # Filtro logo no início: só entram no ciclo as plataformas de
    # config.plataformas_ativas — nenhuma tentativa de upload é feita para
    # quem não está na lista.
    for plataforma in config.plataformas_ativas:
        resultado_anterior = _resultado_anterior(entrada_existente, plataforma)
        if resultado_anterior is not None:
            logger.info(
                "%s já tinha sucesso em %s, não reenviando", video.name, plataforma
            )
            resultados[plataforma] = resultado_anterior
            continue

        faltando = _credenciais_faltando(plataforma)
        if faltando:
            caminhos = ", ".join(str(c) for c in faltando)
            logger.error(
                "Credencial ausente para %s ao publicar %s — arquivo(s) "
                "esperado(s) em: %s. Plataforma pulada, sem tentar upload.",
                plataforma,
                video.name,
                caminhos,
            )
            resultados[plataforma] = PublishResult(
                status="falha", error=f"Credencial ausente em: {caminhos}"
            )
            continue

        provider = _construir_provider(plataforma, config)
        resultados[plataforma] = provider.publish(video, titulo, legenda)

    ledger.registrar(paths.LEDGER_PATH, video.name, hash_arquivo, resultados)

    if all(r.status == "sucesso" for r in resultados.values()):
        _mover(video, paths.POSTADOS)
    else:
        destino = _mover(video, paths.FALHAS)
        _gravar_sidecar_falha(destino, resultados)


def _horario_pendente(
    horarios: list[str], hora_atual: str, hoje: date
) -> str | None:
    """O horário mais antigo já vencido (<= hora_atual) que ainda não foi
    publicado hoje, ou None se nenhum estiver pendente.

    "<=" (não "==") para não perder o horário se o vídeo ainda estiver sendo
    copiado ou faltando exatamente no minuto configurado: o daemon continua
    tentando a cada tick até publicar (e marcar o estado) ou até o dia virar.
    Se o daemon ficar fora do ar e vários horários vencerem juntos, um por
    tick é resolvido, na ordem — o próximo tick já pega o horário seguinte.
    """
    pendentes = sorted(
        h
        for h in horarios
        if h <= hora_atual and not state.ja_publicou_neste_horario(
            paths.STATE_PATH, hoje, h
        )
    )
    return pendentes[0] if pendentes else None


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

    horario = _horario_pendente(
        config_atual.horarios_publicacao, hora_atual, agora.date()
    )
    if horario is not None:
        video = proximo_video(paths.A_POSTAR)
        if video is None:
            logger.info(
                "Horário de publicação %s chegou, mas não há vídeos em "
                "'a postar'",
                horario,
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
            state.marcar_publicado(paths.STATE_PATH, agora.date(), horario)

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
