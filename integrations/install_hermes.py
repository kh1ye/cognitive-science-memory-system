"""Install the directory provider into an explicitly selected Hermes profile."""
import argparse
import json
import shutil
from pathlib import Path


def install(home, user_id):
    home = Path(home).expanduser().resolve()
    if not home.is_dir():
        raise ValueError("Hermes profile must already exist. Pass its active HERMES_HOME with --home.")
    source = Path(__file__).parent / "hermes" / "cognitive-memory"
    target = home / "plugins" / "cognitive-memory"
    files = [path for path in source.iterdir() if path.is_file()]
    for path in files:
        destination = target / path.name
        if destination.exists() and destination.read_bytes() != path.read_bytes():
            raise ValueError(f"Existing provider differs; back it up before replacing: {destination}")
    target.mkdir(parents=True, exist_ok=True)
    for path in files:
        shutil.copy2(path, target / path.name)
    config = home / "cognitive-memory.json"
    if not config.exists():
        with config.open("x", encoding="utf-8") as stream:
            json.dump({"base_url": "http://127.0.0.1:8765", "user_id": user_id}, stream, indent=2)
    print(f"Installed provider: {target}")
    print("Existing config preserved. Run hermes memory setup, select cognitive-memory, then restart Hermes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", required=True, help="Existing active Hermes profile directory (HERMES_HOME)")
    parser.add_argument("--user-id", default="", help="Blank uses a profile-isolated namespace")
    args = parser.parse_args()
    install(args.home, args.user_id)
