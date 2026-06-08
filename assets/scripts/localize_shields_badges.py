#!/usr/bin/env python3
"""Download shields.io badges from README.md and rewrite them to local paths."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen


SHIELDS_RE = re.compile(r"https://img\.shields\.io/[^\s)\"<>]+")


def make_filename(url: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path).strip("/")

    if path.startswith("badge/"):
        name = path.removeprefix("badge/")
    else:
        name = path.replace("/", "-")

    name = re.sub(r"[^A-Za-z0-9._+-]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-._")
    if not name:
        name = "badge"

    if name.lower().endswith((".svg", ".png")):
        name = re.sub(r"\.(svg|png)$", "", name, flags=re.IGNORECASE)

    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{name[:90]}-{digest}.svg"


def download(url: str, destination: Path, force: bool) -> str:
    if destination.exists() and not force:
        return "exists"

    request_url = encode_url(url)
    request = Request(
        request_url,
        headers={
            "Accept": "image/svg+xml,*/*;q=0.8",
            "User-Agent": "anasemadanas-badge-localizer/1.0",
        },
    )

    with urlopen(request, timeout=30) as response:
        content = response.read()
        content_type = response.headers.get("Content-Type", "")

    if b"<svg" not in content[:500].lower() and "svg" not in content_type.lower():
        raise ValueError(f"response does not look like SVG ({content_type or 'unknown content type'})")

    destination.write_bytes(content)
    return "downloaded"


def encode_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe="/%:+"),
            quote(parts.query, safe="=&%:+,.-_"),
            quote(parts.fragment, safe="=&%:+,.-_"),
        )
    )


def read_text_preserve_newline(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8"), newline


def write_text_preserve_newline(path: Path, text: str, newline: str) -> None:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    path.write_text(text, encoding="utf-8", newline="")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
        sys.stderr.reconfigure(errors="backslashreplace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", default="README.md", type=Path, help="README file to update")
    parser.add_argument("--badges-dir", default=Path("assets") / "badges", type=Path, help="directory for downloaded SVG badges")
    parser.add_argument("--dry-run", action="store_true", help="show what would change without writing files")
    parser.add_argument("--force", action="store_true", help="redownload badges even if local files already exist")
    parser.add_argument("--pause", default=0.15, type=float, help="seconds to pause between downloads")
    args = parser.parse_args()

    readme = args.readme
    badges_dir = args.badges_dir

    if not readme.exists():
        print(f"README not found: {readme}", file=sys.stderr)
        return 1

    text, newline = read_text_preserve_newline(readme)
    urls = sorted(set(SHIELDS_RE.findall(text)))

    if not urls:
        print("No shields.io badge URLs found.")
        return 0

    replacements: dict[str, str] = {}
    failures: list[tuple[str, str]] = []

    if not args.dry_run:
        badges_dir.mkdir(parents=True, exist_ok=True)

    for index, url in enumerate(urls, start=1):
        filename = make_filename(url)
        destination = badges_dir / filename
        local_path = f"./{destination.as_posix()}"
        replacements[url] = local_path

        if args.dry_run:
            print(f"would download {url} -> {local_path}")
            continue

        try:
            status = download(url, destination, args.force)
            print(f"{status:10} {url} -> {local_path}")
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            failures.append((url, str(error)))
            print(f"failed     {url}: {error}", file=sys.stderr)

        if index < len(urls) and args.pause > 0:
            time.sleep(args.pause)

    if failures:
        print("\nREADME was not rewritten because some badges failed to download:", file=sys.stderr)
        for url, error in failures:
            print(f"- {url}: {error}", file=sys.stderr)
        return 1

    updated = text
    for url, local_path in replacements.items():
        updated = updated.replace(url, local_path)

    if updated == text:
        print("README already uses local paths for all discovered shields.io badges.")
        return 0

    if args.dry_run:
        print(f"would update {readme} with {len(replacements)} local badge paths")
        return 0

    write_text_preserve_newline(readme, updated, newline)
    print(f"Updated {readme} with {len(replacements)} local badge paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
