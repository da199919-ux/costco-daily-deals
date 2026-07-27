from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.costco.com.tw"
SOURCE_URLS = [
    "https://www.costco.com.tw/voucher4",
    "https://www.costco.com.tw/voucher2",
    "https://www.costco.com.tw/c/hot-buys",
    "https://www.costco.com.tw/Deals/c/Coupon",
    "https://www.costco.com.tw/c/Hero_Cool",
]
MAX_PAGES_PER_SOURCE = 20
DETAIL_WORKERS = 3
MULTIBUY_PROMOTIONS = {
    "https://www.costco.com.tw/voucher4": (
        "指定夏日涼感商品",
        2,
        0.85,
        3,
        0.8,
    ),
    "https://www.costco.com.tw/voucher2": (
        "指定家具",
        1,
        0.85,
        2,
        0.8,
    ),
}
CATEGORY_RULES = [
    ("食品飲料", ("food-dining",)),
    ("家電 3C", ("digital-mobile", "televisions-appliances")),
    ("日用品／母嬰／玩具", ("household-baby-toys",)),
    ("家具家居", ("furniture-kitchen",)),
    ("保健美容", ("health-beauty",)),
    ("服飾配件", ("clothing-accessories",)),
    ("運動休閒", ("online-exclusive-exercise",)),
]
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
WATCHLIST_PATH = Path(__file__).resolve().parents[1] / "watchlist.txt"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPad; CPU OS 18_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.5 Mobile/15E148 Safari/604.1"
)


@dataclass(frozen=True)
class Deal:
    name: str
    price: str
    url: str
    source: str
    image_url: str = ""
    original_price: str = ""
    discount_amount: str = ""
    promotion: str = ""


@dataclass(frozen=True)
class PriceChange:
    deal: Deal
    old_price: str
    direction: str


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def categorize(deal: Deal) -> str:
    path = urlsplit(deal.url).path.casefold()
    for category, markers in CATEGORY_RULES:
        if any(marker in path for marker in markers):
            return category
    return "其他"


def parse_voucher_products(html: str, source_url: str) -> list[Deal]:
    """解析優惠券說明頁使用的自訂商品卡片。"""
    soup = BeautifulSoup(html, "html.parser")
    deals: list[Deal] = []
    seen: set[str] = set()

    for link in soup.select("a[href*='/p/']"):
        url = urljoin(BASE_URL, link.get("href", ""))
        if not url or url in seen:
            continue

        name = clean(link.get_text(" ", strip=True))
        image_in_link = link.select_one("img")
        if not name and image_in_link:
            name = clean(image_in_link.get("alt", ""))
        if not name:
            name = clean(link.get("aria-label", ""))
        if not name:
            continue

        fallback_container = None
        discount_container = None
        for parent in list(link.parents)[:10]:
            text = clean(parent.get_text(" ", strip=True))
            if "$" not in text:
                continue
            fallback_container = fallback_container or parent
            if re.search(r"(?:商品已折價|商品折扣)", text):
                discount_container = parent
                break
        container = discount_container or fallback_container
        if container is None:
            continue

        card_text = clean(container.get_text(" ", strip=True))
        price_match = re.search(r"\$\s*([\d,]+)", card_text)
        if not price_match:
            continue
        price = f"${price_match.group(1)}"
        discount_match = re.search(
            r"(?:商品已折價|商品折扣)\s*(?:[-−–]\s*)?\$\s*([\d,]+)",
            card_text,
        )
        discount_amount = (
            f"${discount_match.group(1)}" if discount_match else ""
        )
        original_price = ""
        if discount_match:
            original_price = (
                f"${price_number(price) + int(discount_match.group(1).replace(',', '')):,}"
            )

        image = container.select_one("img")
        image_url = ""
        if image:
            for attribute in ("data-src", "data-original", "src"):
                candidate = clean(image.get(attribute, ""))
                if candidate and not candidate.startswith("data:"):
                    image_url = urljoin(BASE_URL, candidate)
                    break

        deals.append(
            Deal(
                name=name,
                price=price,
                url=url,
                source=source_url,
                image_url=image_url,
                original_price=original_price,
                discount_amount=discount_amount,
                promotion=(
                    f"商品已折價 {discount_amount}" if discount_amount else ""
                ),
            )
        )
        seen.add(url)

    return deals


