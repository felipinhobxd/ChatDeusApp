# ChatDeusApp 🇧🇷

Aplicativo Windows para transformar pessoas do chat da Twitch em personagens com TTS e overlay animado no OBS. Baseado no conceito do [DougDougGithub/ChatGodApp](https://github.com/DougDougGithub/ChatGodApp), mantendo a licença MIT e os avisos do projeto original.

## v1.3.0 — OBS fácil + TTS grátis

- escolha **1, 2 ou 3 jogadores**;
- **Microsoft Edge TTS** como voz padrão: vozes neurais pt-BR, sem chave e sem créditos;
- emoções gratuitas por prosódia: `(bravo)`, `(alegre)`, `(animado)`, `(triste)`, `(gritando)`, `(assustado)`, `(sussurro)` etc.;
- gTTS continua como fallback gratuito;
- Azure virou totalmente opcional;
- **áudio direto pela Fonte de Navegador do OBS**: o TTS aparece no Mixer do OBS;
- se o OBS estiver fechado, o app pode tocar automaticamente nos alto-falantes do PC;
- OBS WebSocket continua disponível apenas para filtros/efeitos avançados e não é necessário para áudio/personagens;
- login Twitch automático por Device Code Flow continua sem Client Secret;
- personagens PNG/JPG/WebP/GIF continuam animados e sincronizados com a fala.

## Twitch

Clique em **Entrar com Twitch**. O navegador abre, você autoriza e o ChatDeusApp detecta a conta/canal automaticamente. O modo manual antigo fica disponível apenas para compatibilidade.

## Voz sem créditos

O modo padrão é `edge` (Microsoft Edge TTS): não pede API key, assinatura Azure ou créditos no ChatDeusApp. Ele precisa de internet e depende do serviço online da Microsoft. O ChatDeusApp aplica velocidade, tom e volume diferentes para cada emoção.

O modo `gtts` também é gratuito, porém mais simples. `azure` existe só para quem já possui uma chave.

## OBS — configuração recomendada

1. Abra o ChatDeusApp e deixe **Saída de áudio = browser**.
2. Clique em **Iniciar ChatDeusApp**.
3. Na aba **OBS Fácil**, copie a URL do overlay.
4. No OBS: **Fontes → + → Navegador**.
5. Cole a URL.
6. Marque **Controlar áudio via OBS / Control Audio via OBS**.
7. O ChatDeusApp passa a aparecer no Mixer do OBS; ajuste volume/filtros ali normalmente.
8. Use **Testar áudio no OBS** para confirmar.

Não precisa configurar OBS WebSocket para isso.

## Jogadores

Na aba **Aplicativo**, defina `Jogadores ativos` como 1, 2 ou 3. Slots desativados desaparecem do painel e do overlay, e os respectivos comandos deixam de entrar em filas.

Por padrão:

- `!jogador1` / `!player1`
- `!jogador2` / `!player2`
- `!jogador3` / `!player3`

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
