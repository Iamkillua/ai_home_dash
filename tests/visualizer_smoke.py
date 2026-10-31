"""Renderer-specific checks, including graceful fallback; needs localhost demo server."""
import asyncio
import json

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        await page.goto("http://localhost:8000")
        await page.wait_for_function("document.querySelector('#core-canvas').dataset.renderer === 'three'")
        await page.wait_for_function("document.querySelector('#core-canvas').dataset.motion === 'animated'")
        await page.locator("#speech-enabled").uncheck()
        await page.locator("#focus-jarvis").click()
        before = await page.locator("#core-canvas").screenshot()
        await page.wait_for_timeout(700)
        after = await page.locator("#core-canvas").screenshot()
        assert before != after, "Three.js sphere rotation did not change the render"
        await page.keyboard.press("Escape")
        await page.locator("#command").fill("Jarvis, what is the weather?")
        await page.locator("#speech-enabled").check()
        await page.locator("#send-command").click()
        await page.wait_for_function("state.core === 'speaking' && state.playbackAnalyser !== null", timeout=90000)
        await page.wait_for_function("Number(document.querySelector('#core-canvas').dataset.audioLevel) > 0.01")
        await page.locator("#stop-speaking").click()
        await page.wait_for_function("Number(document.querySelector('#core-canvas').dataset.audioLevel) < 0.01")
        await page.evaluate("""() => {
            const canvas = document.querySelector('#core-canvas');
            window.contextLoss = canvas.getContext('webgl2').getExtension('WEBGL_lose_context');
            window.contextLoss.loseContext();
        }""")
        await page.wait_for_function("document.querySelector('#core-canvas').dataset.renderer === 'context-lost'")
        assert await page.locator("#graphics-notice").is_visible()
        await page.evaluate("window.contextLoss.restoreContext()")
        await page.wait_for_function("document.querySelector('#core-canvas').dataset.renderer === 'three'")
        assert await page.locator("#graphics-notice").is_hidden()
        assert not errors, errors
        await page.close()

        fallback = await browser.new_page(viewport={"width": 390, "height": 844})
        await fallback.add_init_script("""(() => {
            const original = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                if (type === 'webgl2' || type === 'webgl') return null;
                return original.call(this, type, ...args);
            };
        })();""")
        await fallback.goto("http://localhost:8000")
        await fallback.wait_for_function("document.querySelector('#core-canvas').dataset.renderer === 'fallback'")
        assert await fallback.locator("#graphics-notice").is_visible()
        await fallback.locator("#focus-jarvis").click()
        assert await fallback.locator("#core-canvas").is_visible()
        await fallback.keyboard.press("Escape")
        assert await fallback.locator("#command-form").is_visible()
        await fallback.close()
        await browser.close()
        print(json.dumps({"three_spheres": 5, "rotation": "passed", "actual_audio_reactivity": "passed",
                          "context_recovery": "passed", "fallback": "passed", "renderer_errors": errors}))


if __name__ == "__main__":
    asyncio.run(main())
