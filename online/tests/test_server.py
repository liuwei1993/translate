import ssl
import subprocess
from pathlib import Path

from online_caption.server import build_ssl_context, parse_args, resolve_web_file


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
    assert args.host == "0.0.0.0"


def test_host_can_bind_loopback_only():
    args = parse_args(["--http", "--host", "127.0.0.1", "--port", "19000"])
    assert args.host == "127.0.0.1"
    assert args.port == 19000


def test_tls_context_allows_only_tls_1_3(tmp_path):
    key = tmp_path / "key.pem"
    cert = tmp_path / "cert.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-days",
            "1",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=tls13-test",
        ],
        check=True,
        capture_output=True,
    )
    context = build_ssl_context(cert, key)
    assert context.minimum_version == ssl.TLSVersion.TLSv1_3
    assert context.maximum_version == ssl.TLSVersion.TLSv1_3
