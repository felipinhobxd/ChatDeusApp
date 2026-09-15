# ChatDeusApp 🇧🇷

Uma adaptação em português do conceito do **ChatGodApp**, feita para abrir como aplicativo Windows com interface gráfica — sem precisar editar Python, procurar OAuth token manualmente ou configurar tudo por variáveis de ambiente.

> Baseado em [DougDougGithub/ChatGodApp](https://github.com/DougDougGithub/ChatGodApp), licenciado sob MIT. Consulte [NOTICE.md](NOTICE.md) e [LICENSE](LICENSE).

## Novidades da v1.2.0

- **Entrar com Twitch** diretamente pelo aplicativo;
- login oficial por Device Code Flow para cliente público, sem Client Secret no `.exe`;
- navegador abre automaticamente para autorizar a conta;
- canal/login detectado automaticamente;
- access token validado e refresh token renovado automaticamente;
- leitura do chat por **EventSub WebSocket**;
- `user:read:chat` como única permissão pedida pelo fluxo automático;
- modo antigo de canal + OAuth token preservado apenas para compatibilidade;
- personagens animados no overlay do OBS continuam disponíveis.

## Instalação e primeiro uso

1. Baixe `ChatDeusApp.exe` em **Releases** e abra normalmente.
2. Clique em **Entrar com Twitch** — ou simplesmente em **Iniciar ChatDeusApp** no primeiro uso.
3. O navegador abrirá a página oficial da Twitch. Autorize sua conta.
4. O aplicativo mostrará `Twitch: conectado como @seunome ✓` e configurará o canal automaticamente.
5. Inicie o ChatDeusApp e use o painel local que será aberto no navegador.

Você não precisa criar nem copiar um OAuth token manualmente. O Client ID da aplicação é público; nenhum Client Secret é colocado no executável. Access token e refresh token ficam no arquivo de configuração local do usuário em `%APPDATA%\ChatDeusApp\config.json` e não são enviados ao repositório.

### Compatibilidade com versões antigas

Quem já usava a v1.0/v1.1 com **Canal + Token OAuth** continua funcionando. Esse método fica na seção **Compatibilidade / modo manual** e pode ser desativado assim que você fizer login pelo botão novo.

## Como funcionam os jogadores

Espectadores entram nas filas com:

- `!jogador1`
- `!jogador2`
- `!jogador3`

Também são aceitos `!player1`, `!player2` e `!player3`. No painel você pode sortear alguém da fila ou escolher um usuário manualmente. As mensagens do usuário escolhido aparecem no overlay e podem ser lidas por TTS.

## Personagens animados no OBS

1. Abra a aba **Personagens**.
2. Em Jogador 1/2/3 clique em **Escolher...** e selecione PNG, JPG, WebP ou GIF.
3. Ajuste tamanho, intensidade, posição X/Y e espelhamento.
4. Em **Falando**, deixe `auto` para o movimento acompanhar o estilo da fala.
5. Copie a URL `/overlay` mostrada no painel.
6. No OBS, adicione **uma única Fonte de Navegador** usando essa URL.

Não é necessário plugin para a animação básica. O OBS WebSocket continua opcional e serve apenas para filtros/efeitos extras.

## Voz

O Azure TTS é opcional e pode ser configurado pela interface. O fallback gTTS em português continua disponível quando habilitado.

Prefixos de emoção suportados incluem `(bravo)`, `(alegre)`, `(animado)`, `(esperançoso)`, `(triste)`, `(gritando)`, `(assustado)`, `(sussurro)` e `(aleatorio)`.

## Desenvolvimento

Recomendado: Python 3.11 ou 3.12.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python chatdeus_app.py
```

Build local:

```powershell
pyinstaller ChatDeusApp.spec --noconfirm --clean
.\dist\ChatDeusApp.exe --smoke-test
```

## Licença

MIT. A licença e o aviso de copyright do projeto original foram preservados.
