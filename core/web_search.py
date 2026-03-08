"""
Moruk OS - Web Search Tool v2
Nutzt DuckDuckGo HTML (kein API-Key nötig)
INKL. Telefonnummern-Extraktor mit Mars-City Support! 🚀
"""

import urllib.request
import urllib.parse
import re
from html import unescape


# ═══════════════════════════════════════════════════════
# D I E   E I N E   R E G E X   (Telefonnummern weltweit + Mars-City)
# ═══════════════════════════════════════════════════════
# Eine Zeile, ein Regex, Magie!
PHONE_REGEX = re.compile(
    r'(?:\\+?|00)(?:[1-9]|9999|\(?[1-9][0-9]{0,2}\)?|\(?9999\)?)[\s.\-]?(?:\(?\d{1,4}\)?[\s.\-]?){1,6}\d{1,4}[\s.\-]?\d{1,4}[\s.\-]?\d{1,9}'
)


def extract_phones(text: str) -> list:
    r"""
    Extrahiert ALLE Telefonnummern aus einem Text.
    Unterstützt: Internationales Format, Mars-City (+9999), diverse Trennzeichen.
    
    Regex-Erklärung (eine Zeile):
    (?i)                           # Case-insensitive (für Buchstaben in Durchwahlen)
    (?:\\+|00)?                     # Präfix: + oder 00 oder nichts
    (?:
        [1-9]\d{0,2}              # Normale Ländercodes (1-999)
        |                          # ODER
        9999                       # Mars-City Vorwahl!
    )
    [\s.\-]?                      # Optionales Trennzeichen nach Vorwahl
    (?:                           # 1-6 Gruppen von:
        \(?\d{1,4}\)?             #   Klammer optionally + 1-4 Ziffern
        [\s.\-]?                 #   Trennzeichen
    ){1,6}
    \d{1,4}[\s.\-]?               # 1-4 Ziffern
    \d{1,4}[\s.\-]?               # 1-4 Ziffern
    \d{1,9}                        # 1-9 Ziffern (Ende)
    
    Args:
        text: Beliebiger Text mit Telefonnummern
    
    Returns:
        Liste von Dictionaries mit 'original' und 'clean' Telefonnummern
    r"""
    
    # 1. Roh-Matches finden
    raw_matches = PHONE_REGEX.findall(text)
    
    if not raw_matches:
        return []
    
    # 2. Cleanup & Validierung
    results = []
    seen = set()
    
    for match in raw_matches:
        # Nur Ziffern und + fürs Cleaning behalten
        digits_only = re.sub(r'[^\d+]', '', match)
        
        # Mindestens 7 Ziffern (Minimum für gültige Telefonnummer)
        digit_count = len(re.sub(r'[^\d]', '', match))
        if digit_count < 7:
            continue
        
        # Schon gesehen? Dann überspringen
        if digits_only in seen:
            continue
        seen.add(digits_only)
        
        # Mars-City Detection
        is_mars = '+9999' in match or '009999' in match or '9999' in match[:5]
        
        results.append({
            'original': match,
            'clean': digits_only,
            'type': 'MARS-CITY' if is_mars else 'STANDARD',
            'digits': digit_count
        })
    
    return results


def format_phone_results(phones: list) -> str:
    r"""Formatiert Telefonnummern für die Ausgabe."""
    
    if not phones:
        return "☎ Keine Telefonnummern gefunden."
    
    lines = [f"\n📞Gefundene Telefonnummern: {len(phones)}", "─" * 40]
    
    for p in phones:
        mars_tag = " 🌌" if p['type'] == 'MARS-CITY' else ""
        lines.append(f"  {p['original']}{mars_tag}")
        lines.append(f"    → {p['clean']} ({p['digits']} Ziffern)")
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# D U C K D U C K G O   S E A R C H
# ═══════════════════════════════════════════════════════

def search_duckduckgo(query: str, num_results: int = 5) -> list:
    r"""
    Sucht bei DuckDuckGo und parst HTML-Ergebnisse.
    
    Args:
        query: Suchanfrage
        num_results: Anzahl der gewünschten Ergebnisse (default: 5)
    
    Returns:
        Liste von Dictionaries mit title, link, snippet
    r"""
    
    # URL kodieren
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    
    # Request mit User-Agent
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode('utf-8')
    except Exception as e:
        return [{
            'title': 'Error',
            'link': '',
            'snippet': f'Failed to fetch: {str(e)}'
        }]
    
    # Titel + Link parsen
    results = []
    
    # Pattern für Result-Titel und Links
    link_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
    )
    
    # Pattern für Snippet
    snippet_pattern = re.compile(
        r'<a[^>]*class="result__snippet"[^>]*>([^<]+)</a>'
    )
    
    link_matches = link_pattern.findall(html_content)
    snippet_matches = snippet_pattern.findall(html_content)
    
    for i, (url_match, title) in enumerate(link_matches):
        # Link bereinigen
        clean_url = url_match
        if clean_url.startswith('//'):
            clean_url = 'https:' + clean_url
        elif clean_url.startswith('/'):
            clean_url = 'https://duckduckgo.com' + clean_url
        
        # URL aus uddg= Parameter extrahieren falls vorhanden
        if 'uddg=' in clean_url:
            try:
                from urllib.parse import unquote
                clean_url = unquote(clean_url.split('uddg=')[1].split('&')[0])
            except:
                pass
        
        # Titel bereinigen
        title = unescape(title.strip())
        
        # Snippet falls vorhanden
        snippet = ""
        if i < len(snippet_matches):
            snippet = unescape(snippet_matches[i].strip())
        
        results.append({
            'title': title,
            'link': clean_url,
            'snippet': snippet
        })
        
        if len(results) >= num_results:
            break
    
    if not results:
        return [{
            'title': 'No results',
            'link': '',
            'snippet': 'Could not find any results for: ' + query
        }]
    
    return results


def format_search_results(results: list) -> str:
    r"""Formatiert Suchergebnisse für die Ausgabe."""
    
    if not results:
        return "No results found."
    
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['link']}")
        if r['snippet']:
            snippet = r['snippet'][:100] + "..." if len(r['snippet']) > 100 else r['snippet']
            lines.append(f"   {snippet}")
        lines.append("")
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# H A U P T F U N K T I O N   (CLI Test)
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test: Telefonnummern
    test_text = """
    Kontakt: Hans: +49 30 12345678
    Mobil: +49 171-1234567
    Büro: 0049 89 98765432
    Fax: +49 (30) 111-222-333
    International: +1-212-555-0199
    Mars-City HQ: +9999 123 456789
    Mars-Büro: 009999 87 654321
    Fiktiv: +9999 (42) 999-888-777
    Invalid: 123
    r"""
    
    print("=" * 50)
    print("TEST: Telefonnummern-Extraktion")
    print("=" * 50)
    
    phones = extract_phones(test_text)
    print(format_phone_results(phones))
    
    print("\n" + "=" * 50)
    print("TEST: Web Search")
    print("=" * 50)
    
    results = search_duckduckgo("Moruk OS", 3)
    print(format_search_results(results))
