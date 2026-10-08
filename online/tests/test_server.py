from pathlib import Path

from online_caption.server import parse_args, resolve_web_file


def test_resolve_web_file_serves_index_and_blocks_escape(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("home", encoding="utf-8")
    (web / "app.js").write_text("js", encoding="utf-8")

    assert resolve_web_file(web, "/").read_text(encoding="utf-8") == "home"
    assert resolve_web_file(web, "/app.js").read_text(encoding="utf-8") == "js"
    assert resolve_web_file(web, "/../.env") is None
    assert resolve_web_file(web, "/missing.js") is None


def test_http_mode_uses_port_9000_by_default():
    args = parse_args(["--http"])
    assert args.http is True
    assert args.port is None
