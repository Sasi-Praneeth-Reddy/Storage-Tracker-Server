"""
find_export_api.py
Intercepts all network requests made when the Export button is clicked.
This tells us the exact API endpoint and parameters for direct download.
Run: venv\\Scripts\\python find_export_api.py
"""
import asyncio, sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import USAHOMELISTINGS_EMAIL, USAHOMELISTINGS_PASSWORD

OUT = pathlib.Path("debug_screenshots")
OUT.mkdir(exist_ok=True)

CAPTURED = []

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        page = await context.new_page()

        # ── Capture ALL requests + responses ───────────────────────
        def on_request(req):
            if any(x in req.url for x in ["export", "download", "csv", "report", "listings"]):
                CAPTURED.append({
                    "type": "REQUEST",
                    "method": req.method,
                    "url": req.url,
                    "headers": dict(req.headers),
                    "post_data": req.post_data or "",
                })
                print("REQUEST:", req.method, req.url[:120])

        async def on_response(resp):
            if any(x in resp.url for x in ["export", "download", "csv", "report"]):
                print("RESPONSE:", resp.status, resp.url[:120])
                try:
                    headers = dict(resp.headers)
                    ct = headers.get("content-type", "")
                    print("  Content-Type:", ct)
                    if "csv" in ct or "excel" in ct or "octet" in ct:
                        body = await resp.body()
                        path = OUT / "intercepted_export.csv"
                        path.write_bytes(body)
                        print("  SAVED intercepted file:", path, "({:.1f} KB)".format(len(body)/1024))
                except Exception as e:
                    print("  Response read error:", e)

        page.on("request", on_request)
        page.on("response", on_response)

        # ── Login ───────────────────────────────────────────────────
        await page.goto("https://get.usahomelistings.com/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[type="email"]', USAHOMELISTINGS_EMAIL)
        await page.click('button[type="submit"]')
        await page.wait_for_selector('input[type="password"]', timeout=12000)
        await page.fill('input[type="password"]', USAHOMELISTINGS_PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(5000)

        # Capture all cookies for later direct API use
        cookies = await context.cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        (OUT / "session_cookies.txt").write_text(cookie_str, encoding="utf-8")
        print("Session cookies saved ({} cookies)".format(len(cookies)))

        # ── Load listings page ──────────────────────────────────────
        await page.goto("https://get.usahomelistings.com/portal/page/listings_data",
                        wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(4000)

        # Find the listings iframe
        frame = None
        for f in page.frames:
            if "portal.usahomelistings.com/listings" in f.url:
                frame = f
                break

        if not frame:
            print("ERROR: Listings iframe not found")
            await browser.close()
            return

        print("Iframe URL:", frame.url[:100])

        # Also intercept iframe requests
        def iframe_req(req):
            if any(x in req.url for x in ["export", "download", "csv", "api", "report"]):
                print("IFRAME-REQ:", req.method, req.url[:120])
                CAPTURED.append({"type": "IFRAME_REQ", "method": req.method, "url": req.url,
                                  "post_data": req.post_data or ""})

        # ── Select Alexandria County using vue-multiselect properly ──
        print("\nSelecting Alexandria County...")

        # Use the specific vue-multiselect structure:
        # .multiselect__tags -> click to open
        # .multiselect__option -> click to select
        
        # Find the Counties multiselect (second .multiselect__tags element)
        multiselects = await frame.query_selector_all(".multiselect__tags")
        print("Found {} multiselect inputs".format(len(multiselects)))
        
        # States is first, Counties is second, Cities is third, Zip Codes is fourth
        if len(multiselects) >= 2:
            counties_input = multiselects[1]  # Counties is the 2nd multiselect
            await counties_input.click()
            print("Counties multiselect opened")
            await frame.wait_for_timeout(1200)

            # Now find the options
            options = await frame.query_selector_all(".multiselect__option")
            print("Options visible: {}".format(len(options)))
            for opt in options[:10]:
                txt = (await opt.inner_text()).strip()
                print("  Option: {!r}".format(txt))

            # Click Alexandria County specifically
            for opt in options:
                txt = (await opt.inner_text()).strip()
                if "Alexandria" in txt:
                    print("Clicking: {!r}".format(txt))
                    await opt.click()
                    break

            await frame.wait_for_timeout(800)

        # Click Update Results
        update_btn = await frame.query_selector('button:has-text("Update Results")')
        if update_btn:
            await update_btn.click()
            print("Update Results clicked")
            await frame.wait_for_timeout(5000)

        # Read the new count
        count_el = await frame.query_selector_all("*")
        for el in count_el:
            try:
                txt = (await el.inner_text()).strip()
                if "Listings Found" in txt and len(txt) < 40:
                    print("Count after filter:", txt)
                    break
            except Exception:
                pass

        await page.screenshot(path=str(OUT / "after_county_filter.png"))
        print("Screenshot: after_county_filter.png")

        # ── Click Export and capture ALL network activity ───────────
        print("\nClicking Export and watching network...")
        CAPTURED.clear()

        # Attach frame-level request watcher
        frame_requests = []
        async def cap_resp(resp):
            frame_requests.append({"url": resp.url, "status": resp.status,
                                   "ct": resp.headers.get("content-type", "")})
            print("NETWORK:", resp.status, resp.url[:100])
        page.on("response", cap_resp)

        export_btn = await frame.query_selector('button:has-text("Export to see Detailed Report")')
        if export_btn:
            try:
                async with page.expect_download(timeout=60000) as dl_info:
                    await export_btn.click()
                    print("Export clicked, waiting 60s for download...")
                    await page.wait_for_timeout(15000)
                    await page.screenshot(path=str(OUT / "during_export.png"))
                    print("Screenshot: during_export.png")
                dl = await dl_info.value
                fname = dl.suggested_filename or "export.csv"
                save_path = pathlib.Path("data/imports") / fname
                save_path.parent.mkdir(parents=True, exist_ok=True)
                await dl.save_as(str(save_path))
                print("SUCCESS! Downloaded:", fname, "({:.1f} KB)".format(save_path.stat().st_size/1024))
            except Exception as exc:
                print("Download exception:", exc)
                await page.screenshot(path=str(OUT / "export_failed.png"))

        # Save all captured request info
        (OUT / "captured_requests.json").write_text(
            json.dumps(frame_requests[-20:], indent=2), encoding="utf-8"
        )
        print("\nNetwork requests captured:", len(frame_requests))
        print("Last 10 requests:")
        for r in frame_requests[-10:]:
            print(" ", r["status"], r["url"][:100])

        await browser.close()

asyncio.run(main())
