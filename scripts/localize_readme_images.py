#!/usr/bin/env python3
"""Download remote README images and rewrite image references to local files."""

from __future__ import annotations

import argparse
import hashlib
import mimetypes
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


HTML_IMG_RE = re.compile(r'(<img\b[^>]*\bsrc=")(https?://[^"]+)(")', re.IGNORECASE)
MD_IMG_RE = re.compile(r"(!\[[^\]]*\]\()(https?://[^)\s]+)(\))")


def safe_name(url: str, content_type: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path).strip("/")
    name = path.replace("/", "-") or parsed.netloc
    name = re.sub(r"[^A-Za-z0-9._+-]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-._") or "image"

    suffix = Path(name).suffix.lower()
    if suffix not in {".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        suffix = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".svg"
        if suffix == ".jpe":
            suffix = ".jpg"
    else:
        name = name[: -len(suffix)]

    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{name[:90]}-{digest}{suffix}"


def download(url: str, output_dir: Path, force: bool) -> Path:
    request = Request(
        url,
        headers={
            "Accept": "image/svg+xml,image/png,image/jpeg,image/gif,image/webp,*/*;q=0.8",
            "User-Agent": "anasemadanas-readme-image-localizer/1.0",
        },
    )
    with urlopen(request, timeout=30) as response:
        content = response.read()
        content_type = response.headers.get("Content-Type", "image/svg+xml")

    filename = safe_name(url, content_type)
    destination = output_dir / filename
    if not destination.exists() or force:
        destination.write_bytes(content)
    return destination


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
        sys.stderr.reconfigure(errors="backslashreplace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", default=Path("README.md"), type=Path)
    parser.add_argument("--output-dir", default=Path("assets/readme/external"), type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    text = args.readme.read_text(encoding="utf-8")
    urls = []
    urls.extend(match.group(2) for match in HTML_IMG_RE.finditer(text))
    urls.extend(match.group(2) for match in MD_IMG_RE.finditer(text))
    urls = sorted(set(urls))

    if not urls:
        print("No remote README images found.")
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)

    replacements: dict[str, str] = {}
    for url in urls:
        destination = download(url, args.output_dir, args.force)
        local = f"./{destination.as_posix()}"
        replacements[url] = local
        print(f"{url} -> {local}")

    updated = text
    for url, local in replacements.items():
        updated = updated.replace(url, local)

    args.readme.write_text(updated, encoding="utf-8", newline="")
    print(f"Updated {args.readme} with {len(replacements)} local image paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