def parse_products(html: str, source_url: str) -> list[Deal]:
    """從 Costco 商品列表頁擷取商品；選擇器留有備援以容納小幅改版。"""
    if re.search(r"/voucher\d+(?:$|[/?#])", source_url):
        return parse_voucher_products(html, source_url)
    soup = BeautifulSoup(html, "html.parser")
    # 優惠頁底部也會出現「專屬推薦／您可能會喜歡」商品，它們不屬於
    # 當前活動。優先只讀主要商品列表，避免把活動折扣錯套到推薦商品。
    listing = soup.select_one(
        ".product__listing, .product-listing, "
        "[data-testid='product-list'], #product-list"
    )
    card_selector = ".product-item, .product__list--item, li.product-item"
    cards = listing.select(card_selector) if listing else soup.select(card_selector)
    deals: list[Deal] = []

    for card in cards:
        link = card.select_one(
            "a.name, a.product__list--name, .product-name a, a[href*='/p/']"
        )
        if not link:
            continue
        name = clean(link.get_text(" ", strip=True))
        if not name:
            image = card.select_one("img[alt]")
            name = clean(image.get("alt", "")) if image else ""
        if not name:
            continue

        price_node = card.select_one(
            ".price-panel, .price, .product__list--price, .product-price, [class*='price']"
        )
        price_text = clean(price_node.get_text(" ", strip=True)) if price_node else ""
        card_text = clean(card.get_text(" ", strip=True))

        # Costco 的響應式商品卡有時把售價和「商品已折價」拆在不同
        # HTML 區塊。優先從整張卡片讀取相鄰的售價與折價金額，
        # 避免只抓到原價而漏掉手機版可見的優惠。
        sale_discount_match = re.search(
            r"\$\s*([\d,]+)\s*(?:商品已折價|商品折扣)"
            r"\s*(?:[-−–]\s*)?\$\s*([\d,]+)",
            card_text,
        )
        price_match = re.search(r"\$\s*[\d,]+", price_text)
        if sale_discount_match:
            price = f"${sale_discount_match.group(1)}"
        else:
            price = (
                price_match.group(0).replace(" ", "")
                if price_match
                else "請查看官網"
            )
        discount_match = re.search(
            r"(?:商品已折價|商品折扣)\s*(?:[-−–]\s*)?\$\s*([\d,]+)",
            card_text,
        )
        discount_amount = (
            f"${discount_match.group(1)}" if discount_match else ""
        )
        original_price = ""
        if price_number(price) is not None and discount_match:
            sale_number = price_number(price)
            discount_number = int(discount_match.group(1).replace(",", ""))
            original_price = f"${sale_number + discount_number:,}"
        promotion_node = card.select_one(
            ".promotion-message, .promotion, .discount-info"
        )
        promotion = (
            clean(promotion_node.get_text(" ", strip=True))
            if promotion_node
            else ""
        )
        url = urljoin(BASE_URL, link.get("href", ""))
        image = card.select_one("img")
        image_url = ""
        if image:
            for attribute in ("data-src", "data-original", "src"):
                candidate = clean(image.get(attribute, ""))
                if candidate and not candidate.startswith("data:"):
                    image_url = urljoin(BASE_URL, candidate)
                    break
            if not image_url:
                srcset = clean(image.get("srcset", ""))
                if srcset:
                    candidate = srcset.split(",")[0].strip().split(" ")[0]
                    if candidate and not candidate.startswith("data:"):
                        image_url = urljoin(BASE_URL, candidate)

        deals.append(
            Deal(
                name=name,
                price=price,
                url=url,
                source=source_url,
                image_url=image_url,
                original_price=original_price,
                discount_amount=discount_amount,
                promotion=promotion,
            )
        )

    return deals


