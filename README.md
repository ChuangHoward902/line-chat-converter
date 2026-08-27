# LINE 聊天記錄轉換器

把 LINE 匯出的聊天文字與從 Android 手機複製的 `messages` 快取資料夾，整理成可離線開啟的聊天頁面。輸出結果包含 `chat.html`、已配對的照片、影片、語音檔，以及媒體配對報告。

> 本工具只在電腦本機處理資料，不會上傳聊天內容或媒體檔案。

## 功能

- 讀取 LINE 匯出的 `.txt` 聊天記錄。
- 讀取無副檔名的照片、影片與語音快取，依檔案內容辨識格式。
- 產生可直接以瀏覽器開啟的 `chat.html`。
- 自動複製已配對媒體到輸出資料夾，不會修改手機或來源資料夾。
- 輸出 `媒體配對報告.txt`，列出配對方式、未配對訊息與未使用快取。
- 可從程式開啟已連線 Android 手機中的 LINE `chats` 資料夾。

## 使用方式

1. 手機解鎖後以 USB 連接電腦，並選擇「檔案傳輸」。
2. 在 Windows 檔案總管找到：

   ```text
   Android\data\jp.naver.line.android\files\chats
   ```

3. 將要處理聊天室中的 `messages` 資料夾複製到電腦。
4. 從 LINE 匯出同一聊天室的文字記錄 `.txt`。
5. 開啟程式，依序選擇：聊天文字檔、複製到電腦的 `messages` 資料夾、輸出資料夾。
6. 開啟輸出資料夾內的 `chat.html`。

### 操作示範

![LINE 聊天記錄轉換器操作示範](docs/使用教學.gif)

## Windows 版本

到本專案的 **Releases** 下載 `LINE聊天記錄轉換器-Windows-x64.zip`，完整解壓縮後執行：

```text
LINE聊天記錄轉換器\LINE聊天記錄轉換器.exe
```

請勿只移動 `.exe`；它必須與同層的 `_internal` 資料夾放在一起。

Windows 可能因為程式尚未有數位簽章而顯示 SmartScreen 警告。請只從本專案的 Release 下載，並可自行檢查原始碼後再執行。

## 資料與配對限制

LINE 快取不是完整聊天備份。媒體可能因過期、清除快取或尚未下載而不存在。檔案的 Windows 修改時間通常是快取寫入時間，不能當作精準的訊息發送時間。

本工具優先使用相同分鐘的時間證據；必要時才使用同日數量相符或檔名順序推定。沒有足夠證據時，會保留 `[照片]`、`[影片]` 或 `[語音訊息]`，不會隨意放入不確定的媒體。請以 `媒體配對報告.txt` 檢查結果。

## 從原始碼執行

需要 Windows 與 Python 3.11 以上：

```powershell
python line_chat_converter.py
```

執行測試：

```powershell
python -m unittest -v test_line_chat_converter.py
```

## 隱私提醒

請不要把自己的聊天文字、`messages` 快取資料夾、輸出的 HTML 或媒體資料夾上傳到 GitHub。這些檔案可能包含私人訊息、照片、語音與聯絡人資訊。

## 授權

本專案採用 [MIT License](LICENSE)。
