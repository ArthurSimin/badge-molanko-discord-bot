import asyncio
from lanlan3292_python_screenshot_web.firefox import capture_screenshot

async def main():
    target_url = "https://example.com"
    print("...")
    file_path, final_url = await capture_screenshot(
        url=target_url,
        device_scale_factor=1.0
    )
    
    print(f"done！")
    print(f"file: {file_path}")
    print(f"final: {final_url}")

if __name__ == "__main__":
    asyncio.run(main())