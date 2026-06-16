"""
CLI for the multi-agent system.

Usage:
    python cli.py "draft a reply declining the meeting, and plan my afternoon"
    python cli.py                 # interactive text chat (keeps context)
    python cli.py --voice         # voice mode: speak requests, hear replies
"""

from __future__ import annotations

import sys
from typing import List

import voice
from orchestrator import coordinate


def _status(msg: str) -> None:
    # Dim status line so specialist activity is visible but not noisy.
    print(f"\033[90m  {msg}\033[0m", file=sys.stderr)


def _one_shot(request: str) -> None:
    answer = coordinate(request, on_event=_status)
    print("\n" + answer)


def _interactive() -> None:
    print("AJ — your Purvi Technologies assistant (text mode). Type 'exit' to quit.\n")
    history: List[dict] = []
    while True:
        try:
            request = input("\033[1myou >\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if request.lower() in {"exit", "quit", "q"}:
            break
        if not request:
            continue

        answer = coordinate(request, history=history, on_event=_status)
        print(f"\n\033[1massistant >\033[0m {answer}\n")

        history.append({"role": "user", "content": request})
        history.append({"role": "assistant", "content": answer})


def _voice_mode() -> None:
    print("AJ — your Purvi Technologies assistant (voice mode). Press Ctrl+C to quit.")
    print("Speak after the prompt. (Say 'exit' to quit.)\n")
    history: List[dict] = []
    while True:
        try:
            print("\033[1m🎙️  Listening…\033[0m", file=sys.stderr)
            request, err = voice.listen_from_mic()
        except KeyboardInterrupt:
            print()
            break

        if err:
            print(f"\033[90m  {err}\033[0m", file=sys.stderr)
            continue
        if not request:
            continue
        print(f"\033[1myou >\033[0m {request}")
        if request.lower().strip(" .") in {"exit", "quit", "stop"}:
            break

        answer = coordinate(request, history=history, on_event=_status)
        print(f"\n\033[1massistant >\033[0m {answer}\n")
        voice.speak(answer)

        history.append({"role": "user", "content": request})
        history.append({"role": "assistant", "content": answer})


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] in {"--voice", "-v"}:
        _voice_mode()
    elif args:
        _one_shot(" ".join(args))
    else:
        _interactive()


if __name__ == "__main__":
    main()
