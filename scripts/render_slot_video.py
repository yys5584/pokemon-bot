"""Playwright로 슬롯 HTML → MP4 녹화."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def render_slot(result_pids="6,6,6", result_type="shiny", output="scripts/slot_test.mp4"):
    from playwright.async_api import async_playwright

    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slot_playwright.html")
    url = f"file:///{html_path}?result={result_pids}&type={result_type}"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 500, "height": 400},
            record_video_dir="scripts/",
            record_video_size={"width": 500, "height": 400},
        )
        page = await context.new_page()
        await page.goto(url)

        # 슬롯 완료 대기
        for _ in range(120):  # max 12초
            done = await page.evaluate("() => window.__slotDone === true")
            if done:
                break
            await asyncio.sleep(0.1)

        await asyncio.sleep(1)  # 결과 여운

        await page.close()
        await context.close()
        await browser.close()

    # 녹화된 비디오 찾기
    import glob
    vids = sorted(glob.glob("scripts/*.webm"), key=os.path.getmtime, reverse=True)
    if vids:
        src = vids[0]
        # webm → mp4 변환 (imageio)
        import imageio
        reader = imageio.get_reader(src)
        writer = imageio.get_writer(output, fps=30, codec="libx264",
                                     output_params=["-pix_fmt", "yuv420p"])
        for frame in reader:
            writer.append_data(frame)
        writer.close()
        reader.close()
        os.remove(src)
        print(f"Done: {output}")
    else:
        print("No video found!")


if __name__ == "__main__":
    result = sys.argv[1] if len(sys.argv) > 1 else "6,6,6"
    rtype = sys.argv[2] if len(sys.argv) > 2 else "shiny"
    asyncio.run(render_slot(result, rtype))
