import unittest

from src.main import deduplicate, parse_products


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


if __name__ == "__main__":
    unittest.main()

