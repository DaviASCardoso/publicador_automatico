# Tutorial: credenciais, instalação e primeira execução

Este tutorial cobre três partes: (1) obter as credenciais no Google Cloud e no
TikTok for Developers, (2) instalar o daemon no notebook Ubuntu, (3) autorizar
as contas e subir o serviço.

---

## 1. Google Cloud (YouTube Data API v3)

### 1.1 Criar o projeto

1. Acesse [console.cloud.google.com](https://console.cloud.google.com/) com a
   conta Google dona do canal do YouTube.
2. No topo, clique no seletor de projeto → **Novo projeto**. Dê um nome (ex.:
   `publicador-cortes`) e crie.

### 1.2 Habilitar a YouTube Data API v3

1. Com o projeto selecionado, vá em **APIs e Serviços → Biblioteca**.
2. Procure por **YouTube Data API v3** e clique em **Ativar**.

### 1.3 Configurar a tela de consentimento OAuth

1. Vá em **APIs e Serviços → Tela de consentimento OAuth**.
2. Tipo de usuário: **Externo** (contas pessoais do Google não têm Google
   Workspace, então é essa a única opção disponível).
3. Preencha nome do app, e-mail de suporte e e-mail do desenvolvedor (os
   obrigatórios). Não precisa de site nem política de privacidade para o
   próximo passo funcionar.
4. Em **Escopos**, adicione `.../auth/youtube.upload`.
5. Em **Usuários de teste**, adicione o e-mail da própria conta do YouTube.

### 1.4 Publicar em produção — passo obrigatório

Por padrão, o app fica em status **Testando**. **Isso quebra o daemon**:
nesse status, o Google emite `refresh_token`s que **expiram em 7 dias**, e o
serviço vai parar de conseguir publicar sem aviso assim que o token expirar.

1. Na tela de consentimento OAuth, clique em **Publicar app** → confirme
   **Enviar para produção**.
2. Como o app só será usado por você, o Google vai mostrar um aviso de "app
   não verificado" na hora de autorizar (passo 1.6) — isso é esperado e
   seguro de ignorar (clique em **Avançado → Acessar [nome do app] (não
   seguro)**). A verificação completa do Google (que remove esse aviso) é um
   processo de revisão manual de vários dias, pensado para apps com muitos
   usuários externos; para um daemon de uso pessoal não é necessária. O que
   importa aqui é só o status **Em produção**, que já elimina a expiração de
   7 dias do refresh token.

### 1.5 Criar a credencial OAuth e baixar o client_secret.json

1. Vá em **APIs e Serviços → Credenciais → Criar credenciais → ID do cliente
   OAuth**.
2. Tipo de aplicativo: **Aplicativo para computador** (Desktop app) — esse
   tipo aceita qualquer porta `localhost` como redirect URI automaticamente,
   o que o script de bootstrap headless (seção 3) depende.
3. Baixe o JSON gerado e copie para o notebook em:
   ```
   /opt/publicador/data/client_secret.json
   ```

### 1.6 O audit de conformidade — por que os vídeos ficam privados sem ele

Mesmo com o app publicado em produção, existe uma segunda trava, específica
da YouTube Data API: **todo vídeo enviado via `videos.insert` por um projeto
que não passou pelo audit de conformidade da YouTube API é forçado a
`private`**, independentemente do `privacyStatus` enviado na requisição. Essa
regra vale para qualquer projeto criado depois de 28/07/2020.

Para poder publicar como `public`/`unlisted` de verdade, solicite o audit:

- **Formulário**: https://support.google.com/youtube/contact/yt_api_form

O processo pede uma descrição do caso de uso e pode levar alguns dias. Até
ele ser aprovado, configure `privacy_status_youtube` como `"private"` no
`config.json` — o daemon publica normalmente, só o vídeo fica visível apenas
para você até liberar.

---

## 2. TikTok for Developers (Content Posting API)

### 2.1 Criar o app

1. Acesse [developers.tiktok.com](https://developers.tiktok.com/) e faça
   login com a conta TikTok que vai publicar os vídeos.
2. Vá em **Manage apps → Create an app**. Preencha nome e categoria.

### 2.2 Adicionar o produto Content Posting API

1. Dentro do app criado, vá em **Add products** e adicione **Content Posting
   API**.
2. Em **Login Kit** (necessário para o OAuth), adicione a redirect URI usada
   pelo script de bootstrap headless:
   ```
   http://localhost:8921/callback
   ```
   Se o portal recusar `http://localhost` como redirect URI (algumas contas
   exigem domínio HTTPS verificado), a alternativa é registrar um domínio
   próprio verificado e trocar `_TIKTOK_REDIRECT_URI` em
   `scripts/bootstrap_oauth.py` de acordo.

### 2.3 Escopos

Solicite, na tela de escopos do app:

- `user.info.basic` — obrigatório para o fluxo OAuth funcionar.
- `video.upload` — o modo padrão usado por este daemon: o vídeo cai na caixa
  de entrada do app do TikTok no celular, e você confirma a postagem por lá.
- `video.publish` — **só peça este se for usar o direct post** (postagem
  automática sem confirmação manual). Ver aviso na seção 2.4.

### 2.4 Client key e client secret

1. Na página **Basic Information** (ou **Credentials**) do app, copie
   **Client key** e **Client secret**.
2. Crie no notebook o arquivo:
   ```
   /opt/publicador/data/tiktok_app.json
   ```
   com o conteúdo:
   ```json
   {
     "client_key": "SEU_CLIENT_KEY",
     "client_secret": "SEU_CLIENT_SECRET"
   }
   ```

### 2.5 App em modo Sandbox — adicione seu usuário de teste

Enquanto o app não passar pelo audit, ele opera em modo de desenvolvimento:
adicione sua própria conta TikTok como "target user"/testador no portal
(normalmente em **Sandbox** ou **Target users** dentro do app), senão o OAuth
vai recusar autorizar essa conta.

### 2.6 O audit — por que o conteúdo fica restrito a privado

Um **client não auditado** do TikTok tem duas restrições:

- Todo conteúdo postado fica forçado a visualização **`SELF_ONLY`** (só você
  vê), mesmo pedindo outro `privacy_level`.
- Limite de até 5 posts por 24h.

O modo padrão deste daemon (`video.upload`, caixa de entrada) já contorna boa
parte disso porque você confirma manualmente cada post no app — mas se quiser
ativar o **direct post** (`tiktok_direct_post_enabled: true` no
`config.json`, ver seção 4), vai precisar do audit para o conteúdo sair de
`SELF_ONLY`.

- **Formulário/portal de audit**: https://developers.tiktok.com/application/content-posting-api

O audit do TikTok também tem requisitos de UI que um daemon headless não
cumpre sozinho (fluxo de autorização visível ao usuário, telas de revisão
antes de postar etc.) — por isso o padrão deste projeto é o modo caixa de
entrada, que não depende do audit para funcionar de forma útil no dia a dia.

---

## 3. Instalação no Ubuntu Server

### 3.1 Usuário de sistema e diretórios

```bash
sudo useradd --system --create-home --home-dir /opt/publicador --shell /usr/sbin/nologin publicador
sudo mkdir -p /opt/publicador/data
sudo chown -R publicador:publicador /opt/publicador
```

`/srv/publicador` (e as subpastas `a postar`, `postados`, `falhas`) já existem
pelo Samba — dê ao usuário `publicador` permissão de leitura/escrita/exclusão
sobre essa árvore (ajuste conforme o dono atual da pasta, por exemplo
adicionando `publicador` ao grupo que já é dono do compartilhamento, ou:

```bash
sudo chown -R publicador:publicador /srv/publicador
```

### 3.2 Copiar o projeto e instalar dependências com uv

```bash
# no notebook, como root ou com sudo
curl -LsSf https://astral.sh/uv/install.sh | sh   # se uv ainda não estiver instalado

sudo -u publicador git clone <url-do-repo> /opt/publicador   # ou copie os arquivos manualmente
cd /opt/publicador
sudo -u publicador uv sync
```

Isso cria `/opt/publicador/.venv` com Python 3.12 e as dependências do
`pyproject.toml`.

### 3.3 Colocar as credenciais

Confirme que os três arquivos abaixo existem, com dono `publicador` e
permissão `600`:

```
/opt/publicador/data/client_secret.json    (seção 1.5)
/opt/publicador/data/tiktok_app.json       (seção 2.4)
```

### 3.4 config.json e legenda.txt

Em `/srv/publicador/config.json` (crie se ainda não existir):

```json
{
  "horario_publicacao": "18:00",
  "plataformas_ativas": ["youtube", "tiktok"],
  "privacy_status_youtube": "private",
  "retencao_postados_dias": 7,
  "tiktok_direct_post_enabled": false,
  "tiktok_privacy_level": null
}
```

- `horario_publicacao`: `"HH:MM"`, 24h.
- `plataformas_ativas`: lista com as plataformas em que o daemon deve
  publicar — aceita `"youtube"` e `"tiktok"`. Não pode ficar vazia. Se a
  chave for omitida, o padrão é as duas ativas (`["youtube", "tiktok"]`), pra
  não quebrar quem já está rodando sem essa chave no config.json.

  **Para começar só com YouTube** (por exemplo, enquanto o audit do TikTok
  não sai — seção 2.6), deixe a lista com um item só:
  ```json
  "plataformas_ativas": ["youtube"]
  ```
  Com isso o daemon nem tenta o TikTok: não instancia o provider, não gasta
  chamada de API, e um vídeo publicado com sucesso só no YouTube já vai
  direto pra `postados/` (não fica esperando o TikTok pra ser considerado
  publicado). Quando as credenciais do TikTok estiverem prontas, basta
  voltar a lista pra `["youtube", "tiktok"]` — não precisa reiniciar o
  serviço, o daemon relê o config.json a cada minuto.

  Se uma plataforma estiver na lista mas faltar o arquivo de credencial
  correspondente (seção 3.3), o daemon não tenta o upload nem quebra: grava
  no `publicador.log` uma linha dizendo qual credencial está faltando e em
  qual caminho ela é esperada, e trata aquele vídeo como falha só daquela
  plataforma (vai pra `falhas/` com o sidecar explicando, a não ser que as
  outras plataformas ativas também tenham dado certo nesse vídeo antes).
- `privacy_status_youtube`: `"private"`, `"unlisted"` ou `"public"` (veja
  seção 1.6 antes de usar `"public"`).
- `retencao_postados_dias`: dias que um vídeo fica em `postados/` antes de ser
  apagado; `0` apaga imediatamente. Padrão: `7`.
- `tiktok_direct_post_enabled`: deixe `false` até ter o audit do TikTok
  aprovado (seção 2.6). Só é relevante se `"tiktok"` estiver em
  `plataformas_ativas`.
- `tiktok_privacy_level`: obrigatório só se `tiktok_direct_post_enabled` for
  `true`. Um de `"PUBLIC_TO_EVERYONE"`, `"MUTUAL_FOLLOW_FRIENDS"`,
  `"FOLLOWER_OF_CREATOR"`, `"SELF_ONLY"`.

Em `/srv/publicador/legenda.txt`, coloque o texto que vai para a descrição do
YouTube e a legenda do TikTok em todo vídeo (é o mesmo texto para todos).

Esses dois arquivos podem ser editados a qualquer momento pelo Explorer, pela
rede — o daemon relê os dois a cada minuto, sem precisar reiniciar nada.

### 3.5 Rodar o bootstrap OAuth (uma vez)

Em um terminal do seu PC Windows, abra o túnel:

```
ssh -L 8921:localhost:8921 usuario@notebook
```

No próprio SSH (pode ser a mesma sessão), rode:

```bash
cd /opt/publicador
sudo -u publicador .venv/bin/python scripts/bootstrap_oauth.py
```

O script imprime uma URL para o YouTube — abra no navegador do PC Windows,
faça login e autorize. Repete o mesmo para o TikTok logo em seguida. Os
tokens são salvos em `/opt/publicador/data/tokens_youtube.json` e
`tokens_tiktok.json`, com permissão `600`.

### 3.6 Instalar e iniciar o systemd service

```bash
sudo cp /opt/publicador/systemd/publicador.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now publicador.service
sudo systemctl status publicador.service
journalctl -u publicador.service -f
```

A partir daqui, o fluxo do dia a dia é: copiar os `.mp4` do Opus Clip para
`\\notebook\publicador\a postar` pelo Explorer, e ajustar
`config.json`/`legenda.txt` quando quiser — tudo pela rede, sem SSH.
