from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys


def smoke_test() -> int:
    from chatdeus.config import AppConfig
    from chatdeus.state import PlayerManager
    from chatdeus.twitch_auth import TWITCH_CLIENT_ID, TWITCH_SCOPES
    from chatdeus.tts import emotion_prosody

    config = AppConfig()
    state = PlayerManager(config)
    assert config.tts_provider == "edge"
    assert config.audio_output == "browser"
    assert 1 <= config.active_players <= 3
    assert state.snapshot()["players"]["1"]["voice"].startswith("pt-BR-")
    assert emotion_prosody("angry", 10)[0].endswith("%")
    assert TWITCH_CLIENT_ID and "user:read:chat" in TWITCH_SCOPES

    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    assert (root / "templates" / "index.html").exists()
    assert (root / "templates" / "overlay.html").exists()
    assert (root / "static" / "app.css").exists()
    assert (root / "static" / "overlay.js").exists()
    print("ChatDeusApp smoke test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ChatDeusApp")
    parser.add_argument("--smoke-test", action="store_true", help="Valida o executável e encerra.")
    args = parser.parse_args()
    if args.smoke_test:
        return smoke_test()
    logging.basicConfig(level=logging.INFO)
    from chatdeus.desktop import run_desktop
    run_desktop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
