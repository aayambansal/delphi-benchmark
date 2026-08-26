"""Import vm-*-{details,summary} from a downloaded vm-results.zip into round3/results."""
from __future__ import annotations
import argparse, shutil, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("zip_or_dir")
    args = p.parse_args()
    src = Path(args.zip_or_dir).expanduser()
    dest = ROOT / "results"
    dest.mkdir(exist_ok=True)
    if src.is_file() and src.suffix == ".zip":
        with zipfile.ZipFile(src) as z:
            z.extractall(dest)
    elif src.is_dir():
        for f in src.glob("vm-*"):
            shutil.copy2(f, dest / f.name)
    else:
        raise SystemExit(f"not a zip or dir: {src}")
    print("imported", sorted(dest.glob("vm-*")))
if __name__ == "__main__":
    main()
