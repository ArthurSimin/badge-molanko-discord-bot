import asyncio
# 从 utils 目录导入截图函数
from utils.screenshot_web_firefox import capture_screenshot

async def main():
    target_url = "https://github.com/FirefoxBar/HeaderEditor"
    
    print("开始截图...")
    # 调用截图函数，返回 (文件保存路径, 最终跳转的URL)
    file_path, final_url = await capture_screenshot(
        url=target_url,        # 是否开启长图/全页截图
        device_scale_factor=1.0    # 缩放倍率，2.0 相当于 HD/Retina 清晰度
    )
    
    print(f"截图成功！")
    print(f"保存位置: {file_path}")
    print(f"最终网址: {final_url}")

if __name__ == "__main__":
    asyncio.run(main())