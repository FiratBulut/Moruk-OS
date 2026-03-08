import sys
import os

# Add core to path so we can import from it
sys.path.append(os.path.expanduser('~/moruk-os'))

try:
    from core.web_search import search_duckduckgo, format_search_results, extract_phones, format_phone_results
except ImportError:
    # Fallback if core import fails (should not happen)
    def search_duckduckgo(query, num):
        return [{'title': 'Error', 'link': '', 'snippet': 'Could not import core.web_search'}]
    def format_search_results(results):
        return str(results)
    def extract_phones(text):
        return []
    def format_phone_results(phones):
        return ""

PLUGIN_CORE = True
PLUGIN_NAME = "web_search"
PLUGIN_DESCRIPTION = "Search the web using DuckDuckGo (no API key needed) and extract phone numbers."
PLUGIN_PARAMS = {
    "query": "Search query (optional if extracting phones)",
    "num_results": "Number of results (default: 5)",
    "extract_phones_from": "Text to extract phone numbers from (optional)"
}

def execute(params):
    results = {}
    
    # 1. Web Search
    if "query" in params:
        query = params["query"]
        num = int(params.get("num_results", 5))
        try:
            search_data = search_duckduckgo(query, num)
            results["search_results"] = format_search_results(search_data)
            results["raw_search"] = search_data
        except Exception as e:
            results["search_error"] = str(e)
            
    # 2. Phone Extraction
    if "extract_phones_from" in params:
        text = params["extract_phones_from"]
        try:
            phones = extract_phones(text)
            results["phones"] = format_phone_results(phones)
            results["raw_phones"] = phones
        except Exception as e:
            results["phone_error"] = str(e)
            
    if not results:
        return {"success": False, "result": "No query or text provided."}
        
    # Format output
    output = []
    if "search_results" in results:
        output.append(f"--- Web Search: {params.get('query')} ---")
        output.append(results["search_results"])
    if "phones" in results:
        output.append("--- Phone Extraction ---")
        output.append(results["phones"])
        
    return {"success": True, "result": "\n\n".join(output)}
