import tempfile
import unittest
from pathlib import Path

import requests

from src.main import (
    Deal,
    add_multibuy_promotion,
    categorize,
    collect_source,
    compare_deals,
    compare_prices,
    deduplicate,
    enrich_product_details,
    find_watchlist_matches,
    load_deals,
    load_keywords,
    parse_products,
    parse_product_detail,
    parse_voucher_products,
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

RESPONSIVE_DISCOUNT_HTML = """
<div class="product-item">
  <a class="name" href="/Furniture-Kitchen/p/111136">
    3M 新絲舒眠單人涼透被
  </a>
  <div class="price">$2,499</div>
  <div class="mobile-price">$1,999</div>
  <div class="discount-message">商品已折價 $500</div>
</div>
"""

LISTING_WITH_RECOMMENDATION_HTML = """
<main>
  <div class="product__listing">
    <div class="product-item">
      <a class="name" href="/Furniture-Kitchen/p/100">活動涼感商品</a>
      <span class="price">$1,000</span>
    </div>
  </div>
  <section class="recommendations">
    <div class="product-item">
      <a class="name" href="/Health-Beauty/p/200">推薦維生素商品</a>
      <span class="price">$279</span>
    </div>
  </section>
</main>
"""

DETAIL_HTML = """
<main>
  <div class="product-price">$925</div>
  <div class="price-panel">
    <span>商品原價 $1,159</span>
    <span>商品已折價 $234</span>
  </div>
</main>
"""

SUBTOTAL_DETAIL_HTML = """
<main>
  <div>商品原價 <span>$479</span></div>
  <div>商品折扣 <span>- $100</span></div>
  <div>小計 <span>$379</span></div>
</main>
"""

LOWER_PRICE_DETAIL_HTML = """
<main>
  <div>商品原價 <span>$399</span></div>
  <div>該商品前次原價為 $469</div>
</main>
"""

VOUCHER_HTML = """
<sip-product-carousel-item>
  <div class="custom-card">
    <span>$379</span>
    <span>商品已折價 $100</span>
    <a href="/Furniture-Kitchen/p/8524812">
      三麗鷗 兒童不鏽鋼保冷保溫瓶 700毫升
    </a>
    <img src="/medias/sanrio.jpg">
  </div>
</sip-product-carousel-item>
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

    def test_deduplicate_prefers_discounted_price(self):
        regular = Deal(
            "三麗鷗保溫瓶",
            "$479",
            "https://example.test/p/8524812",
            "一般清單",
        )
        discounted = Deal(
            "三麗鷗保溫瓶",
            "$379",
            "https://example.test/p/8524812",
            "優惠券",
            original_price="$479",
            discount_amount="$100",
            promotion="商品已折價 $100",
        )
        result = deduplicate([regular, discounted])[0]
        self.assertEqual(result.price, "$379")
        self.assertEqual(result.original_price, "$479")
        self.assertEqual(result.discount_amount, "$100")

    def test_parse_discount_and_calculate_original_price(self):
        deal = parse_products(DISCOUNT_HTML, "https://example.test/deals")[0]
        self.assertEqual(deal.price, "$925")
        self.assertEqual(deal.discount_amount, "$234")
        self.assertEqual(deal.original_price, "$1,159")

    def test_parse_responsive_card_discount_outside_price_panel(self):
        deal = parse_products(
            RESPONSIVE_DISCOUNT_HTML, "https://example.test/deals"
        )[0]
        self.assertEqual(deal.price, "$1,999")
        self.assertEqual(deal.discount_amount, "$500")
        self.assertEqual(deal.original_price, "$2,499")

    def test_parse_products_excludes_recommendation_cards(self):
        deals = parse_products(
            LISTING_WITH_RECOMMENDATION_HTML,
            "https://www.costco.com.tw/c/Hero_Cool",
        )
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].name, "活動涼感商品")

    def test_parse_product_detail_adds_discount_information(self):
        deal = Deal(
            "詳細頁折價商品",
            "$925",
            "https://www.costco.com.tw/Food/p/456",
            "測試",
        )
        updated = parse_product_detail(DETAIL_HTML, deal)
        self.assertEqual(updated.price, "$925")
        self.assertEqual(updated.original_price, "$1,159")
        self.assertEqual(updated.discount_amount, "$234")

    def test_parse_product_detail_uses_discounted_subtotal_as_price(self):
        deal = Deal(
            "三麗鷗保溫瓶",
            "$479",
            "https://www.costco.com.tw/p/8524812",
            "測試",
        )
        updated = parse_product_detail(SUBTOTAL_DETAIL_HTML, deal)
        self.assertEqual(updated.original_price, "$479")
        self.assertEqual(updated.discount_amount, "$100")
        self.assertEqual(updated.price, "$379")

    def test_parse_product_detail_uses_previous_price_for_savings(self):
        deal = Deal(
            "亨氏濃湯",
            "$399",
            "https://www.costco.com.tw/p/150603",
            "測試",
        )
        updated = parse_product_detail(LOWER_PRICE_DETAIL_HTML, deal)
        self.assertEqual(updated.original_price, "$469")
        self.assertEqual(updated.discount_amount, "$70")
        self.assertEqual(updated.price, "$399")
        self.assertIn("優惠售價", updated.promotion)

    def test_parse_voucher_custom_product_card(self):
        deals = parse_voucher_products(
            VOUCHER_HTML, "https://www.costco.com.tw/voucher4"
        )
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].price, "$379")
        self.assertEqual(deals[0].original_price, "$479")
        self.assertEqual(deals[0].discount_amount, "$100")

    def test_multibuy_promotion_keeps_official_displayed_price(self):
        deal = Deal(
            "涼感商品",
            "$2,499",
            "https://example.test/cool",
            "測試",
        )
        updated = add_multibuy_promotion(
            deal, "https://www.costco.com.tw/voucher4"
        )
        self.assertEqual(updated.price, "$2,499")
        self.assertEqual(updated.original_price, "")
        self.assertEqual(updated.discount_amount, "")
        self.assertIn("買2件享8.5折", updated.promotion)
        self.assertIn("買3件享8折", updated.promotion)
        self.assertIn("結帳時依活動條件計算", updated.promotion)

    def test_general_cool_page_does_not_assume_multibuy_discount(self):
        deal = Deal(
            "非指定商品",
            "$279",
            "https://example.test/not-designated",
            "測試",
        )
        updated = add_multibuy_promotion(
            deal, "https://www.costco.com.tw/c/Hero_Cool"
        )
        self.assertEqual(updated, deal)
        self.assertNotIn("買2件享8.5折", updated.promotion)

    def test_multibuy_does_not_replace_fixed_discount(self):
        deal = Deal(
            "三麗鷗保溫瓶",
            "$379",
            "https://example.test/bottle",
            "測試",
            original_price="$479",
            discount_amount="$100",
            promotion="商品已折價 $100",
        )
        updated = add_multibuy_promotion(
            deal, "https://www.costco.com.tw/voucher4"
        )
        self.assertEqual(updated.price, "$379")
        self.assertEqual(updated.original_price, "$479")
        self.assertEqual(updated.discount_amount, "$100")
        self.assertIn("商品已折價 $100", updated.promotion)
        self.assertIn("買2件享8.5折", updated.promotion)

    def test_furniture_promotion_keeps_displayed_price(self):
        deal = Deal(
            "家具商品",
            "$10,000",
            "https://example.test/furniture",
            "測試",
        )
        updated = add_multibuy_promotion(
            deal, "https://www.costco.com.tw/voucher2"
        )
        self.assertEqual(updated.price, "$10,000")
        self.assertEqual(updated.original_price, "")
        self.assertEqual(updated.discount_amount, "")
        self.assertIn("2026/07/20-08/02", updated.promotion)
        self.assertIn("買1件享85折，買2件享8折", updated.promotion)

    def test_enrich_product_details_keeps_failed_product(self):
        good = Deal("成功商品", "$925", "https://example.test/good", "測試")
        failed = Deal("失敗商品", "$100", "https://example.test/fail", "測試")

        def fake_fetch(url):
            if url.endswith("/fail"):
                raise requests.RequestException("測試失敗")
            return DETAIL_HTML

        deals, pages_read = enrich_product_details(
            [good, failed], fetcher=fake_fetch, workers=2
        )
        self.assertEqual(pages_read, 1)
        self.assertEqual(deals[0].original_price, "$1,159")
        self.assertEqual(deals[1], failed)

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
