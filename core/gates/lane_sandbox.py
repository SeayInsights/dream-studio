"""The container a review lane tests in.

WHY LANES RUN CODE. The bench replaced hardcoded seats because a seat could claim
something was wrong without testing it. A lane is only better if it actually tests: the
operator's rule (2026-09-23) is that review lanes "use docker and do a real test, not just
read code". The first live convening of the nine reviewers showed both halves of why --
the findings worth acting on were the ones a reviewer reproduced by running the code, and
a reviewer that mutated the LIVE tree to prove a test could fail nearly got its residue
committed.

WHAT THIS PROVIDES. One image per reviewed commit, and a way to run a command in it:

  - THE IMAGE IS BUILT FROM THE COMMIT, NOT THE WORKING TREE. `git archive <sha>` is the
    build context, so untracked files, local edits and every `studio.db` stay out, and the
    thing tested is exactly the thing that would be pushed. `Dockerfile.runtime-check`
    already gives an isolated HOME and DREAM_STUDIO_HOME with the dev requirements.
  - A RUN HAS NO NETWORK AND NO HOST STATE. `--network none`, `--rm`, nothing mounted. A
    reviewer can mutate, delete or break anything inside and the next run starts clean.

It decides nothing about a change. It is how a verdict gets a reproduction, and how the
recording door re-runs that reproduction instead of trusting a pasted transcript.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = "Dockerfile.runtime-check"
IMAGE_PREFIX = "ds-review"

#: A reproduction is a test, not a suite run. Ten minutes is generous for one and bounds
#: the door, which re-runs every reproduction a submission carries.
RUN_TIMEOUT_S = 600
BUILD_TIMEOUT_S = 1800

#: What is kept of a run's output. The hash covers all of it; the tail is for a reader.
OUTPUT_TAIL_CHARS = 4000


def docker_available() -> tuple[bool, str]:
    """Whether a container can be run right now, and if not, why.

    The caller REFUSES on False. There is no fallback to reading: a lane that cannot run
    is a lane that has not been answered, and treating "Docker was down" as "nothing was
    found" is the silent-default shape the bench exists to catch.
    """
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except FileNotFoundError:
        return False, "`docker` is not on PATH"
    except subprocess.SubprocessError as exc:
        return False, f"`docker info` did not answer: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, (
            "the Docker engine is not running"
            + (f" ({detail[-1]})" if detail else "")
            + ". Start Docker Desktop and retry."
        )
    return True, f"docker engine {proc.stdout.strip()}"


def resolve_sha(ref: str = "HEAD", *, repo_root: Path = REPO_ROOT) -> str:
    """The full commit a review is about. Raises when the ref does not name one."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{ref!r} does not name a commit: {proc.stderr.strip()}")
    return proc.stdout.strip()


def image_tag(sha: str) -> str:
    return f"{IMAGE_PREFIX}:{sha[:12]}"


def _image_exists(tag: str) -> bool:
    proc = subprocess.run(["docker", "image", "inspect", tag], capture_output=True)
    return proc.returncode == 0


def build_image(sha: str, *, repo_root: Path = REPO_ROOT) -> str:
    """Build (or reuse) the lane image for one commit and return its tag.

    Reused when it exists: the tag is the commit, and a commit does not change.
    """
    tag = image_tag(sha)
    if _image_exists(tag):
        return tag

    archive = subprocess.Popen(
        ["git", "archive", "--format=tar", sha],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
    )
    try:
        build = subprocess.run(
            ["docker", "build", "-q", "-f", DOCKERFILE, "-t", tag, "-"],
            stdin=archive.stdout,
            capture_output=True,
            timeout=BUILD_TIMEOUT_S,
        )
    finally:
        if archive.stdout is not None:
            archive.stdout.close()
        archive.wait()
    if archive.returncode != 0:
        raise RuntimeError(f"`git archive {sha[:12]}` failed (exit {archive.returncode})")
    if build.returncode != 0:
        detail = build.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(f"building {tag} failed: {detail[-1] if detail else 'no error text'}")
    return tag


def run_in_lane(image: str, command: str, *, timeout: int = RUN_TIMEOUT_S) -> dict[str, Any]:
    """Run one shell command in a fresh container from the lane image.

    Returns ``{command, exit_code, timed_out, output_sha256, output_tail}``. A timeout is
    reported as its own state with exit_code None, never as a pass or a fail: a command
    that did not finish has not answered either way.
    """
    try:
        proc = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", image, "sh", "-c", command],
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"") + (exc.stderr or b"")
        text = out.decode("utf-8", "replace")
        return {
            "command": command,
            "exit_code": None,
            "timed_out": True,
            "output_sha256": hashlib.sha256(out).hexdigest(),
            "output_tail": text[-OUTPUT_TAIL_CHARS:],
        }
    out = (proc.stdout or b"") + (proc.stderr or b"")
    return {
        "command": command,
        "exit_code": proc.returncode,
        "timed_out": False,
        "output_sha256": hashlib.sha256(out).hexdigest(),
        "output_tail": out.decode("utf-8", "replace")[-OUTPUT_TAIL_CHARS:],
    }


def verify_reproduction(
    image: str, reproduction: dict[str, Any], *, runner=run_in_lane
) -> tuple[bool, dict[str, Any] | None, str]:
    """Re-run a reviewer's reproduction and say whether it holds.

    Holds when the command, run fresh, exits with the code the reviewer reported. The exit
    code is the claim: a finding says "this command fails", a pass says "this command
    succeeds". Output is recorded, not compared -- timestamps and paths differ run to run,
    and comparing them would refuse honest reproductions for noise.

    Returns ``(holds, run, reason)``.
    """
    command = str(reproduction.get("command", "") or "").strip()
    if not command:
        return False, None, "the reproduction has no command"
    reported = reproduction.get("exit_code")
    if not isinstance(reported, int) or isinstance(reported, bool):
        return False, None, "the reproduction must report the integer exit_code it saw"

    run = runner(image, command)
    if run.get("timed_out"):
        return False, run, f"re-running it timed out after {RUN_TIMEOUT_S}s"
    if run.get("exit_code") != reported:
        return (
            False,
            run,
            (
                f"re-run exited {run.get('exit_code')}, the reviewer reported {reported} --"
                " the reproduction does not reproduce"
            ),
        )
    return True, run, "reproduced"
