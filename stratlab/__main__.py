import argparse
import socket
import threading
import time
import webbrowser

import uvicorn

from stratlab.api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="stratlab", description="StratégieLab — terminal quant hors ligne")
    parser.add_argument("--port", type=int, default=0, help="Port local (0 = automatique)")
    parser.add_argument("--browser", action="store_true", help="Ouvrir dans le navigateur plutôt qu'en fenêtre")
    parser.add_argument("--headless", action="store_true", help="Démarrer uniquement le serveur")
    args = parser.parse_args()

    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))

    if args.headless:
        print(f"StratégieLab disponible sur {url}")
        server.run()
        return

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_until_started(server)
    print(f"StratégieLab disponible sur {url}")

    if not args.browser and _open_window(url):
        server.should_exit = True
        return
    webbrowser.open(url)
    try:
        while thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        server.should_exit = True


def _open_window(url: str) -> bool:
    try:
        import webview
    except ImportError:
        return False
    webview.create_window("StratégieLab", url, width=1400, height=900, min_size=(1000, 650))
    webview.start()
    return True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_started(server: uvicorn.Server, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)


if __name__ == "__main__":
    main()
