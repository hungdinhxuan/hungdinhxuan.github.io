#!/usr/bin/env python

import os
import sys
import yaml
import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


def load_scholar_user_id() -> str:
    """Load the Google Scholar user ID from the configuration file."""
    config_file = "_data/socials.yml"
    if not os.path.exists(config_file):
        print(
            f"Configuration file {config_file} not found. Please ensure the file exists and contains your Google Scholar user ID."
        )
        sys.exit(1)
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        scholar_user_id = config.get("scholar_userid")
        if not scholar_user_id:
            print(
                "No 'scholar_userid' found in the configuration file. Please add 'scholar_userid' to _data/socials.yml."
            )
            sys.exit(1)
        return scholar_user_id
    except yaml.YAMLError as e:
        print(
            f"Error parsing YAML file {config_file}: {e}. Please check the file for correct YAML syntax."
        )
        sys.exit(1)


SCHOLAR_USER_ID: str = load_scholar_user_id()
OUTPUT_FILE: str = "_data/citations.yml"
SERPAPI_ENDPOINT: str = "https://serpapi.com/search.json"


def load_serpapi_key() -> str:
    api_key = os.environ.get("SERPAPI_API_KEY") or os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("Missing SERPAPI_API_KEY. Add it as a GitHub Actions secret.")
        sys.exit(1)
    return api_key


def serpapi_get(params: dict[str, str]) -> dict:
    query = urlencode(params)
    try:
        with urlopen(f"{SERPAPI_ENDPOINT}?{query}", timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        print(f"SerpApi request failed with HTTP {e.code}: {e.reason}")
        sys.exit(1)
    except URLError as e:
        print(f"SerpApi request failed: {e.reason}")
        sys.exit(1)

    if data.get("error"):
        print(f"SerpApi error: {data['error']}")
        sys.exit(1)
    if data.get("search_metadata", {}).get("status") == "Error":
        print("SerpApi search failed.")
        sys.exit(1)

    return data


def get_scholar_citations() -> None:
    """Fetch and update Google Scholar citation data."""
    print(f"Fetching citations for Google Scholar ID: {SCHOLAR_USER_ID}")
    today = datetime.now().strftime("%Y-%m-%d")

    # Check if the output file was already updated today
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r") as f:
                existing_data = yaml.safe_load(f)
            if (
                existing_data
                and "metadata" in existing_data
                and "last_updated" in existing_data["metadata"]
            ):
                print(f"Last updated on: {existing_data['metadata']['last_updated']}")
                if existing_data["metadata"]["last_updated"] == today:
                    print("Citations data is already up-to-date. Skipping fetch.")
                    return
        except Exception as e:
            print(
                f"Warning: Could not read existing citation data from {OUTPUT_FILE}: {e}. The file may be missing or corrupted."
            )

    citation_data = {"metadata": {"last_updated": today}, "papers": {}}

    author_data = serpapi_get(
        {
            "engine": "google_scholar_author",
            "author_id": SCHOLAR_USER_ID,
            "hl": "en",
            "sort": "pubdate",
            "num": "100",
            "api_key": load_serpapi_key(),
        }
    )

    if not author_data:
        print(
            f"Could not fetch author data for user ID '{SCHOLAR_USER_ID}'. Please verify the Scholar user ID and try again."
        )
        sys.exit(1)

    if "articles" not in author_data:
        print(f"No publications found in author data for user ID '{SCHOLAR_USER_ID}'.")
        sys.exit(1)

    for article in author_data["articles"]:
        try:
            pub_id = article.get("citation_id")
            if not pub_id:
                print(
                    f"Warning: No ID found for publication: {article.get('title', 'Unknown')}. This publication will be skipped."
                )
                continue

            title = article.get("title", "Unknown Title")
            year = article.get("year", "Unknown Year")
            citations = article.get("cited_by", {}).get("value", 0)

            print(f"Found: {title} ({year}) - Citations: {citations}")

            citation_data["papers"][pub_id] = {
                "title": title,
                "year": year,
                "citations": citations,
            }
        except Exception as e:
            print(
                f"Error processing publication '{article.get('title', 'Unknown')}': {e}. This publication will be skipped."
            )

    # Compare new data with existing data
    if existing_data and existing_data.get("papers") == citation_data["papers"]:
        print("No changes in citation data. Skipping file update.")
        return

    try:
        with open(OUTPUT_FILE, "w") as f:
            yaml.dump(citation_data, f, width=1000, sort_keys=True)
        print(f"Citation data saved to {OUTPUT_FILE}")
    except Exception as e:
        print(
            f"Error writing citation data to {OUTPUT_FILE}: {e}. Please check file permissions and disk space."
        )
        sys.exit(1)


if __name__ == "__main__":
    try:
        get_scholar_citations()
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
