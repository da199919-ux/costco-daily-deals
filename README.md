# Costco 台灣每日優惠清單

這是第一版自動整理工具。它每天讀取 Costco 台灣官方線上優惠頁，去除重複商品，
並產生一份容易閱讀的 Markdown 清單與可用試算表開啟的 CSV。

## 目前範圍

- 資料來源只使用 Costco 台灣官方公開頁面。
- 收錄官方線上優惠，不保證包含各實體賣場當天臨時降價。
- 每天台灣時間早上 7:00 由 GitHub Actions 自動更新。
- 輸出位置是 `output/latest.md` 與 `output/latest.csv`。

## 第一次在 Mac 執行

打開「終端機」，進入這個專案資料夾後，依序貼上：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m src.main
```

成功時會看到「完成：N 項優惠」。接著打開 `output/latest.md` 就能閱讀。

## 測試

```bash
source .venv/bin/activate
python3 -m unittest discover -s tests
```

## 放上 GitHub 後開啟每日更新

1. 使用 GitHub Desktop 登入。
2. 選擇 **File → Add Local Repository**，加入此資料夾。
3. 按 **Publish repository**。建議先設為 Private。
4. 到 GitHub 網頁的專案頁，打開 **Actions**。
5. 選擇「每日更新 Costco 優惠」，按 **Run workflow** 測試一次。

GitHub 的排程可能不會準點到秒，通常會在設定時間附近開始執行。

