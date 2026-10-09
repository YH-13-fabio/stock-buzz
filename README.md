# 股市討論熱度 Dashboard

每天自動爬 PTT Stock 板、你指定的 YouTube 頻道（Dcard 為實驗性選項），統計每檔股票被提到幾次、看多還是看空，做成今日／本週排行網頁。
設定永豐金 Shioaji API 後，還會顯示被討論股票的收盤價、漲跌、均線、RSI、KD、MACD，並把股價走勢和討論熱度放在同一條時間軸上比較。

整套放在 GitHub 上免費運作：

- **GitHub Actions** 每天晚上 11 點自動執行爬蟲
- 結果存回你的 repo（`data/buzz.db`）
- **GitHub Pages** 把 `docs/` 資料夾變成網站，網址是 `https://你的帳號.github.io/stock-buzz/`

---

## 先認識 5 個名詞

| 名詞 | 白話解釋 |
|---|---|
| **Repository（repo）** | 一個專案資料夾，放在 GitHub 雲端 |
| **Commit** | 「存檔」。每次修改檔案後按 Commit，GitHub 會記住這一版，隨時可以回到舊版 |
| **Actions** | GitHub 幫你免費跑程式的機器，可以設定每天定時執行 |
| **Secrets** | 存放密碼／金鑰的保險箱，程式讀得到，但別人（包括看你 repo 的人）看不到 |
| **Pages** | 把 repo 裡的網頁檔變成一個公開網站 |

---

## 第一次設定（約 20 分鐘）

### 步驟 1：註冊 GitHub

到 <https://github.com/signup> 用 email 註冊，記住你的帳號名稱（之後網址會用到）。

### 步驟 2：建立 repository

1. 登入後點右上角 **＋** → **New repository**
2. **Repository name** 填 `stock-buzz`
3. 選 **Public**（免費帳號的 Pages 網站需要 Public；放的是公開論壇資料，金鑰會放在 Secrets 不會外洩）
4. 勾選 **Add a README file**
5. 按 **Create repository**

### 步驟 3：上傳程式檔案

1. 把收到的 `stock-buzz.zip` 解壓縮
2. 在 repo 頁面點 **Add file** → **Upload files**
3. 打開解壓縮後的 `stock-buzz` 資料夾，**把裡面所有東西**（`buzz`、`data`、`docs` 資料夾，以及 `main.py`、`config.yaml`、`requirements.txt`、`README.md` 等檔案）一起拖進網頁
   - 是拖「資料夾裡面的東西」，不是拖整個 `stock-buzz` 資料夾
   - 會問 README 要不要覆蓋，直接覆蓋即可
4. 最下面按 **Commit changes**

### 步驟 4：建立自動排程檔（重要，最容易漏掉）

`.github` 這個資料夾名稱開頭有個點，Mac 預設會隱藏，拖曳時常常沒傳上去，所以直接在網頁上建立：

1. 在 repo 頁面點 **Add file** → **Create new file**
2. 檔名欄位輸入：`.github/workflows/daily.yml`
   （打到 `/` 時 GitHub 會自動變成資料夾，這是正常的）
3. 用記事本打開解壓縮資料夾裡的 `.github/workflows/daily.yml`，全部複製貼到網頁的內容區
   - Mac 看不到這個檔案的話，在 Finder 按 `Cmd + Shift + .` 就能顯示隱藏檔
4. 按 **Commit changes**

### 步驟 5：申請 YouTube API 金鑰（免費）

1. 到 <https://console.cloud.google.com/> 用 Google 帳號登入
2. 上方選單 **選取專案** → **新增專案**，名稱隨意（例如 stock-buzz）→ 建立
3. 左側選單 **API 和服務** → **程式庫**，搜尋 **YouTube Data API v3** → 按 **啟用**
4. 左側 **憑證** → **建立憑證** → **API 金鑰**，複製產生的那串字

> 免費額度每天 10,000 單位，追蹤一個頻道每天只用 2～3 單位，非常夠用。

### 步驟 6：把金鑰放進 GitHub Secrets

1. 回到 repo，點上方 **Settings**
2. 左側 **Secrets and variables** → **Actions**
3. 按 **New repository secret**
   - Name：`YOUTUBE_API_KEY`
   - Secret：貼上剛剛的金鑰
