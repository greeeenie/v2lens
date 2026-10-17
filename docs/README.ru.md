<p align="center"><img src="brand/v2lens.png" width="80" alt="V2Lens"></p>
<h1 align="center">V2Lens</h1>
<p align="center"><a href="../README.md">English</a> · <b>Русский</b></p>
<p align="center">Минималистичный просмотр соединений Xray и редактор TUN-шаблона v2rayN.</p>

**[Скачать для Windows x64](https://github.com/greeeenie/v2lens/releases/latest)**

![Соединения — демонстрационные данные](screenshots/connections.png)

### Как запустить

1. Положи **V2Lens.exe рядом с v2rayN.exe** и запусти обе программы.
2. Подтверди запрос администратора — это нужно для Reload клиента v2rayN с повышенными правами.
3. Включи в v2rayN **запись access-журнала Xray в файл**, чтобы появились соединения.

**Нужно:** Windows 10/11 x64 и [WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/). Проверено с v2rayN **7.25.6** / Xray **26.9.9**. Для готового EXE Python и Node.js не нужны.

### Возможности

- **Connections:** приложение → соединения с PID, протоколом, адресом, скоростью, **Gateway (TUN / SOCKS)** и **Route (Proxy / Direct)**. Поиск, сортировка и группировка; промежуточных строк PID нет.
- **[Template](screenshots/template.png):** подсветка JSON, сохранение свёрнутости, Format, Expand all и **+** с определением типа. Save проверяет конфиг штатным Xray; галочка **Auto-reload v2rayN** применяет сохранённый шаблон.
- **Переносимость:** настройки в `V2Lens-data` рядом с EXE, при необходимости — в `%LOCALAPPDATA%\V2Lens`. Серверы, подписки и личные журналы в сборку не входят.

Template редактирует включённый **Full Config Template → Xray TUN template**, а не обычные routing profiles. Авторелоад по умолчанию выключен. Журнал показывает решения Xray; соединения в обход него могут отсутствовать.

<details><summary>Сборка из исходников</summary>

Windows x64, Python 3.12, Node.js 22+, компилятор .NET Framework 4.x и WebView2:

```powershell
python -m pip install -e ".[build]"
npm ci --prefix frontend
npm run build --prefix frontend
python -m unittest discover -s tests
node frontend/test.mjs
node frontend/connections.test.mjs
python scripts/build.py
```

Результат — в `dist/`. Код приложения — в `src/v2lens/`, редактор — в `frontend/`, сборка — в `scripts/`, ETW-помощник — в `native/`, проверки — в `tests/`. Запуск исходников: `python -m v2lens --v2ray-dir "D:\Apps\v2rayN"`. GitHub Actions проверяет сборку при push; тег `vX.Y.Z`, совпадающий с версией в `pyproject.toml`, публикует релиз.

</details>

[Лицензия MIT](../LICENSE) · [Изменения](../CHANGELOG.md) · Используются [v2rayN](https://github.com/2dust/v2rayN), [Xray](https://github.com/XTLS/Xray-core), CodeMirror, pywebview и TraceEvent. Самостоятельный проект; лицензии сторонних компонентов включены в ZIP.
