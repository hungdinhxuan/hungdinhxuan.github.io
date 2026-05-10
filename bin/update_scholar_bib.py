#!/usr/bin/env python3

"""Append new Google Scholar publications to the LaTeX CV BibTeX file.

Uses SerpApi's Google Scholar Author API instead of direct Google Scholar
scraping, which is frequently blocked in CI.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import yaml


SOCIALS_FILE = Path("_data/socials.yml")
BIB_FILE = Path("cv_latex/own-bib.bib")
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


def load_scholar_user_id() -> str:
    try:
        config = yaml.safe_load(SOCIALS_FILE.read_text()) or {}
    except FileNotFoundError:
        sys.exit(f"Missing {SOCIALS_FILE}; cannot read scholar_userid.")

    scholar_user_id = config.get("scholar_userid")
    if not scholar_user_id:
        sys.exit(f"Missing scholar_userid in {SOCIALS_FILE}.")

    return str(scholar_user_id)


def load_serpapi_key() -> str:
    api_key = os.environ.get("SERPAPI_API_KEY") or os.environ.get("SERPAPI_KEY")
    if not api_key:
        sys.exit("Missing SERPAPI_API_KEY. Add it as a GitHub Actions secret.")
    return api_key


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def existing_titles(bib_text: str) -> set[str]:
    titles: set[str] = set()
    for match in re.finditer(r"\btitle\s*=\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\"[^\"]+\")", bib_text, re.I):
        raw_title = match.group(1).strip("{}\" ")
        titles.add(normalize_title(raw_title))
    return titles


def existing_keys(bib_text: str) -> set[str]:
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", bib_text))


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
    }
    return "".join(replacements.get(char, char) for char in value)


def make_key(title: str, year: str, used_keys: set[str]) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower())
    base = "".join(words[:4]) or "scholarpub"
    if year:
        base = f"{base}{year}"

    key = base
    suffix = 2
    while key in used_keys:
        key = f"{base}_{suffix}"
        suffix += 1
    used_keys.add(key)
    return key


def make_minimal_bibtex(article: dict, used_keys: set[str]) -> str:
    title = str(article.get("title", "Untitled"))
    year = str(article.get("year", ""))
    venue = str(article.get("publication", ""))
    authors = str(article.get("authors", ""))
    link = str(article.get("link", ""))
    key = make_key(title, year, used_keys)

    lines = [f"@inproceedings{{{key},"]
    if authors:
        lines.append(f"  author = {{{latex_escape(authors)}}},")
    lines.append(f"  title = {{{latex_escape(title)}}},")
    if venue:
        lines.append(f"  booktitle = {{{latex_escape(venue)}}},")
    if year:
        lines.append(f"  year = {{{latex_escape(year)}}},")
    if link:
        lines.append(f"  url = {{{latex_escape(link)}}},")
    lines.append("}")
    return "\n".join(lines)


def serpapi_get(params: dict[str, str]) -> dict:
    query = urlencode(params)
    try:
        with urlopen(f"{SERPAPI_ENDPOINT}?{query}", timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        sys.exit(f"SerpApi request failed with HTTP {exc.code}: {exc.reason}")
    except URLError as exc:
        sys.exit(f"SerpApi request failed: {exc.reason}")

    if data.get("error"):
        sys.exit(f"SerpApi error: {data['error']}")
    if data.get("search_metadata", {}).get("status") == "Error":
        sys.exit("SerpApi search failed.")

    return data


def scholar_publications(scholar_user_id: str, api_key: str) -> Iterable[dict]:
    data = serpapi_get(
        {
            "engine": "google_scholar_author",
            "author_id": scholar_user_id,
            "hl": "en",
            "sort": "pubdate",
            "num": "100",
            "api_key": api_key,
        }
    )
    return data.get("articles", [])


def main() -> int:
    scholar_user_id = load_scholar_user_id()
    api_key = load_serpapi_key()
    current_bib = BIB_FILE.read_text() if BIB_FILE.exists() else ""
    known_titles = existing_titles(current_bib)
    used_keys = existing_keys(current_bib)
    new_entries: list[str] = []

    print(f"Fetching Google Scholar publications for {scholar_user_id} via SerpApi")
    for article in scholar_publications(scholar_user_id, api_key):
        title = str(article.get("title", "")).strip()
        if not title:
            continue

        normalized = normalize_title(title)
        if normalized in known_titles:
            print(f"Already present: {title}")
            continue

        print(f"Adding new publication: {title}")
        new_entries.append(make_minimal_bibtex(article, used_keys))
        known_titles.add(normalized)

    if not new_entries:
        print("No new publications found.")
        return 0

    separator = "\n\n" if current_bib.strip() else ""
    BIB_FILE.write_text(current_bib.rstrip() + separator + "\n\n".join(new_entries) + "\n")
    print(f"Appended {len(new_entries)} publication(s) to {BIB_FILE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
