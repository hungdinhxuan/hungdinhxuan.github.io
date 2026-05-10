#!/usr/bin/env python3

"""Append new Google Scholar publications to the LaTeX CV BibTeX file."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

import yaml
from scholarly import scholarly


SOCIALS_FILE = Path("_data/socials.yml")
BIB_FILE = Path("cv_latex/own-bib.bib")


def load_scholar_user_id() -> str:
    try:
        config = yaml.safe_load(SOCIALS_FILE.read_text()) or {}
    except FileNotFoundError:
        sys.exit(f"Missing {SOCIALS_FILE}; cannot read scholar_userid.")

    scholar_user_id = config.get("scholar_userid")
    if not scholar_user_id:
        sys.exit(f"Missing scholar_userid in {SOCIALS_FILE}.")

    return str(scholar_user_id)


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


def make_minimal_bibtex(pub: dict, used_keys: set[str]) -> str:
    bib = pub.get("bib", {})
    title = str(bib.get("title", "Untitled"))
    year = str(bib.get("pub_year", bib.get("year", "")))
    venue = str(bib.get("venue", bib.get("journal", bib.get("conference", ""))))
    authors = str(bib.get("author", ""))
    key = make_key(title, year, used_keys)

    lines = [f"@inproceedings{{{key},"]
    if authors:
        lines.append(f"  author = {{{latex_escape(authors)}}},")
    lines.append(f"  title = {{{latex_escape(title)}}},")
    if venue:
        lines.append(f"  booktitle = {{{latex_escape(venue)}}},")
    if year:
        lines.append(f"  year = {{{latex_escape(year)}}},")
    lines.append("}")
    return "\n".join(lines)


def scholar_publications(scholar_user_id: str) -> Iterable[dict]:
    scholarly.set_timeout(20)
    scholarly.set_retries(3)
    author = scholarly.search_author_id(scholar_user_id)
    author = scholarly.fill(author, sections=["publications"])
    publications = author.get("publications", [])
    return sorted(
        publications,
        key=lambda pub: int(pub.get("bib", {}).get("pub_year", 0) or 0),
        reverse=True,
    )


def bibtex_for_publication(pub: dict, used_keys: set[str]) -> str:
    try:
        filled_pub = scholarly.fill(pub)
        bibtex = scholarly.bibtex(filled_pub).strip()
        key_match = re.match(r"(@\w+\s*\{\s*)([^,\s]+)", bibtex)
        if key_match:
            key = key_match.group(2)
            if key in used_keys:
                title = filled_pub.get("bib", {}).get("title", key)
                year = str(filled_pub.get("bib", {}).get("pub_year", ""))
                new_key = make_key(title, year, used_keys)
                bibtex = bibtex.replace(key_match.group(0), f"{key_match.group(1)}{new_key}", 1)
            else:
                used_keys.add(key)
        return bibtex
    except Exception as exc:
        print(f"Warning: falling back to minimal BibTeX for {pub.get('bib', {}).get('title', 'unknown')}: {exc}")
        return make_minimal_bibtex(pub, used_keys)


def main() -> int:
    scholar_user_id = load_scholar_user_id()
    current_bib = BIB_FILE.read_text() if BIB_FILE.exists() else ""
    known_titles = existing_titles(current_bib)
    used_keys = existing_keys(current_bib)
    new_entries: list[str] = []

    print(f"Fetching Google Scholar publications for {scholar_user_id}")
    for pub in scholar_publications(scholar_user_id):
        title = str(pub.get("bib", {}).get("title", "")).strip()
        if not title:
            continue

        normalized = normalize_title(title)
        if normalized in known_titles:
            print(f"Already present: {title}")
            continue

        print(f"Adding new publication: {title}")
        new_entries.append(bibtex_for_publication(pub, used_keys))
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
