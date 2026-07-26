# Costco 台灣每日優惠清單

這是每日自動整理工具。它每天讀取 Costco 台灣官方線上優惠頁，去除重複商品，
並產生容易閱讀的清單、今日變化摘要與歷史 CSV。

## 目前範圍

- 資料來源只使用 Costco 台灣官方公開頁面。
- 收錄官方線上優惠，不保證包含各實體賣場當天臨時降價。
- 每天台灣時間早上 7:00 由 GitHub Actions 自動更新。
- 輸出位置是 `output/latest.md` 與 `output/latest.csv`。
- 自動列出今日新增，以及已結束或不在清單的優惠。
- 每日紀錄保存在 `output/history/年-月-日.csv`。
- 精簡摘要保存在 `output/summary.md`，並透過 GitHub Issues 發送 Gmail 通知。
- `watchlist.txt` 可設定常買商品或品牌，符合的優惠會顯示在摘要最上方。

## 修改追蹤商品

用 VS Code 打開 `watchlist.txt`，每行輸入一個商品或品牌關鍵字。英文大小寫不影響搜尋。
儲存後再使用 GitHub Desktop Commit 與 Push，下一次每日更新就會採用新清單。

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
