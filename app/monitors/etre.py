from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.models import Product, Variant
from .base import BaseMonitor


class EtreMonitor(BaseMonitor):
    site = "ETRÉ TOKYO"

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
        links = set()

        for a in soup.select(
            "a[href*='/shop/g/g']"
        ):
            href = a.get("href", "")

            if not href:
                continue

            url = urljoin(
                base_url,
                href,
            )

            if (
                "/shop/g/g"
                in url
            ):
                links.add(url)

        return links

    def get_page_links(
        self,
        soup,
        base_url,
    ):
        """
        从页面中寻找全部分页链接。

        ETRÉ 的分页可能不是“次へ”文字，
        因此直接寻找搜索页 search.aspx 的链接，
        再根据 URL 参数判断是否是分页。
        """

        page_links = {
            base_url
        }

        for a in soup.select(
            "a[href]"
        ):
            href = a.get(
                "href",
                ""
            )

            if not href:
                continue

            url = urljoin(
                base_url,
                href,
            )

            if (
                "/shop/goods/search.aspx"
                not in url
            ):
                continue

            # 必须保留原搜索条件。
            if (
                "yy_min_releasedt=2010"
                not in url
            ):
                continue

            page_links.add(
                url
            )

        return page_links

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
            # 读取第一页并找出全部分页
            # =================================

            print(
                "[ETRÉ TOKYO] "
                "正在读取第一页："
                f"{self.start_url}"
            )

            await page.goto(
                self.start_url,
                wait_until="networkidle",
                timeout=90000,
            )

            first_soup = (
                BeautifulSoup(
                    await page.content(),
                    "html.parser",
                )
            )

            page_urls = (
                self.get_page_links(
                    first_soup,
                    self.start_url,
                )
            )

            print(
                "[ETRÉ TOKYO] "
                "第一页找到 "
                f"{len(page_urls)} "
                "个可能的分页链接"
            )

            # =================================
            # 第二阶段：
            # 逐页读取商品
            # =================================

            all_links = set()

            sorted_page_urls = sorted(
                page_urls
            )

            for page_number, current_url in enumerate(
                sorted_page_urls,
                start=1,
            ):

                try:

                    print(
                        "[ETRÉ TOKYO] "
                        f"正在读取第 "
                        f"{page_number}/"
                        f"{len(sorted_page_urls)} "
                        "个分页："
                        f"{current_url}"
                    )

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

                    page_products = (
                        self.get_product_links(
                            soup,
                            current_url,
                        )
                    )

                    before_count = (
                        len(all_links)
                    )

                    all_links.update(
                        page_products
                    )

                    new_count = (
                        len(all_links)
                        - before_count
                    )

                    print(
                        "[ETRÉ TOKYO] "
                        f"当前页发现 "
                        f"{len(page_products)} "
                        "个商品，"
                        f"新增 "
                        f"{new_count} "
                        "个，"
                        f"当前去重总数 "
                        f"{len(all_links)} "
                        "个"
                    )

                except Exception as e:

                    print(
                        "[ETRÉ TOKYO] "
                        "分页读取失败："
                        f"{current_url}"
                    )

                    print(
                        "[ETRÉ TOKYO] "
                        f"错误：{e}"
                    )

                    continue

            print(
                "[ETRÉ TOKYO] "
                "商品列表读取完成，"
                f"去重后共发现 "
                f"{len(all_links)} "
                "个商品链接"
            )

            # =================================
            # 第三阶段：
            # 逐个读取商品详情
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
