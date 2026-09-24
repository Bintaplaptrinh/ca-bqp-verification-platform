from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.robotparser
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
import fitz
from tenacity import retry, stop_after_attempt, wait_exponential


USER_AGENT = "CA-BQP-Public-Registry-Research/2.0"


def _allowed_host(host: str, suffixes: list[str]) -> bool:
    host = (host or "").lower()
    return any(host == s.lower() or host.endswith("." + s.lower()) for s in suffixes)


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def _is_document_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


class RobotsCache:
    def __init__(self, client: httpx.Client):
        self.client = client
        self.cache = {}

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.cache:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = origin + "/robots.txt"
            try:
                r = self.client.get(robots_url, timeout=10)
                rp.set_url(robots_url)
                rp.parse(r.text.splitlines() if r.status_code < 400 else [])
            except Exception:
                rp.parse([])
            self.cache[origin] = rp
        return self.cache[origin].can_fetch(USER_AGENT, url)


def _extract_pdf_text(content: bytes) -> str:
    doc = fitz.open(stream=content, filetype="pdf")
    return "\n".join(page.get_text("text") for page in doc)


def _html_to_text_and_links(html: str, url: str) -> tuple[str, str, list[str]]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    links = []
    for a in soup.find_all("a", href=True):
        target = _normalize_url(urljoin(url, a["href"]))
        if target.startswith(("http://", "https://")):
            links.append(target)
    return title, text, links


def _page_relevant(url: str, text: str, source: dict) -> bool:
    url_l = url.casefold()
    text_l = text.casefold()
    url_keywords = [str(x).casefold() for x in source.get("relevant_url_keywords", [])]
    text_keywords = [str(x).casefold() for x in source.get("relevant_text_keywords", [])]
    if any(k in url_l for k in url_keywords):
        return True
    return any(k in text_l for k in text_keywords)


def _discover_sitemap_urls(client: httpx.Client, seed: str) -> list[str]:
    parsed = urlparse(seed)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    urls = []
    for name in ["/sitemap.xml", "/sitemap_index.xml"]:
        try:
            r = client.get(origin + name, timeout=10)
            if r.status_code < 400 and "<loc>" in r.text:
                urls.extend(re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text, flags=re.I))
        except Exception:
            pass
    return urls


def _load_existing_pages(out_dir: Path) -> list[dict]:
    """Load pages already crawled to a source's raw dir, sorted by file index.

    Lets crawl_source() resume across runs instead of re-fetching and
    overwriting everything from file 000001 each time.
    """
    existing = []
    for f in sorted(out_dir.glob("*.json")):
        try:
            existing.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return existing


def crawl_source(
    source: dict,
    crawler_cfg: dict,
    raw_root: Path,
    resume: bool = True,
) -> list[dict]:
    source_id = source["source_id"]
    out_dir = raw_root / source_id
    out_dir.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )
    robots = RobotsCache(client)

    seeds = list(source.get("seed_urls", []))
    if crawler_cfg.get("discover_sitemaps", True):
        for seed in list(seeds):
            seeds.extend(_discover_sitemap_urls(client, seed))

    pages: list[dict] = _load_existing_pages(out_dir) if resume else []
    seen = {_normalize_url(p["url"]) for p in pages}
    next_index = len(pages) + 1

    max_pages = int(crawler_cfg.get("max_pages_per_source", 4000))
    max_depth = int(crawler_cfg.get("max_depth", 4))
    delay = float(crawler_cfg.get("delay_seconds", 0.35))
    max_pdf_bytes = int(crawler_cfg.get("max_pdf_mb", 30)) * 1024 * 1024

    queue = deque((u, 0) for u in dict.fromkeys(seeds) if _normalize_url(u) not in seen)

    # Resuming: previously-crawled pages already discovered outbound links,
    # but stopping at max_pages last time meant those links were never
    # visited. Re-seed the queue from them so raising max_pages actually
    # lets the crawl go deeper instead of finding an empty queue.
    if resume:
        for p in pages:
            depth = p.get("depth", 0)
            if depth >= max_depth:
                continue
            if not (p.get("relevant") or depth <= 1):
                continue
            for link in p.get("links", []):
                norm = _normalize_url(link)
                if norm in seen:
                    continue
                if not _allowed_host(urlparse(norm).hostname or "", source["allowed_host_suffixes"]):
                    continue
                queue.append((link, depth + 1))

    while queue and len(pages) < max_pages:
        url, depth = queue.popleft()
        url = _normalize_url(url)

        if url in seen:
            continue
        seen.add(url)

        if depth > max_depth:
            continue
        if not _allowed_host(urlparse(url).hostname or "", source["allowed_host_suffixes"]):
            continue
        if crawler_cfg.get("respect_robots_txt", True) and not robots.can_fetch(url):
            continue

        try:
            response = client.get(
                url,
                timeout=float(crawler_cfg.get("timeout_seconds", 20)),
            )
            if response.status_code >= 400:
                continue

            content_type = response.headers.get("content-type", "").lower()
            final_url = str(response.url)
            content = response.content
            sha256 = hashlib.sha256(content).hexdigest()

            if "application/pdf" in content_type or _is_document_url(final_url):
                if len(content) > max_pdf_bytes:
                    continue
                try:
                    text = _extract_pdf_text(content)
                except Exception:
                    continue
                title = Path(urlparse(final_url).path).name
                links = []
                kind = "PDF"
            else:
                try:
                    html = response.text
                except Exception:
                    continue
                title, text, links = _html_to_text_and_links(html, final_url)
                kind = "HTML"

            if not text.strip():
                continue

            relevant = _page_relevant(final_url, text, source)
            # `links` is kept so a later resumed run can re-seed its queue
            # from pages already crawled, without re-fetching them.
            record = {
                "source_id": source_id,
                "organization_type": source["organization_type"],
                "source_role": source["role"],
                "url": url,
                "final_url": final_url,
                "title": title,
                "kind": kind,
                "sha256": sha256,
                "text": text,
                "relevant": relevant,
                "depth": depth,
                "links": links,
            }
            pages.append(record)

            raw_file = out_dir / f"{next_index:06d}.json"
            raw_file.write_text(
                json.dumps(record, ensure_ascii=False),
                encoding="utf-8",
            )
            next_index += 1

            if (
                crawler_cfg.get("follow_same_site_links", True)
                and depth < max_depth
                and (relevant or depth <= 1)
            ):
                for link in links:
                    if _allowed_host(
                        urlparse(link).hostname or "",
                        source["allowed_host_suffixes"],
                    ):
                        queue.append((link, depth + 1))

            time.sleep(delay)

        except Exception:
            continue

    client.close()
    return pages