def add_multibuy_promotion(deal: Deal, source_url: str) -> Deal:
    # 只對 Costco 的指定活動券清單計算多件折扣。一般主題專區
    # （例如 Hero_Cool）可能混有推薦或非指定商品，不能僅憑來源頁
    # 就推定每項商品都符合相同優惠。
    rule = MULTIBUY_PROMOTIONS.get(source_url)
    current = price_number(deal.price)
    if not rule or current is None:
        return deal
    label, first_quantity, first_rate, second_quantity, second_rate = rule

    # 家具活動是在符合條件後於結帳時折扣，商品頁顯示的仍是目前售價。
    # 不把推算後的 85 折價格冒充為單品特價，只顯示活動條件。
    if source_url == "https://www.costco.com.tw/voucher2":
        conditions = (
            "2026/07/20-08/02期間購買指定家具，"
            "買1件享85折，買2件享8折優惠。"
        )
        promotion = "；".join(
            part for part in (deal.promotion, conditions) if part
        )
        return replace(deal, promotion=promotion)

    first_each = round(current * first_rate)
    second_each = round(current * second_rate)
    conditions = (
        f"{label}：買{first_quantity}件享{first_rate * 10:g}折，"
        f"每件約 ${first_each:,}；買{second_quantity}件享"
        f"{second_rate * 10:g}折，每件約 ${second_each:,}"
    )

    # 商品本身已有固定折價時，以 Costco 公布的固定特價為主，
    # 多件優惠只補充顯示，避免覆蓋更精確的折扣後小計。
    if deal.discount_amount or deal.original_price:
        promotion = "；".join(
            part for part in (deal.promotion, conditions) if part
        )
        return replace(deal, promotion=promotion)

    # 多件優惠沒有獨立的「小計」欄位，因此將最低購買門檻下的
    # 每件價格直接放在卡片主價格，並清楚保留購買件數條件。
    discount = current - first_each
    return replace(
        deal,
        price=f"${first_each:,}",
        original_price=f"${current:,}",
        discount_amount=f"${discount:,}",
        promotion=conditions,
    )


def parse_product_detail(html: str, deal: Deal) -> Deal:
    """從商品詳細頁補上列表頁未提供的原價、折價與優惠文字。"""
    soup = BeautifulSoup(html, "html.parser")
    detail_text = clean(soup.get_text(" ", strip=True))

    explicit_original = re.search(
        r"商品原價\s*(?:NT\$|\$)\s*([\d,]+)", detail_text
    )
    previous_original = re.search(
        r"前次原價(?:為)?\s*(?:NT\$|\$)\s*([\d,]+)", detail_text
    )
    discount_match = re.search(
        r"(?:商品已折價|商品折扣)\s*(?:[-−–]\s*)?(?:NT\$|\$)\s*([\d,]+)",
        detail_text,
    )
    subtotal_match = re.search(
        r"(?:小計|折扣後價格|優惠價)\s*(?:NT\$|\$)\s*([\d,]+)",
        detail_text,
    )
    current_match = re.search(
        r"(?:售價|優惠價|網路價|特價)?\s*(?:NT\$|\$)\s*([\d,]+)",
        detail_text,
    )

    price = (
        f"${subtotal_match.group(1)}"
        if subtotal_match
        else deal.price
    )
    if price_number(price) is None and current_match:
        price = f"${current_match.group(1)}"

    discount_amount = deal.discount_amount
    if not discount_amount and discount_match:
        discount_amount = f"${discount_match.group(1)}"

    original_price = deal.original_price
    explicit_original_number = (
        int(explicit_original.group(1).replace(",", ""))
        if explicit_original
        else None
    )
    if (
        not original_price
        and explicit_original
        and (
            discount_match
            or explicit_original_number != price_number(price)
        )
    ):
        original_price = f"${explicit_original.group(1)}"
    if not original_price and discount_match and price_number(price) is not None:
        original_price = (
            f"${price_number(price) + int(discount_match.group(1).replace(',', '')):,}"
        )
    if (
        not original_price
        and not discount_amount
        and previous_original
        and price_number(price) is not None
    ):
        previous_number = int(previous_original.group(1).replace(",", ""))
        current_number = price_number(price)
        if previous_number > current_number:
            original_price = f"${previous_number:,}"
            discount_amount = f"${previous_number - current_number:,}"

    promotion = deal.promotion
    if not promotion:
        promotion_node = soup.select_one(
            ".promotion-message, .discount-info"
        )
        if promotion_node:
            promotion = clean(promotion_node.get_text(" ", strip=True))
        elif discount_match:
            promotion = f"商品已折價 ${discount_match.group(1)}"
        elif original_price and previous_original:
            promotion = "Costco 公布的目前優惠售價"

    return replace(
        deal,
        price=price,
        original_price=original_price,
        discount_amount=discount_amount,
        promotion=promotion,
    )


def enrich_product_details(
    deals: Iterable[Deal],
    fetcher: Callable[[str], str] | None = None,
    workers: int = DETAIL_WORKERS,
) -> tuple[list[Deal], int]:
    """平行讀取商品詳細頁；單一頁面失敗時保留列表頁資料。"""
    fetcher = fetcher or fetch
    items = list(deals)
    enriched = list(items)
    completed = 0

    def read_one(index: int, deal: Deal) -> tuple[int, Deal]:
        return index, parse_product_detail(fetcher(deal.url), deal)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(read_one, index, deal): index
            for index, deal in enumerate(items)
            if deal.url
        }
        for future in as_completed(futures):
            try:
                index, updated = future.result()
            except (requests.RequestException, ValueError):
                continue
            enriched[index] = updated
            completed += 1

    return enriched, completed