4. 按 **Add secret**

**（選用）用 Claude 判斷多空會比較準：**
到 <https://console.anthropic.com/> 建立 API Key，用同樣方式新增一個 Secret，Name 填 `ANTHROPIC_API_KEY`。
這是依用量付費的，可以在 Anthropic Console 設定每月花費上限；`config.yaml` 裡的 `max_llm_calls_per_run` 也會限制每次最多呼叫幾次。
不設定的話，程式會自動用免費的關鍵字規則判斷。

### 步驟 6-2：（選用）加上永豐金股價與技術指標

需要永豐金證券帳戶，並已在永豐金網站完成 **API 簽署**。

1. 登入永豐金證券網站，到 API 管理頁面**新增 API Key**，會拿到 **API Key** 和 **Secret Key**
   - **安全建議：如果有權限選項，只勾選「行情／資料」相關權限，不要勾「交易」**。這個程式只讀股價，不會下單，也不需要憑證（CA）檔案
   - Secret Key 通常只顯示一次，請先存好
2. 跟步驟 6 一樣到 **Secrets and variables → Actions** 新增兩個 Secret：
   - `SHIOAJI_API_KEY`：貼上 API Key
   - `SHIOAJI_SECRET_KEY`：貼上 Secret Key
3. 完成。下次執行就會抓最近 7 天被討論最多的 80 檔股票股價

> 說明：
> - Shioaji 只提供 1 分鐘 K 線，程式會自動合成日 K 再計算指標
> - 沒有透過 API 下單過的帳號，每日行情流量上限是 500MB，所以第一次執行每次最多替 25 檔股票補 150 天歷史，**大約 3～4 天後所有股票的均線和指標才會完整**；之後每天只補一天，流量很小
> - 每次登入用完會立刻登出，不會佔用你的連線數
> - Secrets 是加密儲存的，repo 設成 Public 別人也看不到金鑰

### 步驟 7：開啟網站（GitHub Pages）

1. **Settings** → 左側 **Pages**
2. **Source** 選 **Deploy from a branch**
3. **Branch** 選 `main`，旁邊資料夾選 `/docs` → **Save**
4. 等 1～2 分鐘，頁面上方會出現網址：`https://你的帳號.github.io/stock-buzz/`

### 步驟 8：手動跑第一次

1. 點上方 **Actions**
   - 如果看到「Workflows aren't being run on this repository」之類的提示，按綠色按鈕啟用
2. 左側點 **每日爬取股票討論**
3. 右邊按 **Run workflow** → 再按綠色的 **Run workflow**
4. 等 3～10 分鐘，出現綠色勾勾 ✅ 就完成了
5. 打開步驟 7 的網址，就能看到 Dashboard 了（若還是空的，等 1 分鐘重新整理）

之後每天台灣時間晚上 11 點左右會自動執行，不用再管它。

---

## 日常操作

### 新增或修改 YouTube 頻道

1. 在 repo 點 `config.yaml`
2. 右上角 **鉛筆圖示** 進入編輯
3. 修改 `channels:` 底下的清單，例如：
   ```yaml
   channels:
     - "@yutinghao"
     - "@另一個頻道"
     - "https://www.youtube.com/@第三個頻道"
   ```
4. 按 **Commit changes** 存檔，下次執行就會生效

`config.yaml` 裡還可以調整：要爬哪些 PTT 看板、要不要算推文、要不要開 Dcard 等，每一項都有中文說明。

### 新增股票暱稱

鄉民常用暱稱（例如「GG」＝台積電、「海公公」＝鴻海）放在 `data/aliases.csv`，一行一個，格式是 `暱稱,股票代號`，用同樣的鉛筆圖示編輯即可。

### 看執行紀錄／出錯時

**Actions** 頁面每一次執行都有紀錄：

- ✅ 綠色：成功
- ❌ 紅色：失敗，點進去 → 點 **crawl** → 展開出錯的步驟，就能看到錯誤訊息（可以直接複製貼給 Claude 問）

