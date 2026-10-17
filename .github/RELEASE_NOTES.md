**TUN / Without TUN** теперь редактируются отдельно: каждый шаблон сохраняется в своё поле v2rayN и проверяется штатным Xray. Переключение сохраняет черновик, отмену изменений и свёрнутые блоки каждого режима. Пустой шаблон остаётся пустым — используются настройки v2rayN по умолчанию.

Окно можно менять за края и углы. **Auto-reload v2rayN** перезагружает только текущий режим; сохранение второго шаблона не включает и не выключает TUN.

**Установка / обновление:** положите `V2Lens.exe` рядом с `v2rayN.exe`, заменив предыдущую версию после её закрытия. Папку `V2Lens-data` оставьте для сохранения настроек. Python и Node.js не нужны.

Windows 10/11 x64, WebView2 Runtime. Проверено с v2rayN 7.25.6 / Xray 26.9.9. EXE запрашивает права администратора. Для Connections нужна запись access-журнала Xray в файл. Контрольные суммы — в `SHA256SUMS.txt`; инструкции и лицензии — в ZIP.

---

Separate **TUN / Without TUN** templates with independent Xray validation, saves, drafts, undo and persistent folds. The window now resizes from every edge and corner. Auto-reload affects only the active mode; selecting a template does not toggle TUN.

Place `V2Lens.exe` beside `v2rayN.exe`. When upgrading, close the old version and replace the EXE; keep `V2Lens-data`. Windows 10/11 x64 and WebView2 are required. No Python or Node.js installation needed.
