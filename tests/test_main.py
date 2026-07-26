import tempfile
import unittest
from pathlib import Path

from src.main import (
    Deal,
    categorize,
    collect_source,
    compare_deals,
    compare_prices,
    deduplicate,
    find_watchlist_matches,
    load_deals,
    load_keywords,
    parse_products,
    write_csv,
    with_page,
)


SAMPLE_HTML = """
<div class="product-item">
  <a class="name" href="/Food/p/123">科克蘭測試商品</a>
  <img data-src="/medias/test-product.jpg" alt="科克蘭測試商品">
  <span class="price">$1,299</span>
</div>
"""

DISCOUNT_HTML = """
<div class="product-item">
  <a class="name" href="/Food/p/456">折價測試商品</a>
  <img src="/medias/discount.jpg" alt="折價測試商品">
  <div class="price-panel">
    <div class="original-price"><span class="product-price-amount">$925</span></div>
    <span>商品已折價 $234</span>
  </div>
</div>
"""


class CostcoDealsTest(unittest.TestCase):
    def test_parse_product(self):
        deals = parse_products(SAMPLE_HTML, "https://example.test/deals")
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].name, "科克蘭測試商品")
        self.assertEqual(deals[0].price, "$1,299")
        self.assertEqual(deals[0].url, "https://www.costco.com.tw/Food/p/123")
        self.assertEqual(
            deals[0].image_url,
            "https://www.costco.com.tw/medias/test-product.jpg",
        )

    def test_deduplicate_by_url(self):
        deal = parse_products(SAMPLE_HTML, "https://example.test/deals")[0]
        self.assertEqual(len(deduplicate([deal, deal])), 1)

    def test_parse_discount_and_calculate_original_price(self):
        deal = parse_products(DISCOUNT_HTML, "https://example.test/deals")[0]
        self.assertEqual(deal.price, "$925")
        self.assertEqual(deal.discount_amount, "$234")
        self.assertEqual(deal.original_price, "$1,159")

    def test_compare_added_and_removed(self):
        old = Deal("舊商品", "$100", "https://example.test/old", "測試")
        new = Deal("新商品", "$90", "https://example.test/new", "測試")
        added, removed = compare_deals([new], [old])
        self.assertEqual(added, [new])
        self.assertEqual(removed, [old])

    def test_csv_history_can_be_loaded(self):
        deal = Deal("測試商品", "$99", "https://example.test/item", "測試")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deals.csv"
            write_csv(path, [deal], "2026-07-26")
            self.assertEqual(load_deals(path), [deal])

    def test_watchlist_is_case_insensitive(self):
        iphone = Deal("Apple iPhone 16", "$1", "https://example.test/iphone", "測試")
        coffee = Deal("咖啡豆", "$2", "https://example.test/coffee", "測試")
        self.assertEqual(find_watchlist_matches([iphone, coffee], ["iphone"]), [iphone])

    def test_load_keywords_skips_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watchlist.txt"
            path.write_text("# 我的清單\nApple\n\niPad\n", encoding="utf-8")
            self.assertEqual(load_keywords(path), ["Apple", "iPad"])

    def test_page_url(self):
        self.assertEqual(with_page("https://example.test/deals", 0), "https://example.test/deals")
        self.assertEqual(
            with_page("https://example.test/deals?sort=name", 2),
            "https://example.test/deals?sort=name&page=2",
        )

    def test_collect_source_stops_on_repeated_page(self):
        first_page = SAMPLE_HTML
        calls = []

        def fake_fetch(url):
            calls.append(url)
            return first_page

        deals, pages_read = collect_source(
            "https://example.test/deals", fetcher=fake_fetch, max_pages=5
        )
        self.assertEqual(len(deals), 1)
        self.assertEqual(pages_read, 1)
        self.assertEqual(len(calls), 2)

    def test_compare_prices_detects_drop_and_increase(self):
        old_phone = Deal("iPhone", "$30,000", "https://example.test/phone", "測試")
        new_phone = Deal("iPhone", "$28,000", "https://example.test/phone", "測試")
        old_mac = Deal("MacBook", "$40,000", "https://example.test/mac", "測試")
        new_mac = Deal("MacBook", "$42,000", "https://example.test/mac", "測試")
        changes = compare_prices([new_phone, new_mac], [old_phone, old_mac])
        self.assertEqual(changes[0].direction, "降價")
        self.assertEqual(changes[1].direction, "漲價")

    def test_compare_prices_ignores_unknown_price(self):
        old = Deal("iPad", "請查看官網", "https://example.test/ipad", "測試")
        new = Deal("iPad", "$20,000", "https://example.test/ipad", "測試")
        self.assertEqual(compare_prices([new], [old]), [])

    def test_categorize_from_product_url(self):
        food = Deal(
            "咖啡",
            "$1",
            "https://www.costco.com.tw/Food-Dining/Drinks/Coffee/p/1",
            "測試",
        )
        laptop = Deal(
            "MacBook",
            "$2",
            "https://www.costco.com.tw/Digital-Mobile/Computers/p/2",
            "測試",
        )
        self.assertEqual(categorize(food), "食品飲料")
        self.assertEqual(categorize(laptop), "家電 3C")

    def test_categorize_unknown_as_other(self):
        deal = Deal("活動商品", "$1", "https://www.costco.com.tw/c/item/p/3", "測試")
        self.assertEqual(categorize(deal), "其他")


if __name__ == "__main__":
    unittest.main()
