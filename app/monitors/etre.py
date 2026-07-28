from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.models import Product, Variant
from .base import BaseMonitor


class EtreMonitor(BaseMonitor):
    site = "ETRÉ TOKYO"

    # 使用全站搜索结果页，而不是原来的 c10 分类页。
    start_url = (
        "https://etretokyo.jp/shop/goods/search.aspx"
        "?yy_min_releasedt=2010"
        "&mm_min_releasedt=01"
        "&dd_min_releasedt=01"
        "&sort=c4"
        "&search=%E6%A4%9C%E7%B4%A2"
    )

    def normalize(self, text: str) -> str:
        t = (text or "").strip().lower()

        if any(
            x in t
            for x in [
                "sold out",
                "在庫切れ",
                "入荷待ち",
                "再入荷待ち",
            ]
        ):
            return "out_of_stock"

        if any(
            x in t
            for x in [
                "残りわずか",
                "カートに入れる",
                "add to cart",
            ]
        ):
            return "in_stock"

        if any(
            x in t
            for x in [
                "予約",
                "pre order",
                "preorder",
            ]
        ):
            return "preorder"

        if any(
            x in t
            for x in [
                "発売前",
                "coming soon",
            ]
        ):
            return "coming_soon"

        return "unknown"

    def get_product_links(self, soup, base_url):
        """
        从当前搜索结果页提取商品详情链接。
        """

        links = set()

        selectors = [
            "a[href*='/shop/g/g']",
            "a[href*='/shop/goods/']",
        ]

        for selector in selectors:

            for a in soup.select(selector):

                href = a.get("href", "")

                if not href:
                    continue

                url = urljoin(
                    base_url,
                    href,
                )

                # 排除搜索页、分类页等。
                if (
                    "/shop/goods/search.aspx"
                    in url
                ):
                    continue

                # 商品详情页通常为 /shop/g/g商品编号/
                if (
                    "/shop/g/g"
                    in url
                ):
                    links.add(url)

        return links

    def get_next_page(
        self,
        soup,
        current_url,
    ):
        """
        查找下一页。

        优先识别：
        ・次へ
        ・次のページ
        ・Next
        ・分页的 >、›、»
        """

        next_words = {
            "次へ",
            "次のページ",
            "next",
            "next page",
            ">",
            "›",
            "»",
        }

        for a in soup.select(
            "a[href]"
        ):

            label = a.get_text(
                " ",
                strip=True,
            ).lower()

            if label in next_words:

                href = a.get(
                    "href",
                    "",
                )

                if href:

                    return urljoin(
                        current_url,
                        href,
                    )

        return None

    async def collect(
        self,
    ) -> list[Product]:

        products = []

        async with async_playwright() as p:

            browser = (
                await p.chromium.launch(
                    headless=True
                )
            )

            page = (
                await browser.new_page()
            )

            # =================================
            # 第一阶段：
            # 遍历所有搜索结果分页
            # =================================

            all_links = set()

            current_url = (
                self.start_url
            )

            visited_pages = set()

            page_number = 1

            while current_url:

                # 防止网站分页链接循环。
                if (
                    current_url
                    in visited_pages
                ):
                    print(
                        "[ETRÉ TOKYO] "
                        "检测到重复分页，"
                        "停止翻页。"
                    )
                    break

                visited_pages.add(
                    current_url
                )

                print(
                    "[ETRÉ TOKYO] "
                    f"正在读取第 "
                    f"{page_number} 页："
                    f"{current_url}"
                )

                try:

                    await page.goto(
                        current_url,
                        wait_until=(
                            "networkidle"
                        ),
                        timeout=90000,
                    )

                    soup = (
                        BeautifulSoup(
                            await page.content(),
                            "html.parser",
                        )
                    )

                    page_links = (
                        self.get_product_links(
                            soup,
                            current_url,
                        )
                    )

                    before_count = (
                        len(all_links)
                    )

                    all_links.update(
                        page_links
                    )

                    new_count = (
                        len(all_links)
                        - before_count
                    )

                    print(
                        "[ETRÉ TOKYO] "
                        f"第 {page_number} 页"
                        f"发现 "
                        f"{len(page_links)} "
                        f"个商品链接，"
                        f"新增 "
                        f"{new_count} "
                        f"个，当前去重总数 "
                        f"{len(all_links)} "
                        f"个"
                    )

                    next_url = (
                        self.get_next_page(
                            soup,
                            current_url,
                        )
                    )

                    if not next_url:

                        print(
                            "[ETRÉ TOKYO] "
                            "没有找到下一页，"
                            "搜索结果读取完成。"
                        )

                        break

                    current_url = (
                        next_url
                    )

                    page_number += 1

                except Exception as e:

                    print(
                        "[ETRÉ TOKYO] "
                        f"读取第 "
                        f"{page_number} "
                        f"页失败：{e}"
                    )

                    break

            print(
                "[ETRÉ TOKYO] "
                "商品列表读取完成，"
                f"去重后共发现 "
                f"{len(all_links)} "
                "个商品链接"
            )

            # =================================
            # 第二阶段：
            # 逐个打开商品详情页
            # =================================

            total = len(
                all_links
            )

            for index, url in enumerate(
                sorted(all_links),
                start=1,
            ):

                try:

                    print(
                        "[ETRÉ TOKYO] "
                        "正在读取商品详情 "
                        f"{index}/{total}"
                    )

                    await page.goto(
                        url,
                        wait_until=(
                            "networkidle"
                        ),
                        timeout=60000,
                    )

                    psoup = (
                        BeautifulSoup(
                            await page.content(),
                            "html.parser",
                        )
                    )

                    title_el = (
                        psoup.select_one(
                            "h1, "
                            ".goods_name, "
                            ".item_name"
                        )
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

                    price_el = (
                        psoup.select_one(
                            ".price, "
                            "[class*='price']"
                        )
                    )

                    price = (
                        price_el.get_text(
                            " ",
                            strip=True,
                        )
                        if price_el
                        else ""
                    )

                    img_el = (
                        psoup.select_one(
                            "main img, "
                            ".goods img, "
                            ".item img"
                        )
                    )

                    image_url = ""

                    if (
                        img_el
                        and img_el.get(
                            "src"
                        )
                    ):

                        image_url = (
                            urljoin(
                                url,
                                img_el.get(
                                    "src"
                                ),
                            )
                        )

                    text = (
                        psoup.get_text(
                            " ",
                            strip=True,
                        )
                    )

                    variants = []

                    # 暂时读取常见的规格元素。
                    # 后续根据实际页面结构，
                    # 再精确区分颜色和尺码。
                    for el in psoup.select(
                        "select option, "
                        "button, "
                        "label"
                    ):

                        label = (
                            el.get_text(
                                " ",
                                strip=True,
                            )
                        )

                        if (
                            not label
                            or len(label) > 80
                        ):
                            continue

                        status = (
                            self.normalize(
                                label
                                + " "
                                + " ".join(
                                    el.get(
                                        "class",
                                        [],
                                    )
                                )
                            )
                        )

                        if (
                            status
                            != "unknown"
                        ):

                            variants.append(
                                Variant(
                                    size=label,
                                    status=status,
                                )
                            )

                    # 如果没有识别到规格，
                    # 暂时保存商品整体库存状态。
                    if not variants:

                        variants = [
                            Variant(
                                status=(
                                    self.normalize(
                                        text
                                    )
                                )
                            )
                        ]

                    products.append(
                        Product(
                            site=self.site,
                            url=url,
                            name=name,
                            price=price,
                            image_url=(
                                image_url
                            ),
                            variants=(
                                variants
                            ),
                        )
                    )

                except Exception as e:

                    print(
                        "[ETRÉ TOKYO] "
                        "商品详情读取失败："
                        f"{url}"
                    )

                    print(
                        "[ETRÉ TOKYO] "
                        f"错误：{e}"
                    )

                    continue

            await browser.close()

        print(
            "[ETRÉ TOKYO] "
            "商品详情读取完成，"
            f"成功保存 "
            f"{len(products)} "
            "个商品"
        )

        return products
