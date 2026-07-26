from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.costco.com.tw"
SOURCE_URLS = [
    "https://www.costco.com.tw/c/hot-buys",
    "https://www.costco.com.tw/Deals/c/Coupon",
]
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
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


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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
            ".price, .product__list--price, .product-price, [class*='price']"
        )
        price_text = clean(price_node.get_text(" ", strip=True)) if price_node else ""
        price_match = re.search(r"\$\s*[\d,]+", price_text)
        price = price_match.group(0).replace(" ", "") if price_match else "請查看官網"
        url = urljoin(BASE_URL, link.get("href", ""))
        deals.append(Deal(name=name, price=price, url=url, source=source_url))

    return deals


def fetch(url: str) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9"},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


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
            )
            for row in csv.DictReader(handle)
        ]


def write_csv(csv_path: Path, deals: Iterable[Deal], date_text: str) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["日期", "商品", "價格", "商品網址", "資料來源"])
        for deal in deals:
            writer.writerow([date_text, deal.name, deal.price, deal.url, deal.source])


def deal_lines(deals: Iterable[Deal]) -> list[str]:
    return [
        f"- [{deal.name.replace('|', '｜')}]({deal.url})（{deal.price}）"
        for deal in deals
    ]


def write_outputs(
    deals: list[Deal],
    previous_deals: list[Deal],
    generated_at: datetime,
    has_previous: bool,
) -> tuple[Path, Path, Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_text = generated_at.strftime("%Y-%m-%d")
    time_text = generated_at.strftime("%Y-%m-%d %H:%M")
    csv_path = OUTPUT_DIR / "latest.csv"
    md_path = OUTPUT_DIR / "latest.md"
    summary_path = OUTPUT_DIR / "summary.md"
    history_path = OUTPUT_DIR / "history" / f"{date_text}.csv"
    added, removed = compare_deals(deals, previous_deals)

    write_csv(csv_path, deals, date_text)
    write_csv(history_path, deals, date_text)

    summary_lines = [
        f"# Costco 每日優惠摘要（{date_text}）",
        "",
        f"更新時間：{time_text}（台灣時間）",
        f"共整理出 **{len(deals)}** 項官方線上優惠。",
        "",
        "> 價格、庫存與實體賣場活動可能隨時變動，購買前請以 Costco 官網或現場為準。",
        "",
    ]
    if has_previous:
        summary_lines.extend(
            [
                f"- 新增優惠：**{len(added)}** 項",
                f"- 已結束或不在清單：**{len(removed)}** 項",
                "",
                "### 今日新增",
                "",
            ]
        )
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
        "| 商品 | 價格 |",
        "|---|---:|",
        ]
    )
    lines.extend(
        f"| [{deal.name.replace('|', '｜')}]({deal.url}) | {deal.price} |"
        for deal in deals
    )
    lines.extend(["", "資料來源：", ""])
    lines.extend(f"- {url}" for url in SOURCE_URLS)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, csv_path, history_path, summary_path


def main() -> int:
    all_deals: list[Deal] = []
    errors: list[str] = []
    for url in SOURCE_URLS:
        try:
            all_deals.extend(parse_products(fetch(url), url))
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
    md_path, csv_path, history_path, summary_path = write_outputs(
        deals, previous_deals, now, has_previous
    )
    print(f"完成：{len(deals)} 項優惠")
    if has_previous:
        added, removed = compare_deals(deals, previous_deals)
        print(f"- 今日新增：{len(added)} 項")
        print(f"- 已結束或不在清單：{len(removed)} 項")
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
