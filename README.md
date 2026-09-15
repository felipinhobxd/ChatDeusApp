# ChatDeusApp 🇧🇷

Uma adaptação em português do conceito do **ChatGodApp**, feita para abrir como aplicativo Windows com interface gráfica — sem precisar editar Python ou configurar tudo por variáveis de ambiente.

> Baseado em [DougDougGithub/ChatGodApp](https://github.com/DougDougGithub/ChatGodApp), licenciado sob MIT. Consulte [NOTICE.md](NOTICE.md) e [LICENSE](LICENSE).

## Novidades da v1.1.0

- **personagens animados no overlay**: escolha uma imagem para cada jogador diretamente no `.exe`;
- PNG, JPG, WebP e GIF copiados para `%APPDATA%\ChatDeusApp\characters`;
- tamanho, intensidade, posição X/Y e espelhamento configuráveis;
- movimento automático conforme `(bravo)`, `(animado)`, `(sussurro)` e outros estilos;
- atualização em tempo real do overlay via SSE;
- uma única **Fonte de Navegador** no OBS mostra imagens, nomes e mensagens;
- OBS WebSocket continua opcional para filtros/efeitos avançados.

## Instalação

Baixe `ChatDeusApp.exe` em **Releases** e abra normalmente.

### Personagens animados

1. Abra a aba **Personagens** no ChatDeusApp.
2. Em Jogador 1/2/3 clique em **Escolher...** e selecione PNG, JPG, WebP ou GIF.
3. Ajuste tamanho, intensidade, posição X/Y e espelhamento.
4. Em **Falando**, deixe `auto` para o movimento acompanhar o estilo da fala.
5. Inicie o ChatDeusApp e copie a URL `/overlay` mostrada no painel.
6. No OBS, adicione **uma única Fonte de Navegador** com essa URL.

Não é necessário instalar plugin para a animação básica. O navegador do OBS recebe quando o TTS começa/termina e anima o personagem.

### Twitch

Informe o canal e um token OAuth com permissão para ler o chat. Espectadores entram nas filas com `!jogador1`, `!jogador2` ou `!jogador3` (também aceita `!player1/2/3`).

### Voz

O Azure TTS é opcional e pode ser configurado pela UI. O fallback gTTS em português continua disponível quando habilitado.

### OBS WebSocket

É opcional. Use apenas se quiser ligar/desligar filtros adicionais no OBS durante a fala. Se o OBS estiver fechado, o ChatDeusApp continua funcionando.

## Emoções

Prefixos suportados incluem `(bravo)`, `(alegre)`, `(animado)`, `(esperançoso)`, `(triste)`, `(gritando)`, `(assustado)`, `(sussurro)` e `(aleatorio)`.

## Desenvolvimento

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python chatdeus_app.py
```

Build:

```powershell
pyinstaller ChatDeusApp.spec --noconfirm --clean
.\dist\ChatDeusApp.exe --smoke-test
```

## Licença

MIT. A licença e o aviso de copyright do projeto original foram preservados.
