# ChatDeusApp 🇧🇷

Uma adaptação em português do conceito do **ChatGodApp**, feita para abrir como aplicativo Windows com interface gráfica — sem precisar editar Python ou configurar tudo por variáveis de ambiente.

> Baseado em [DougDougGithub/ChatGodApp](https://github.com/DougDougGithub/ChatGodApp), licenciado sob MIT. Consulte [NOTICE.md](NOTICE.md) e [LICENSE](LICENSE).

## O que mudou

- interface desktop em **PT-BR** para configurar tudo;
- canal e token da Twitch configuráveis pela UI;
- Microsoft Azure TTS configurável pela UI;
- vozes brasileiras por padrão;
- fallback automático para **gTTS em português** quando o Azure não estiver disponível;
- OBS WebSocket opcional — se o OBS estiver fechado, o app continua funcionando;
- painel moderno para escolher/sortear até 3 jogadores;
- overlay transparente dedicado para usar como **Browser Source** no OBS;
- comandos em português (`!jogador1`, `!jogador2`, `!jogador3`) e compatibilidade com `!player1/2/3`;
- fila de áudio para evitar TTS sobreposto;
- configuração persistida no `%APPDATA%\ChatDeusApp\config.json`;
- testes automatizados e build do `.exe` pelo GitHub Actions.

## Instalação mais fácil

Baixe `ChatDeusApp.exe` na seção **Releases**, abra e preencha as configurações na tela.

### Twitch

1. Informe o nome do seu canal.
2. Cole um token OAuth com permissão para ler o chat.
3. Clique em **Salvar configurações**.

O ChatDeusApp não inclui nem envia credenciais para o repositório. Elas ficam no arquivo local do seu perfil do Windows.

### Microsoft Azure TTS

O Azure é opcional. Para usar:

1. crie um recurso de Speech no Microsoft Azure;
2. copie a **chave** e a **região**;
3. cole os dois valores na aba **Conexões**;
4. escolha entre várias vozes `pt-BR` disponíveis no painel;
5. deixe o fallback gTTS ativado para continuar falando se o Azure falhar.

Sem Azure, o fallback gTTS pode funcionar normalmente, desde que o computador tenha acesso à internet.

### OBS

A integração com OBS é opcional. No OBS 28+:

1. habilite o servidor WebSocket;
2. informe host, porta e senha no launcher;
3. opcionalmente configure a fonte de áudio e um filtro para cada jogador;
4. adicione uma **Fonte de Navegador** apontando para o endereço `/overlay` mostrado pelo ChatDeusApp.

Se o OBS não estiver aberto, o ChatDeusApp não fecha nem trava.

## Uso

Espectadores entram em uma fila digitando `!jogador1`, `!jogador2` ou `!jogador3`. No painel você pode sortear alguém da fila ou escolher um usuário manualmente. Mensagens dos jogadores escolhidos aparecem no painel/overlay e, com TTS ativo, são faladas.

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
