from __future__ import annotations

from flask import Flask, render_template, send_from_directory
from flask_cors import CORS

from core.api import api, hooks
from core.db import init_db
from core.seed import seed_samples
from core.settings import HOST, PORT, SECRET_KEY
from core.db import SessionLocal


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
        static_url_path="/static",
    )
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["JSON_SORT_KEYS"] = False

    CORS(app, resources={r"/api/*": {"origins": "*"}, r"/webhook/*": {"origins": "*"}})

    init_db()
    db = SessionLocal()
    try:
        seed_samples(db)
    finally:
        db.close()

    app.register_blueprint(api)
    app.register_blueprint(hooks)

    @app.get("/favicon.svg")
    def favicon():
        return send_from_directory(app.static_folder, "img/mark.svg")

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path: str):
        if path.startswith("api/") or path.startswith("webhook/"):
            return {"error": "not found"}, 404
        return render_template("index.html")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
