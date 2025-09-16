import shutil
import subprocess
from pathlib import Path

def detect_engine() -> str:
    """
    Detect container engine using PATH.
    Prefers 'podman', otherwise 'docker'.
    Raises FileNotFoundError if neither exists.
    """
    if shutil.which("podman"):
        return "podman"
    if shutil.which("docker"):
        return "docker"
    raise FileNotFoundError("No container engine found in PATH (podman/docker)")


def load_image(engine: str, tarball: Path) -> None:
    """
    Load an image tarball into the detected container engine.
    Runs: <engine> load -i <tarball>
    Raises CalledProcessError if the engine fails.
    """
    cmd = [engine, "load", "-i", str(tarball)]
    proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    if proc.stdout:
        print(proc.stdout.strip())


def run_in_container(engine: str, image: str, workdir: Path, args: list[str]) -> None:
    """
    Run a command in a throwaway container with the env directory mounted.
    This is enough for early 'make' usage; adjust volumes/net/user later as needed.
    """
    cmd = [
        engine, "run", "--rm",
        "-v", f"{workdir}:{workdir}:Z",  # :Z is SELinux-friendly; ok on non-SELinux too
        "-w", f"{workdir}",
        image, *args
    ]
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)
