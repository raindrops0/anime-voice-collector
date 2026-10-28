"""Put together the folder the online demo is deployed from.

From a workspace made from the demo episodes (make_episodes.py, then `avoc add` and
`avoc quality`), it writes OUT/ with the Dockerfile and README from deploy/, the workspace packed
as a template (`avoc.app.demo pack`, which also cuts every line's vocals) with the low-quality
hint's starter weights, and a wheel of avoc
built from this checkout. Push that folder to the git repository the host builds from. Run from
the repository root:

    uv run python scripts/demo/make_deploy.py data/online-demo-ws data/online-demo-deploy
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from avoc import quality
from avoc.app.demo import STARTER, pack


def main() -> None:
    workspace, out = Path(sys.argv[1]), Path(sys.argv[2])
    if out.exists():
        raise SystemExit(f"{out} exists already; remove it first")
    shutil.copytree(Path(__file__).parent / "deploy", out)
    pack(workspace, out / "template")
    starter = quality.starter_path()
    if starter is None:
        raise SystemExit("could not download the low-quality hint's starter weights")
    shutil.copy2(starter, out / "template" / STARTER)
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(out / "wheels")], check=True)
    # uv leaves a .gitignore of "*" there, which would keep the wheel out of the git repository.
    (out / "wheels" / ".gitignore").unlink(missing_ok=True)
    print(f"Deploy folder written to {out}")


if __name__ == "__main__":
    main()