| 狀況 | 解法 |
|---|---|
| 「儲存結果」步驟出現 `Permission denied` 或 `403` | **Settings** → **Actions** → **General** → 最下面 **Workflow permissions** 選 **Read and write permissions** → Save |
| PTT 一直顯示「讀取列表失敗」 | PTT 偶爾會擋國外雲端主機，可改在自己電腦執行（見下方） |
| YouTube 顯示「無法取得字幕」 | YouTube 常擋雲端主機抓字幕，程式會自動改用標題＋影片說明分析，不影響其他功能 |
| 「[股價] Shioaji 登入失敗」 | 確認兩個金鑰沒有貼錯或多了空白、帳戶已完成 API 簽署；若訊息含 `Sign data is timeout` 通常重跑一次即可。永豐的連線若擋國外主機，請改在自己電腦執行 |
| 部分股票沒有均線／指標 | 新股票正在分批補歷史資料，過幾天就會補齊 |
| 排程好一陣子沒有自動跑 | 到 **Actions** 頁面看是否被停用，按 **Enable workflow** 重新啟用 |

---

## 進階：在自己電腦執行

需要先安裝 Python 3.10 以上（<https://www.python.org/downloads/>，Windows 安裝時記得勾選 **Add Python to PATH**）。

```bash
cd stock-buzz
pip install -r requirements.txt
pip install shioaji

# Mac / Linux
export YOUTUBE_API_KEY="你的金鑰"
export SHIOAJI_API_KEY="永豐 API Key"
export SHIOAJI_SECRET_KEY="永豐 Secret Key"
# Windows（PowerShell）
$env:YOUTUBE_API_KEY="你的金鑰"
$env:SHIOAJI_API_KEY="永豐 API Key"
$env:SHIOAJI_SECRET_KEY="永豐 Secret Key"

python main.py
```

執行完後，用以下指令開啟網頁預覽，再用瀏覽器打開 <http://localhost:8000>：

```bash
cd docs
python -m http.server 8000
```

---

## 專案結構

```
stock-buzz/
├── main.py                 主程式（爬文 → 辨識 → 多空判斷 → 存檔 → 產生網頁資料）
├── config.yaml             設定檔（頻道、看板、開關）
├── requirements.txt        需要的 Python 套件
├── buzz/
│   ├── ptt.py              PTT 爬蟲
│   ├── youtube.py          YouTube 新影片＋字幕
│   ├── dcard.py            Dcard（實驗性）
│   ├── stocks.py           上市櫃股票清單＋辨識文章提到哪些股票
│   ├── sentiment.py        多空判斷（關鍵字規則／Claude）
│   ├── prices.py           永豐 Shioaji 股價（1 分 K 合成日 K）
│   ├── indicators.py       均線、RSI、KD、MACD
│   ├── db.py               SQLite 資料庫
│   └── site.py             產生 docs/data.json
├── data/
│   ├── aliases.csv         股票暱稱
│   ├── stocks_fallback.csv 抓不到官方清單時的備用清單
│   └── buzz.db             歷史資料（自動產生）
├── docs/
│   ├── index.html          Dashboard 網頁
│   └── data.json           網頁讀取的資料（自動產生）
└── .github/workflows/
    └── daily.yml           每日排程設定
```

## 計算方式

- **提及次數**：一篇文章或一部影片對同一檔股票只算 1 次；PTT 每則推文分開計算，在網頁上歸類為「PTT推文」，可以用上方按鈕切換要不要納入
- **股票辨識**：比對證交所／櫃買中心的上市櫃名稱、4 碼代號、ETF 代號與 `aliases.csv` 暱稱；代號後面接「元、年、張、點」等字的不算（避免把價格當代號）；名稱容易跟日常用語撞到的（如「統一」）只認代號
- **多空**：PTT `[標的]` 文直接採用作者標示的多／空；其他內容看提到股票的那一句有沒有多空關鍵字（「不會漲」會反轉）；有設定 Claude 金鑰時改由 Claude 判斷整篇
- **技術指標**：MA5／20／60 簡單均線；RSI(14) 採 Wilder 平滑；KD(9,3,3)；MACD(12,26,9)。訊號標籤（站上月線、KD 黃金交叉、爆量等）只是指標狀態的描述
- 一篇提到超過 8 檔股票的（通常是盤後整理文）略過不計，可在 `config.yaml` 調整

> 多空為程式自動判斷，只反映討論氣氛，不構成投資建議。請遵守各平台使用條款，維持低頻率爬取。
