import tempfile
import unittest
from pathlib import Path

from src.main import (
    Deal,
    compare_deals,
    deduplicate,
    find_watchlist_matches,
    load_deals,
    load_keywords,
    parse_products,
    write_csv,
)


SAMPLE_HTML = """
<div class="product-item">
  <a class="name" href="/Food/p/123">科克蘭測試商品</a>
  <span class="price">$1,299</span>
</div>
"""


class CostcoDealsTest(unittest.TestCase):
    def test_parse_product(self):
        deals = parse_products(SAMPLE_HTML, "https://example.test/deals")
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].name, "科克蘭測試商品")
        self.assertEqual(deals[0].price, "$1,299")
        self.assertEqual(deals[0].url, "https://www.costco.com.tw/Food/p/123")

    def test_deduplicate_by_url(self):
        deal = parse_products(SAMPLE_HTML, "https://example.test/deals")[0]
        self.assertEqual(len(deduplicate([deal, deal])), 1)

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


if __name__ == "__main__":
    unittest.main()
