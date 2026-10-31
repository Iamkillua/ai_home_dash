"""Run with a demo server on localhost:8000. Optional Playwright dependencies."""
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright


async def check(browser, size, name, output):
    page = await browser.new_page(viewport=size, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    await page.goto("http://localhost:8000")
    await page.get_by_text("6 devices", exact=True).wait_for()
    await page.wait_for_function("document.querySelector('#core-canvas').dataset.renderer === 'three'")
    assert await page.locator("#core-canvas").get_attribute("data-spheres") == "5"
    assert await page.locator("#core-canvas").get_attribute("data-layout") == "concentric"
    assert await page.locator(".core-letter").count() == 0
    await page.wait_for_function("document.querySelector('#core-canvas').dataset.motion === 'reduced'")
    await page.locator("#speech-enabled").uncheck()
    assert await page.locator("#weather-symbol").get_attribute("href") == "#i-cloud-sun"
    if name == "mobile":
        assert await page.locator(".table-hint").is_visible()
        assert await page.locator(".device-list").evaluate("el => el.scrollHeight <= el.clientHeight")
    await page.screenshot(path=str(output / f"jarvis-{name}.png"), full_page=True)
    overflow = await page.evaluate("document.documentElement.scrollWidth > innerWidth")
    assert not overflow, f"{name}: document overflows viewport"
    toggle = page.get_by_role("switch", name="Turn Living room lights off")
    if not await toggle.count():
        await page.get_by_role("switch", name="Turn Living room lights on").click()
        await toggle.wait_for()
    await toggle.click()
    await page.get_by_role("switch", name="Turn Living room lights on").wait_for()
    await page.locator("#command").fill("Jarvis, tell me about my applications")
    await page.locator("#send-command").click()
    await page.locator("#chat-log").get_by_text("Demo inventory:", exact=False).wait_for()
    reply = await page.locator("#chat-log .chat-entry").last.locator("p").inner_text()
    await page.locator("#focus-jarvis").click()
    assert await page.locator("body").evaluate("el => el.classList.contains('jarvis-focus')")
    assert await page.locator(".rail").is_hidden()
    assert await page.locator("#command-form").is_hidden()
    assert await page.locator("#core-message").inner_text() == reply
    assert not await page.evaluate("document.documentElement.scrollWidth > innerWidth")
    await page.screenshot(path=str(output / f"jarvis-focus-{name}.png"), full_page=True)
    await page.keyboard.press("Escape")
    assert await page.locator(".rail").is_visible()
    await page.locator("#focus-jarvis").click()
    await page.locator("#focus-jarvis").click()
    assert await page.locator("#command-form").is_visible()
    config = await page.evaluate("fetch('/api/config').then(response => response.json())")
    if config.get("tts", {}).get("engine") == "piper" and config["tts"]["ready"]:
        await page.evaluate("() => { window.browserSpeechCalls = 0; speechSynthesis.speak = () => { window.browserSpeechCalls++; }; }")
        await page.locator("#speech-enabled").check()
        await page.locator("#command").fill("Jarvis, what is the weather?")
        await page.locator("#send-command").click()
        await page.wait_for_function("state.core === 'speaking' && state.playbackAnalyser !== null", timeout=90000)
        await page.wait_for_function("""() => {
            const samples = new Uint8Array(256);
            state.playbackAnalyser.getByteTimeDomainData(samples);
            return samples.some(value => value !== 128);
        }""")
        assert await page.evaluate("window.browserSpeechCalls") == 0
        await page.wait_for_function("Number(document.querySelector('#core-canvas').dataset.audioLevel) > 0.01")
        await page.locator("#stop-speaking").click()
        assert await page.evaluate("state.playback === null && state.speechSession === null && !state.spoken")
        await page.locator("#speech-enabled").uncheck()
    await page.locator("#app-filter").select_option("stopped")
    assert await page.locator("#app-list tr").count() == 1
    await page.locator("#app-filter").select_option("all")
    await page.locator("#open-connections").click()
    assert await page.locator("#connections").is_visible()
    await page.locator("#close-connections").click()
    await page.locator('[data-view="briefing"]').click()
    await page.locator("#page-title").get_by_text("The world, without the noise.").wait_for()
    await page.locator('[data-view="overview"]').click()
    assert not errors, errors
    await page.get_by_role("switch", name="Turn Living room lights on").click()
    await page.close()
    return {"viewport": name, "overflow": overflow, "browser_errors": errors, "interaction_checks": "passed"}


async def main():
    output = Path(os.environ.get("JARVIS_SCREENSHOTS", "screenshots"))
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # Same demo inventory is shared by all pages: exercise mutations sequentially.
        desktop = await check(browser, {"width": 1440, "height": 1100}, "desktop", output)
        mobile = await check(browser, {"width": 390, "height": 844}, "mobile", output)
        await browser.close()
        print(json.dumps([desktop, mobile]))


if __name__ == "__main__":
    asyncio.run(main())
