import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from app.models import Product, Variant
from .base import BaseMonitor

class LifesMonitor(BaseMonitor):
    site = "LIFE's #203"
    start_url = "https://lifes-203.com/products/list.php"

    def normalize(self, text: str) -> str:
        t = (text or "").strip()
        low = t.lower()
        if any(x in low for x in ["sold out", "在庫切れ", "入荷待ち", "再入荷待ち"]):
            return "out_of_stock"
        if any(x in low for x in ["coming soon", "発売前"]):
            return "coming_soon"
        if any(x in low for x in ["pre order", "preorder", "予約"]):
            return "preorder"
        if any(x in low for x in ["残りわずか", "在庫あり", "add to cart", "カートに入れる"]):
            return "in_stock"
        return "unknown"

    async def collect(self) -> list[Product]:
        products = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(self.start_url, wait_until="networkidle", timeout=90000)
            soup = BeautifulSoup(await page.content(), "html.parser")

            # 先从所有商品链接中提取候选；页面结构变化时可在这里调整。
            seen = set()
            links = []
            for a in soup.select("a[href*='products/detail'], a[href*='products/']"):
                href = urljoin(self.start_url, a.get("href", ""))
                if href and href not in seen and "list.php" not in href:
                    seen.add(href); links.append(href)

            for url in links:
                try:
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                    psoup = BeautifulSoup(await page.content(), "html.parser")
                    title_el = psoup.select_one("h1, .product_name, .item_name")
                    name = title_el.get_text(" ", strip=True) if title_el else url.rsplit("/",1)[-1]
                    price_el = psoup.select_one(".price, .product_price, [class*='price']")
                    price = price_el.get_text(" ", strip=True) if price_el else ""
                    img_el = psoup.select_one("main img, .product img, .item img")
                    image_url = urljoin(url, img_el.get("src")) if img_el and img_el.get("src") else ""

                    text = psoup.get_text(" ", strip=True)
                    variants = []
                    # 尝试读取常见的颜色/尺码选项；无法细分时保留商品级状态。
                    for opt in psoup.select("select option"):
                        label = opt.get_text(" ", strip=True)
                        if not label or "選択" in label: continue
                        status = self.normalize(label + " " + (opt.get("disabled") or ""))
                        variants.append(Variant(color="", size=label, status=status))
                    if not variants:
                        variants = [Variant(status=self.normalize(text))]
                    products.append(Product(self.site, url, name, price, image_url, variants))
                except Exception:
                    continue
            await browser.close()
        return products
