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

            if "/shop/g/g" in url:
                links.add(url)

        return links

    def get_page_links(
        self,
        soup,
        base_url,
    ):
        """
        只读取真正的商品分页。

        ETRÉ 的真正分页 URL 带有：
        p=2、p=3、p=4……

        sort=c3、sort=sp、sort=spd 是排序链接，
        不加入分页。
        """

        # 第一页固定加入
        page_links = {
            self.start_url
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

            parsed = urlparse(
                url
            )

            # 必须是商品搜索页面
            if (
                "/shop/goods/search.aspx"
                not in parsed.path
            ):
                continue

            query = parse_qs(
                parsed.query
            )

            # 必须有真正的页码参数 p
            if (
                "p"
                not in query
            ):
                continue

            page_value = (
                query["p"][0]
            )

            # 页码必须是数字
            if not page_value.isdigit():
                continue

            page_number = int(
                page_value
            )

            # 第一页已经固定加入，
            # 这里只加入第 2 页及以后
            if page_number < 2:
                continue

            # 必须保留原搜索条件
            if (
                query.get(
                    "yy_min_releasedt",
                    [""],
                )[0]
                != "2010"
            ):
                continue

            # 统一移除 URL 锚点
            clean_url = (
                parsed._replace(
                    fragment=""
                ).geturl()
            )

            page_links.add(
                clean_url
            )

        return page_links

    def get_page_number(
        self,
        url,
    ):
        """
        从 URL 中取得页码。

        第一页没有 p 参数，
        所以默认返回 1。
        """

        parsed = urlparse(
            url
        )

        query = parse_qs(
            parsed.query
        )

        value = query.get(
            "p",
            ["1"],
        )[0]

        if value.isdigit():
            return int(
                value
            )

        return 1

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

            # 按真正页码排序：
            # 第 1 页、第 2 页、第 3 页……
            sorted_page_urls = sorted(
                page_urls,
                key=self.get_page_number,
            )

            print(
                "[ETRÉ TOKYO] "
                "找到 "
                f"{len(sorted_page_urls)} "
                "个真正的商品分页"
            )

            # =================================
            # 第二阶段：
            # 逐页读取商品
            # =================================

            all_links = set()

            for page_index, current_url in enumerate(
                sorted_page_urls,
                start=1,
            ):

                try:

                    actual_page_number = (
                        self.get_page_number(
                            current_url
                        )
                    )

                    print(
                        "[ETRÉ TOKYO] "
                        "正在读取第 "
                        f"{page_index}/"
                        f"{len(sorted_page_urls)} "
                        "页"
                        f"（实际页码 "
                        f"{actual_page_number}）："
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
                        "当前页发现 "
                        f"{len(page_products)} "
                        "个商品，"
                        "新增 "
                        f"{new_count} "
                        "个，"
                        "当前去重总数 "
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
                "去重后共发现 "
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
            "成功保存 "
            f"{len(products)} "
            "个商品"
        )

        return products
