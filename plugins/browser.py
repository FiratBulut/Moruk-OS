PLUGIN_CORE = True
PLUGIN_NAME = "browser"
PLUGIN_DESCRIPTION = "Selenium Browser: get(url) -> title + optional screenshot. headless=True/False. chromium-browser."
PLUGIN_PARAMS = ["url", "screenshot", "headless"]

import os
os.environ["DISPLAY"] = ":0"

def execute(params):
    driver = None
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        options = Options()
        headless = params.get("headless", True)
        if headless:
            options.add_argument("--headless=new")
        else:
            options.add_argument("--start-maximized")
            options.add_argument("--window-position=0,0")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--remote-debugging-port=9222")
        options.binary_location = "/usr/bin/chromium-browser"

        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(20)

        url = params.get("url", "https://httpbin.org/ip")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        driver.get(url)
        title = driver.title
        current_url = driver.current_url
        result_text = f"Title: {title}\nURL: {current_url}"

        if params.get("screenshot", False):
            shot_path = os.path.expanduser("~/moruk-os/browser_shot.png")
            driver.save_screenshot(shot_path)
            size = os.path.getsize(shot_path) // 1024
            result_text += f"\nScreenshot: {shot_path} ({size}KB)"

        return {"success": True, "result": result_text}

    except Exception as e:
        return {"success": False, "result": f"Browser error: {e}"}
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
