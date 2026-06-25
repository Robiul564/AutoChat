import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings


def main() -> None:
    settings.validate_for_runtime()
    print("Production configuration check passed.")


if __name__ == "__main__":
    main()
