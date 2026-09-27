"""gametagger-play: let Claude play an Android game on an emulator and record it.

    gametagger-play com.studio.game --check                  # free: is everything set up?
    gametagger-play com.studio.game --budget-usd 0.75         # play, record, write a dossier

The result folder holds a dossier that ``gametagger-genome`` tags:

    gametagger-genome gametagger-play/com.studio.game/<time>/dossier.json --google-play \\
        com.studio.game --live --budget-usd 0.25
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from gametagger.comparison.budget import PRICES, Ledger, Meter, MeteredAnthropic, price_key
from gametagger.config import anthropic_api_key
from gametagger.play.agent import PlayAgent
from gametagger.play.device import AdbDevice, AdbError, valid_package
from gametagger.play.session import PlayConfig, PlaySession

DEFAULT_MODEL = "claude-sonnet-5"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gametagger-play",
        description="Let Claude play an Android game on an emulator, record the screen, and "
        "write a dossier for tagging. Nothing is bought: purchase screens are closed.",
    )
    p.add_argument("package", help="Google Play package name, e.g. com.king.candycrushsaga")
    p.add_argument("--title", help="Game title, for labels")
    p.add_argument("--check", action="store_true", help="Only check the setup; costs nothing")
    p.add_argument("--minutes", type=float, default=12.0, help="Session length (1-14, default 12)")
    p.add_argument(
        "--first-session-minutes",
        type=float,
        default=5.0,
        help="Minutes of ordinary play before exploring shops and menus (default 5)",
    )
    p.add_argument("--max-steps", type=int, default=200, help="Most actions to take")
    p.add_argument("--model", default=os.environ.get("PLAYER_MODEL", DEFAULT_MODEL))
    p.add_argument(
        "--budget-usd",
        type=float,
        help="Required for a real session: hard cap on total spend in the ledger",
    )
    p.add_argument("--ledger", type=Path, default=Path("benchmark-runs") / "ledger.jsonl")
    p.add_argument("--out", type=Path, default=Path("gametagger-play"))
    p.add_argument("--serial", help="Which device, when several are connected")
    p.add_argument("--no-record", action="store_true", help="Keep screenshots, skip the video")
    p.add_argument("--settle-seconds", type=float, default=1.5, help="Wait after each action")
    return p


def check(device: AdbDevice, package: str) -> bool:
    """Print what is ready and what is missing, in plain words. Returns True when ready."""
    ok = True
    info = device.info()
    model = info["model"] or "unknown"
    print(f"Device: {model} (Android {info['android_version']}), {info['serial']}")
    try:
        device.screenshot()
        print("Screenshot: works.")
    except AdbError as exc:
        ok = False
        print(f"Screenshot: FAILED ({exc}).")
    if shutil.which("ffmpeg"):
        print("ffmpeg: installed.")
    else:
        ok = False
        print("ffmpeg: MISSING. Install it with: brew install ffmpeg")
    if device.is_installed(package):
        print(f"Game {package}: installed.")
    else:
        ok = False
        device.open_store_page(package)
        print(
            f"Game {package}: NOT installed. The Play Store page is now open on the emulator: "
            "tap Install, wait for it to finish, then run this again."
        )
    if anthropic_api_key():
        print("Claude key: found.")
    else:
        ok = False
        print("Claude key: MISSING. Put ANTHROPIC_API_KEY in your keys file.")
    print("Ready to play." if ok else "Not ready yet; fix the items above.")
    return ok


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        package = valid_package(args.package)
        config = PlayConfig(
            package=package,
            title=args.title,
            minutes=args.minutes,
            first_session_minutes=args.first_session_minutes,
            max_steps=args.max_steps,
            settle_seconds=args.settle_seconds,
            record=not args.no_record,
        )
    except ValueError as exc:
        parser.error(str(exc))
    try:
        device = AdbDevice(args.serial)
    except AdbError as exc:
        parser.exit(2, f"{exc}\n")

    if args.check:
        parser.exit(0 if check(device, package) else 1)
    if args.budget_usd is None:
        parser.error("A real session calls Claude and costs money: pass --budget-usd (e.g. 0.75)")
    if price_key(args.model) not in PRICES or price_key(args.model) == "jev":
        parser.error(f"No list price is known for {args.model}; the budget cap needs one")
    key = anthropic_api_key()
    if not key:
        parser.error("Set ANTHROPIC_API_KEY (or GAMETAGGER_ANTHROPIC_API_KEY)")
    if not device.is_installed(package):
        device.open_store_page(package)
        parser.exit(2, f"{package} is not installed. Install it from the Play Store page now open "
                       "on the emulator, then run again.\n")  # fmt: skip
    if not args.no_record and not shutil.which("ffmpeg"):
        parser.error("ffmpeg is needed to save the recording (brew install ffmpeg)")

    from anthropic import Anthropic

    try:
        ledger = Ledger(args.ledger, args.budget_usd)
    except ValueError as exc:
        parser.error(str(exc))
    if ledger.spent >= ledger.cap:
        parser.exit(2, f"The ledger has already spent ${ledger.spent:.2f} of ${ledger.cap:.2f}.\n")
    meter = Meter(ledger, "android-play", f"android:{package}", [])
    client = MeteredAnthropic(Anthropic(api_key=key, timeout=60, max_retries=1), meter)
    agent = PlayAgent(
        client, model=args.model, workspace_id=os.environ.get("ANTHROPIC_WORKSPACE_ID")
    )
    print(
        f"Playing {package} for up to {config.minutes:g} minutes with {args.model}. "
        f"Ledger: ${ledger.spent:.2f} spent of ${ledger.cap:.2f}. Press Ctrl+C to stop early.",
        file=sys.stderr,
    )
    session = PlaySession(device, agent, config, args.out, meter=meter)
    result = session.run()
    print(f"Stopped because: {result.stop_reason.replace('_', ' ')}.")
    print(f"Steps: {len(result.steps)}. Cost: ${result.cost_usd:.4f}.")
    print(f"Goals reached: {', '.join(result.goals_reached) or 'none'}.")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    print(f"Results: {result.directory}")
    if result.dossier_path:
        print(f"Next: gametagger-genome {result.dossier_path} --google-play {package} --live ...")


if __name__ == "__main__":
    main()