def fetch(url: str) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9"},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


@contextmanager
def browser_source_fetcher():
    """以真正的瀏覽器讀取優惠清單，取得 JavaScript 載入的折價資料。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=MOBILE_USER_AGENT,
            viewport={"width": 1024, "height": 1366},
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()

        def rendered_fetch(url: str) -> str:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2_500)
                # 部分商品卡會在捲動後才載入折價文字。
                for _ in range(4):
                    page.evaluate("window.scrollBy(0, document.body.scrollHeight / 4)")
                    page.wait_for_timeout(500)
                return page.content()
            except Exception as exc:
                print(
                    f"瀏覽器讀取失敗，改用一般方式：{url}（{exc}）",
                    file=sys.stderr,
                )
                return fetch(url)

        try:
            yield rendered_fetch
        finally:
            context.close()
            browser.close()


def with_page(url: str, page: int) -> str:
    if page == 0:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["page"] = str(page)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def collect_source(
    source_url: str,
    fetcher: Callable[[str], str] = fetch,
    max_pages: int = MAX_PAGES_PER_SOURCE,
) -> tuple[list[Deal], int]:
    """逐頁收集商品；空白頁或整頁重複時自動停止。"""
    collected: list[Deal] = []
    seen: set[str] = set()
    pages_read = 0

    for page in range(max_pages):
        deals = parse_products(fetcher(with_page(source_url, page)), source_url)
        deals = [add_multibuy_promotion(deal, source_url) for deal in deals]
        new_deals = [deal for deal in deals if deal_key(deal) not in seen]
        if not new_deals:
            break
        collected.extend(new_deals)
        seen.update(deal_key(deal) for deal in new_deals)
        pages_read += 1

    return collected, pages_read


def deduplicate(deals: Iterable[Deal]) -> list[Deal]:
    unique: dict[str, Deal] = {}
    for deal in deals:
        key = deal.url or deal.name.casefold()
        existing = unique.get(key)
        if existing is None:
            unique[key] = deal
            continue
        prefer_discounted = bool(deal.discount_amount) and not bool(
            existing.discount_amount
        )
        unique[key] = replace(
            existing,
            price=deal.price if prefer_discounted else existing.price,
            source=deal.source if prefer_discounted else existing.source,
            image_url=existing.image_url or deal.image_url,
            original_price=existing.original_price or deal.original_price,
            discount_amount=existing.discount_amount or deal.discount_amount,
            promotion=deal.promotion if prefer_discounted else (
                existing.promotion or deal.promotion
            ),
        )
    return sorted(unique.values(), key=lambda item: item.name.casefold())


def deal_key(deal: Deal) -> str:
    return deal.url or deal.name.casefold()


def compare_deals(
    current: Iterable[Deal], previous: Iterable[Deal]
) -> tuple[list[Deal], list[Deal]]:
    current_by_key = {deal_key(deal): deal for deal in current}
    previous_by_key = {deal_key(deal): deal for deal in previous}
    added = [
        deal for key, deal in current_by_key.items() if key not in previous_by_key
    ]
    removed = [
        deal for key, deal in previous_by_key.items() if key not in current_by_key
    ]
    return deduplicate(added), deduplicate(removed)


def price_number(price: str) -> int | None:
    match = re.search(r"[\d,]+", price)
    return int(match.group(0).replace(",", "")) if match else None


def compare_prices(
    current: Iterable[Deal], previous: Iterable[Deal]
) -> list[PriceChange]:
    previous_by_key = {deal_key(deal): deal for deal in previous}
    changes: list[PriceChange] = []
    for deal in current:
        old = previous_by_key.get(deal_key(deal))
        if not old or old.price == deal.price:
            continue
        old_number = price_number(old.price)
        new_number = price_number(deal.price)
        if old_number is None or new_number is None:
            continue
        direction = "降價" if new_number < old_number else "漲價"
        changes.append(PriceChange(deal, old.price, direction))
    return sorted(changes, key=lambda change: change.deal.name.casefold())


def load_deals(csv_path: Path) -> list[Deal]:
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            Deal(
                name=row["商品"],
                price=row["價格"],
                url=row["商品網址"],
                source=row["資料來源"],
                image_url=row.get("圖片網址", ""),
                original_price=row.get("原價", ""),
                discount_amount=row.get("折價金額", ""),
                promotion=row.get("優惠說明", ""),
            )
            for row in csv.DictReader(handle)
        ]


def write_csv(csv_path: Path, deals: Iterable[Deal], date_text: str) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "日期",
                "分類",
                "商品",
                "價格",
                "原價",
                "折價金額",
                "優惠說明",
                "商品網址",
                "圖片網址",
                "資料來源",
            ]
        )
        for deal in deals:
            writer.writerow(
                [
                    date_text,
                    categorize(deal),
                    deal.name,
                    deal.price,
                    deal.original_price,
                    deal.discount_amount,
                    deal.promotion,
                    deal.url,
                    deal.image_url,
                    deal.source,
                ]
            )


def deal_lines(deals: Iterable[Deal]) -> list[str]:
    return [
        f"- [{deal.name.replace('|', '｜')}]({deal.url})（{deal.price}）"
        for deal in deals
    ]


def price_change_lines(changes: Iterable[PriceChange]) -> list[str]:
    return [
        (
            f"- **{change.direction}**："
            f"[{change.deal.name.replace('|', '｜')}]({change.deal.url}) "
            f"{change.old_price} → {change.deal.price}"
        )
        for change in changes
    ]


def load_keywords(path: Path = WATCHLIST_PATH) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def find_watchlist_matches(deals: Iterable[Deal], keywords: Iterable[str]) -> list[Deal]:
    normalized = [keyword.casefold() for keyword in keywords if keyword.strip()]
    return [
        deal
        for deal in deals
        if any(keyword in deal.name.casefold() for keyword in normalized)
    ]


def write_outputs(
    deals: list[Deal],
    previous_deals: list[Deal],
    generated_at: datetime,
    has_previous: bool,
    keywords: list[str],
    pages_read: int,
) -> tuple[Path, Path, Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_text = generated_at.strftime("%Y-%m-%d")
    time_text = generated_at.strftime("%Y-%m-%d %H:%M")
    csv_path = OUTPUT_DIR / "latest.csv"
    md_path = OUTPUT_DIR / "latest.md"
    summary_path = OUTPUT_DIR / "summary.md"
    history_path = OUTPUT_DIR / "history" / f"{date_text}.csv"
    added, removed = compare_deals(deals, previous_deals)
    price_changes = compare_prices(deals, previous_deals)
    watched = find_watchlist_matches(deals, keywords)
    category_counts = Counter(categorize(deal) for deal in deals)

    write_csv(csv_path, deals, date_text)
    write_csv(history_path, deals, date_text)
    changes_path = OUTPUT_DIR / "changes.json"
    changes_path.write_text(
        json.dumps(
            {
                "date": date_text,
                "generated_at": time_text,
                "has_previous": has_previous,
                "added": [
                    {
                        "name": deal.name,
                        "price": deal.price,
                        "original_price": deal.original_price,
                        "discount_amount": deal.discount_amount,
                        "promotion": deal.promotion,
                        "url": deal.url,
                        "image": deal.image_url,
                        "category": categorize(deal),
                    }
                    for deal in added
                ],
                "removed": [
                    {
                        "name": deal.name,
                        "price": deal.price,
                        "original_price": deal.original_price,
                        "discount_amount": deal.discount_amount,
                        "promotion": deal.promotion,
                        "url": deal.url,
                        "image": deal.image_url,
                        "category": categorize(deal),
                    }
                    for deal in removed
                ],
                "price_changes": [
                    {
                        "name": change.deal.name,
                        "price": change.deal.price,
                        "original_price": change.deal.original_price,
                        "discount_amount": change.deal.discount_amount,
                        "promotion": change.deal.promotion,
                        "old_price": change.old_price,
                        "direction": change.direction,
                        "url": change.deal.url,
                        "image": change.deal.image_url,
                        "category": categorize(change.deal),
                    }
                    for change in price_changes
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary_lines = [
        f"# Costco 每日優惠摘要（{date_text}）",
        "",
        f"更新時間：{time_text}（台灣時間）",
        f"共整理出 **{len(deals)}** 項官方線上優惠。",
        f"本次共讀取 **{pages_read}** 個官方商品頁面。",
        "",
        "> 價格、庫存與實體賣場活動可能隨時變動，購買前請以 Costco 官網或現場為準。",
        "",
        "## 分類統計",
        "",
        "| 分類 | 商品數量 |",
        "|---|---:|",
    ]
    summary_lines.extend(
        f"| {category} | {count} |"
        for category, count in sorted(
            category_counts.items(), key=lambda item: (-item[1], item[0])
        )
    )
    summary_lines.extend(
        [
        "",
        "## 我的追蹤商品",
        "",
        f"追蹤關鍵字：{', '.join(keywords) if keywords else '尚未設定'}",
        "",
        ]
    )
    summary_lines.extend(
        deal_lines(watched) or ["- 今天的優惠清單沒有符合追蹤關鍵字的商品。"]
    )
    summary_lines.extend(["", "## 今日變化", ""])
    if has_previous:
        summary_lines.extend(
            [
                f"- 新增優惠：**{len(added)}** 項",
                f"- 已結束或不在清單：**{len(removed)}** 項",
                f"- 價格變動：**{len(price_changes)}** 項",
                "",
                "### 價格變動",
                "",
            ]
        )
        summary_lines.extend(
            price_change_lines(price_changes) or ["- 今天沒有偵測到價格變動。"]
        )
        summary_lines.extend(["", "### 今日新增", ""])
        summary_lines.extend(deal_lines(added) or ["- 今天沒有新增優惠。"])
        summary_lines.extend(["", "### 已結束或不在清單", ""])
        summary_lines.extend(deal_lines(removed) or ["- 今天沒有優惠離開清單。"])
    else:
        summary_lines.append(
            "- 這是第一份歷史紀錄，明天起會顯示新增與已結束優惠。"
        )
    summary_lines.extend(
        [
            "",
            "完整清單請查看專案中的 `output/latest.md`。",
        ]
    )
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    lines = [
        f"# Costco 台灣每日優惠清單（{date_text}）",
        "",
        "## 今日變化",
        "",
        *summary_lines[2:-2],
    ]
    lines.extend(
        [
            "",
            "## 全部優惠",
            "",
        "| 分類 | 商品 | 價格 |",
        "|---|---|---:|",
        ]
    )
    lines.extend(
        (
            f"| {categorize(deal)} | "
            f"[{deal.name.replace('|', '｜')}]({deal.url}) | {deal.price} |"
        )
        for deal in deals
    )
    lines.extend(["", "資料來源：", ""])
    lines.extend(f"- {url}" for url in SOURCE_URLS)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, csv_path, history_path, summary_path


def main() -> int:
    all_deals: list[Deal] = []
    errors: list[str] = []
    pages_read = 0
    try:
        with browser_source_fetcher() as source_fetcher:
            for url in SOURCE_URLS:
                try:
                    source_deals, source_pages = collect_source(
                        url, fetcher=source_fetcher
                    )
                    all_deals.extend(source_deals)
                    pages_read += source_pages
                except requests.RequestException as exc:
                    errors.append(f"{url}: {exc}")
    except Exception as exc:
        print(
            f"無法啟動瀏覽器，改用一般讀取方式（{exc}）",
            file=sys.stderr,
        )
        for url in SOURCE_URLS:
            try:
                source_deals, source_pages = collect_source(url)
                all_deals.extend(source_deals)
                pages_read += source_pages
            except requests.RequestException as request_exc:
                errors.append(f"{url}: {request_exc}")

    deals = deduplicate(all_deals)
    if not deals:
        print("沒有抓到商品，網站版面可能已變更。", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    deals, detail_pages_read = enrich_product_details(deals)
    pages_read += detail_pages_read

    now = datetime.now(ZoneInfo("Asia/Taipei"))
    csv_path = OUTPUT_DIR / "latest.csv"
    has_previous = csv_path.exists()
    previous_deals = load_deals(csv_path)
    keywords = load_keywords()
    md_path, csv_path, history_path, summary_path = write_outputs(
        deals, previous_deals, now, has_previous, keywords, pages_read
    )
    print(f"完成：{len(deals)} 項優惠")
    print(f"- 已讀取頁面：{pages_read} 頁")
    print(f"- 追蹤商品：{len(find_watchlist_matches(deals, keywords))} 項")
    if has_previous:
        added, removed = compare_deals(deals, previous_deals)
        price_changes = compare_prices(deals, previous_deals)
        print(f"- 今日新增：{len(added)} 項")
        print(f"- 已結束或不在清單：{len(removed)} 項")
        print(f"- 價格變動：{len(price_changes)} 項")
    print(f"- {md_path}")
    print(f"- {csv_path}")
    print(f"- {history_path}")
    print(f"- {summary_path}")
    if errors:
        print("部分來源讀取失敗：", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
