"""Share the extension's local NLP implementation with the inference webpage."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    assets = ROOT / "public/assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "extension/nlp.js", assets / "nlp.js")
    shutil.copyfile(ROOT / "extension/safety.js", assets / "safety.js")
    for name in ("index.html", "assets/app.js", "assets/styles.css", "favicon.svg"):
        if not (ROOT / "public" / name).is_file():
            raise RuntimeError(f"Missing playground asset: {name}")
    print("Playground assets prepared; extension and webpage use the same local NLP.")


if __name__ == "__main__":
    main()
