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
        text = (text or "").strip()
        low = text.lower()

        if any(
            x in low
            for x in [
                "sold out",
                "在庫切れ",
                "入荷待ち",
                "再入荷待ち",
            ]
        ):
            return "out_of_stock"

        if any(
            x in low
            for x in [
                "coming soon",
                "発売前",
            ]
        ):
            return "coming_soon"

        if any(
            x in low
            for x in [
                "pre order",
                "preorder",
                "予約",
            ]
        ):
            return "preorder"

        if any(
            x in low
            for x in [
                "残りわずか",
                "在庫あり",
                "add to cart",
                "カートに入れる",
            ]
        ):
            return "in_stock"

        return "unknown"

    def get_product_links(self, soup, base_url):
        """
        从当前商品列表页提取商品详情链接。
        """

        links = set()

        selectors = [
            "a[href*='products/detail']",
            "a[href*='/products/']",
        ]

        for selector in selectors:
            for a in soup.select(selector):
                href = a.get("href", "")

                if not href:
                    continue

                url = urljoin(base_url, href)

                # 排除商品列表页、分类页等非商品详情页。
                if "list.php" in url:
                    continue

                if url.startswith("https://lifes-203.com/"):
                    links.add(url)

        return links

    def get_next_page(self, soup, current_url):
        """
        查找下一页。

        优先识别：
        ・次へ
        ・次のページ
        ・Next
        ・分页中的下一页按钮
        """

        next_words = [
            "次へ",
            "次のページ",
            "next",
            "next page",
            ">",
            "›",
            "»",
        ]

        for a in soup.select("a[href]"):
            label = a.get_text(" ", strip=True).lower()

            if label in next_words:
                href = a.get("href", "")

                if href:
                    return urljoin(current_url, href)

        return None

    async def collect(self) -> list[Product]:
        products = []

        async with async_playwright() as p:

            browser = await p.chromium.launch(
                headless=True
            )

            page = await browser.new_page()

            # ==================================
            # 第一阶段：
            # 遍历全部商品列表分页
            # ==================================

            all_links = set()

            current_url = self.start_url

            visited_pages = set()

            page_number = 1

            while current_url:

                # 防止分页循环。
                if current_url in visited_pages:
                    break

                visited_pages.add(current_url)

                print(
                    f"[LIFE's #203] "
                    f"正在读取商品列表第 {page_number} 页："
                    f"{current_url}"
                )

                try:

                    await page.goto(
                        current_url,
                        wait_until="networkidle",
                        timeout=90000,
                    )

                    soup = BeautifulSoup(
                        await page.content(),
                        "html.parser",
                    )

                    page_links = self.get_product_links(
                        soup,
                        current_url,
                    )

                    before_count = len(all_links)

                    all_links.update(page_links)

                    new_count = (
                        len(all_links)
                        - before_count
                    )

                    print(
                        f"[LIFE's #203] "
                        f"第 {page_number} 页发现 "
                        f"{len(page_links)} 个商品链接，"
                        f"新增 {new_count} 个，"
                        f"当前去重总数 "
                        f"{len(all_links)} 个"
                    )

                    next_url = self.get_next_page(
                        soup,
                        current_url,
                    )

                    if not next_url:
                        print(
                            "[LIFE's #203] "
                            "没有找到下一页，"
                            "商品列表分页读取完成。"
                        )
                        break

                    current_url = next_url

                    page_number += 1

                except Exception as e:

                    print(
                        f"[LIFE's #203] "
                        f"读取第 {page_number} 页失败："
                        f"{e}"
                    )

                    break

            print(
                f"[LIFE's #203] "
                f"商品列表读取完成，"
                f"去重后共发现 "
                f"{len(all_links)} 个商品链接"
            )

            # ==================================
            # 第二阶段：
            # 逐个进入商品详情页
            # ==================================

            total = len(all_links)

            for index, url in enumerate(
                sorted(all_links),
                start=1,
            ):

                try:

                    print(
                        f"[LIFE's #203] "
                        f"正在读取商品详情 "
                        f"{index}/{total}"
                    )

                    await page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=60000,
                    )

                    psoup = BeautifulSoup(
                        await page.content(),
                        "html.parser",
                    )

                    title_el = psoup.select_one(
                        "h1, "
                        ".product_name, "
                        ".item_name"
                    )

                    name = (
                        title_el.get_text(
                            " ",
                            strip=True,
                        )
                        if title_el
                        else url.rsplit(
                            "/",
                            1,
                        )[-1]
                    )

                    price_el = psoup.select_one(
                        ".price, "
                        ".product_price, "
                        "[class*='price']"
                    )

                    price = (
                        price_el.get_text(
                            " ",
                            strip=True,
                        )
                        if price_el
                        else ""
                    )

                    img_el = psoup.select_one(
                        "main img, "
                        ".product img, "
                        ".item img"
                    )

                    image_url = ""

                    if (
                        img_el
                        and img_el.get("src")
                    ):

                        image_url = urljoin(
                            url,
                            img_el.get("src"),
                        )

                    text = psoup.get_text(
                        " ",
                        strip=True,
                    )

                    variants = []

                    # 先读取下拉菜单中的规格。
                    for opt in psoup.select(
                        "select option"
                    ):

                        label = opt.get_text(
                            " ",
                            strip=True,
                        )

                        if (
                            not label
                            or "選択" in label
                        ):
                            continue

                        status = self.normalize(
                            label
                            + " "
                            + (
                                opt.get(
                                    "disabled"
                                )
                                or ""
                            )
                        )

                        variants.append(
                            Variant(
                                color="",
                                size=label,
                                status=status,
                            )
                        )

                    # 如果暂时没有解析到规格，
                    # 先保存商品整体状态。
                    if not variants:

                        variants = [
                            Variant(
                                status=self.normalize(
                                    text
                                )
                            )
                        ]

                    products.append(
                        Product(
                            site=self.site,
                            url=url,
                            name=name,
                            price=price,
                            image_url=image_url,
                            variants=variants,
                        )
                    )

                except Exception as e:

                    print(
                        f"[LIFE's #203] "
                        f"商品详情读取失败："
                        f"{url}"
                    )

                    print(
                        f"[LIFE's #203] "
                        f"错误：{e}"
                    )

                    continue

            await browser.close()

        print(
            f"[LIFE's #203] "
            f"商品详情读取完成，"
            f"成功保存 "
            f"{len(products)} 个商品"
        )

        return products
