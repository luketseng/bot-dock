"""Run one BotDock process with one polling owner per bot."""
import argparse
import uvicorn
from dotenv import load_dotenv
from .app import create_app
from .config import Settings


def main():
    parser = argparse.ArgumentParser(description="BotDock Telegram gateway")
    parser.add_argument("--config", default="bot-dock.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False)
    uvicorn.run(create_app(Settings.load(args.config)), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
