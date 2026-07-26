from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.costco.com.tw"
SOURCE_URLS = [
    "https://www.costco.com.tw/c/hot-buys",
    "https://www.costco.com.tw/Deals/c/Coupon",
]
MAX_PAGES_PER_SOURCE = 20
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
    "AppleWebKit/537.36 CostcoDailyDeals/1.0"
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


def parse_products(html: str, source_url: str) -> list[Deal]:
    """從 Costco 商品列表頁擷取商品；選擇器留有備援以容納小幅改版。"""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".product-item, .product__list--item, li.product-item")
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
        price_match = re.search(r"\$\s*[\d,]+", price_text)
        price = price_match.group(0).replace(" ", "") if price_match else "請查看官網"
        discount_match = re.search(r"商品已折價\s*\$\s*([\d,]+)", price_text)
        discount_amount = (
            f"${discount_match.group(1)}" if discount_match else ""
        )
        original_price = ""
        if price_match and discount_match:
            sale_number = int(re.sub(r"\D", "", price_match.group(0)))
            discount_number = int(discount_match.group(1).replace(",", ""))
            original_price = f"${sale_number + discount_number:,}"
        promotion_node = card.select_one(
            ".promotion-message, .promotion, [class*='promotion']"
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


def fetch(url: str) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9"},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


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
        unique.setdefault(key, deal)
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
    for url in SOURCE_URLS:
        try:
            source_deals, source_pages = collect_source(url)
            all_deals.extend(source_deals)
            pages_read += source_pages
        except requests.RequestException as exc:
            errors.append(f"{url}: {exc}")

    deals = deduplicate(all_deals)
    if not deals:
        print("沒有抓到商品，網站版面可能已變更。", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1

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
