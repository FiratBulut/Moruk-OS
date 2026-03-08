"""
Moruk OS - Web Scraper Plugin v2
Extrahiert strukturierte Daten von Webseiten.
"""

PLUGIN_CORE = True
PLUGIN_NAME = "web_scraper"
PLUGIN_DESCRIPTION = "Extrahiert Titel, Links, Texte und Bilder von Webseiten."
PLUGIN_PARAMS = {"url": "URL zum Scrapen", "extract": "what to extract: links|text|images|all"}

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

def execute(params):
    url     = params.get("url", "").strip()
    extract = params.get("extract", "text")

    if not url:
        return {"success": False, "result": "No URL provided"}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        title = soup.find("title")
        title_text = title.text.strip() if title else "(no title)"

        lines = [f"URL:    {url}", f"Status: {resp.status_code}", f"Title:  {title_text}", ""]

        if extract in ("all", "text"):
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)[:3000]
            lines.append("── Text ──")
            lines.append(text)

        if extract in ("all", "links"):
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http"):
                    links.append(href)
                elif href.startswith("/"):
                    links.append(urljoin(url, href))
            links = list(dict.fromkeys(links))[:30]
            lines.append(f"── Links ({len(links)}) ──")
            for lnk in links:
                lines.append(f"  {lnk}")

        if extract in ("all", "images"):
            imgs = []
            for img in soup.find_all("img", src=True):
                src = img["src"]
                if src.startswith("http"):
                    imgs.append(src)
            imgs = list(dict.fromkeys(imgs))[:15]
            lines.append(f"── Images ({len(imgs)}) ──")
            for img in imgs:
                lines.append(f"  {img}")

        return {"success": True, "result": "\n".join(lines)}

    except requests.Timeout:
        return {"success": False, "result": f"Timeout fetching: {url}"}
    except requests.RequestException as e:
        return {"success": False, "result": f"Request failed: {e}"}
    except Exception as e:
        return {"success": False, "result": f"Scraper error: {e}"}
