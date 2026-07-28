from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from app.models import Product, Variant
from .base import BaseMonitor

class EtreMonitor(BaseMonitor):
    site = "ETRÉ TOKYO"
    start_url = "https://etretokyo.jp/shop/c/c10/"

    def normalize(self, text: str) -> str:
        t = (text or "").strip().lower()
        if any(x in t for x in ["sold out", "在庫切れ", "入荷待ち", "再入荷待ち"]):
            return "out_of_stock"
        if any(x in t for x in ["残りわずか", "カートに入れる", "add to cart"]):
            return "in_stock"
        if any(x in t for x in ["予約", "pre order", "preorder"]):
            return "preorder"
        if any(x in t for x in ["発売前", "coming soon"]):
            return "coming_soon"
        return "unknown"

    async def collect(self) -> list[Product]:
        products = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(self.start_url, wait_until="networkidle", timeout=90000)
            soup = BeautifulSoup(await page.content(), "html.parser")

            seen, links = set(), []
            for a in soup.select("a[href*='/shop/g/g'], a[href*='/shop/goods/']"):
                href = urljoin(self.start_url, a.get("href", ""))
                if href and href not in seen:
                    seen.add(href); links.append(href)

            for url in links:
                try:
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                    psoup = BeautifulSoup(await page.content(), "html.parser")
                    title_el = psoup.select_one("h1, .goods_name, .item_name")
                    name = title_el.get_text(" ", strip=True) if title_el else url.rsplit("/",1)[-1]
                    price_el = psoup.select_one(".price, [class*='price']")
                    price = price_el.get_text(" ", strip=True) if price_el else ""
                    img_el = psoup.select_one("main img, .goods img, .item img")
                    image_url = urljoin(url, img_el.get("src")) if img_el and img_el.get("src") else ""
                    text = psoup.get_text(" ", strip=True)

                    variants = []
                    # 常见的下拉/按钮型规格。实际页面需根据首次日志微调。
                    for el in psoup.select("select option, button, label"):
                        label = el.get_text(" ", strip=True)
                        if not label or len(label) > 80: continue
                        status = self.normalize(label + " " + " ".join(el.get("class", [])))
                        if status != "unknown":
                            variants.append(Variant(size=label, status=status))
                    if not variants:
                        variants = [Variant(status=self.normalize(text))]
                    products.append(Product(self.site, url, name, price, image_url, variants))
                except Exception:
                    continue
            await browser.close()
        return products
