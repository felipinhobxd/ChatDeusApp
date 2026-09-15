from __future__ import annotations
from pathlib import Path
import sys
from flask import Flask,Response,jsonify,render_template,request,send_file,stream_with_context
from .tts import PT_BR_VOICES,VOICE_STYLES

def _resource_root():
    if getattr(sys,"frozen",False) and hasattr(sys,"_MEIPASS"):return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent

def create_app(runtime):
    root=_resource_root();app=Flask(__name__,template_folder=str(root/"templates"),static_folder=str(root/"static"))
    @app.get("/")
    def panel():return render_template("index.html",voices=PT_BR_VOICES,styles=VOICE_STYLES,overlay_url=f"{runtime.base_url}/overlay")
    @app.get("/overlay")
    def overlay():return render_template("overlay.html")
    @app.get("/character/<int:player>")
    def character(player):
        path=runtime.character_file(player)
        return send_file(path,conditional=True,max_age=0) if path else ("",404)
    @app.get("/api/state")
    def api_state():
        data=runtime.state.snapshot();data["twitch"]={"configured":runtime.twitch.configured,"ready":runtime.twitch.ready.is_set(),"error":runtime.twitch.error};data["azure"]={"configured":runtime.tts.azure_ready};data["obs"]={"enabled":runtime.config.obs_enabled};data["characters"]={str(n):runtime.character_public(n) for n in (1,2,3)};data["version"]=runtime.wait_for_change(-1,timeout=0);return jsonify(data)
    @app.get("/api/events")
    def api_events():
        @stream_with_context
        def generate():
            version=-1
            while True:
                current=runtime.wait_for_change(version,timeout=15.0)
                if current!=version:version=current;yield f"data: {version}\n\n"
                else:yield ": keepalive\n\n"
        response=Response(generate(),mimetype="text/event-stream");response.headers["Cache-Control"]="no-cache";response.headers["X-Accel-Buffering"]="no";return response
    @app.post("/api/player/<int:player>/choose")
    def choose(player):
        payload=request.get_json(silent=True) or {};ok=runtime.state.choose(player,str(payload.get("user","")));return jsonify({"ok":ok}),200 if ok else 400
    @app.post("/api/player/<int:player>/random")
    def pick_random(player):
        user=runtime.state.pick_random(player);return jsonify({"ok":bool(user),"user":user}),200 if user else 409
    @app.post("/api/player/<int:player>/tts")
    def toggle_tts(player):
        payload=request.get_json(silent=True) or {};ok=runtime.state.set_tts(player,bool(payload.get("enabled")));return jsonify({"ok":ok}),200 if ok else 400
    @app.post("/api/player/<int:player>/voice")
    def set_voice(player):
        payload=request.get_json(silent=True) or {};ok=runtime.state.set_voice(player,str(payload.get("voice","")));return jsonify({"ok":ok}),200 if ok else 400
    @app.post("/api/player/<int:player>/style")
    def set_style(player):
        payload=request.get_json(silent=True) or {};ok=runtime.state.set_style(player,str(payload.get("style","")));return jsonify({"ok":ok}),200 if ok else 400
    @app.get("/health")
    def health():return jsonify({"ok":True,"app":"ChatDeusApp"})
    return app
