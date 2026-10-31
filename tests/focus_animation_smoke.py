"""Verify focus expansion, interruption and reduced motion against the demo server."""
import asyncio
import json

from playwright.async_api import async_playwright


async def check(browser, viewport):
    page = await browser.new_page(viewport=viewport)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    await page.goto("http://localhost:8000")
    await page.wait_for_function("document.querySelector('#core-canvas').dataset.renderer === 'three'")
    expected_particles = "11200" if viewport["width"] <= 800 else "20200"
    assert await page.locator("#core-canvas").get_attribute("data-particles") == expected_particles
    await page.locator("#speech-enabled").uncheck()
    button = page.locator("#focus-jarvis")
    await button.focus()
    await page.keyboard.press("Enter")
    assert await page.evaluate("state.focused && state.focusAnimations[0].effect.getTiming().duration === 420")
    animation = await page.evaluate("""() => {
        const animation = state.focusAnimations[0];
        animation.pause();
        animation.currentTime = 0;
        const start = document.querySelector('#reactor').getBoundingClientRect().toJSON();
        animation.currentTime = 210;
        const matrix = new DOMMatrix(getComputedStyle(document.querySelector('#reactor')).transform);
        const middle = document.querySelector('#reactor').getBoundingClientRect().toJSON();
        animation.currentTime = 420;
        const end = document.querySelector('#reactor').getBoundingClientRect().toJSON();
        animation.currentTime = 210;
        return {start, middle, end, scaleX: matrix.a, scaleY: matrix.d};
    }""")
    assert animation["start"]["height"] < animation["middle"]["height"] < animation["end"]["height"]
    assert abs(animation["scaleX"] - animation["scaleY"]) < 0.00001, "Spheres stretched into ellipses"
    await page.evaluate("""() => {
        state.focusAnimations[0].pause();
        state.focusAnimations[0].currentTime = 100;
    }""")
    await page.wait_for_timeout(100)
    canvas_size = await page.locator("#core-canvas").evaluate("""canvas => ({
        actual: canvas.width, expected: Math.floor(canvas.clientWidth * Math.min(devicePixelRatio || 1, innerWidth <= 800 ? 1.25 : 1.5))
    })""")
    assert abs(canvas_size["actual"] - canvas_size["expected"]) <= 1, "Transform changed canvas render resolution"
    await page.evaluate("state.focusAnimations[0].play()")
    await page.wait_for_function("state.focusAnimations.length === 0")
    assert await page.locator(".rail").is_hidden()
    assert await page.locator("#core-message").is_visible()
    await page.keyboard.press("Escape")
    assert await page.evaluate("!state.focused && state.focusAnimations[0].effect.getTiming().duration === 280")
    await page.wait_for_function("state.focusAnimations.length === 0")
    assert await page.locator("#command-form").is_visible()
    await page.evaluate("() => { toggleJarvisFocus(); toggleJarvisFocus(); toggleJarvisFocus(); }")
    await page.wait_for_function("state.focusAnimations.length === 0")
    assert await page.evaluate("state.focused")
    await page.keyboard.press("Escape")
    await page.set_viewport_size({"width": viewport["width"], "height": viewport["height"] - 20})
    await page.wait_for_function("state.focusAnimations.length === 0")
    await page.emulate_media(reduced_motion="reduce")
    await button.click()
    assert await page.evaluate("state.focused && state.focusAnimations.length === 0")
    await page.keyboard.press("Escape")
    assert await page.evaluate("!state.focused && state.focusAnimations.length === 0")
    assert not await page.evaluate("document.documentElement.scrollWidth > innerWidth")
    assert not errors, errors
    await page.close()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for viewport in [{"width": 1440, "height": 1100}, {"width": 390, "height": 844}]:
            await check(browser, viewport)
        await browser.close()
    print(json.dumps({"expansion": "passed", "return": "passed", "interruption": "passed",
                      "keyboard": "passed", "reduced_motion": "passed", "viewports": ["desktop", "mobile"]}))


if __name__ == "__main__":
    asyncio.run(main())
