Если прежняя позиция строки была далеко внизу за пределами таблицы, анимация подъёма начинается с нижней видимой строки. Это убирает слишком быстрый пролёт через скрытую часть списка. Длительность остаётся **150 мс**, перемещения внутри видимой области и подсветка названия сохранены.

**Обновление:** замените `V2Lens.exe` рядом с `v2rayN.exe`, сохранив `V2Lens-data`. Windows 10/11 x64, WebView2 Runtime. Python и Node.js для готового EXE не нужны.

---

Rows promoted from below the visible table now start their animation at the bottom visible row instead of racing through the hidden list. Movement still takes **150 ms**; visible-row movement and name highlighting are preserved.

Replace `V2Lens.exe` beside `v2rayN.exe` and keep `V2Lens-data`.
