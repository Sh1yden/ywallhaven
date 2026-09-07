# Changelog

Все значимые изменения в проекте будут документироваться в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/),
и этот проект придерживается [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

### Планируется

- [x] Фикс фильтра relevance.
- [x] Скрытие range toplist пока не выбран этот фильтр.
- [x] Исправление page, short в right_panel.
- [x] Исправление размера кнопки download.
- [x] Полноценная панель настроек: тема, API-ключ, мода, уровень
  лога, порт, флаги обновлений (сохранение в config.json).
- [x] Тема оформления: переключатель тёмная/светлая.
- [x] Фуллскрин: дублирующее превью в углу (единый фон слоёв).
- [x] Выбор разрешения при отсутствии dimension в поиске
  (дозапрос деталей).
- [x] Надёжные уведомления о скачивании / отмене / ошибке.
- [x] Уведомления о проверке обновлений переведены на SnackBar.
- [x] Реальная логика в `cleanup()` (закрытие клиентов, чистка
  temp-файлов апдейта, ротация лога апдейтера).
- [x] Тесты апдейтера и `WallhavenAPI` (моки httpx).
- [x] Наполнение `README.md`
- [x] fix LICENSE.
- [x] Auto Update btn & file
- [x] Убрать поле API-ключа из левой панели (ключ вводится только
  в настройках).
- [x] Разблокировка NSFW/Sketchy сразу после ввода ключа
  в настройках, без перезапуска.
- [x] Теги у NSFW-обоев (передача `apikey` в запрос деталей).
- [x] Сделать красивое оформление приложения
    - [x] Система заготовленных тем (9 builtin: dark_default, light_default, midnight, forest, ocean, sunset, arctic, kanagawa_wave, kanagawa_lotus из rebelot/kanagawa.nvim)
    - [x] Система собственных тем (пользовательских) в определённом формате (themes/*.json, гибрид seed+colors, import через UI)
- [x] Улучшить внешний вид приложения (C3 редизайн: header Card, surface tokens, responsive grid, skeleton, empty states, chips)
- [x] Fix updater'a(логи при его запуске чек)
- [x] Изменить иконку собранного exe на свою
- [x] Изменить иконку запущенного приложения со стандартной на свою
- [x] Добавить закрытие всплывающих меню по клику вне его(исключительно меню скачки картинки, когда выбираешь его разрешения)
- [x] Исправить размеры предпросмотра картинок в левой панели, + в мидл панели
- [x] Получше залогировать приложение

## [0.9.0] - 2026-09-07

### Добавлено

- Кэш деталей обоев (LRU, 256) в `WallhavenAPI.get_wallpaper`
  (`wallhaven_api.py`): теги уже открытых обоев рендерятся мгновенно,
  без повторного запроса; transient-retry 429/502/503/504 в запросе
  деталей; кэш сбрасывается при смене API-ключа.
- Предзагрузка следующей страницы галереи (`middle_panel.py`):
  `_prefetch_next_page` тянет страницу в фоне, скролл к низу берёт её
  из кэша; анти-дубль через флаг `_load_wanted` вместо спама retry-тасков.
- Превью в правой панели показывает миниатюру мгновенно через
  `placeholder_src` + `gapless_playback` (`right_panel.py`).
- Тайминги в логи (DEBUG): рендер страницы галереи, сборка UI, рендер
  превью.
- Тесты кэша деталей и пагинационного кэша (`test_wallhaven_api.py`,
  `test_middle_panel.py`).

### Изменено

- Меню выбора разрешения закрывается по клику вне: не-модальный
  `AlertDialog` + прозрачный барьер в `page.overlay` (`right_panel.py`).
- Тайлы галереи широкие (`child_aspect_ratio = 16/9`) вместо квадратных —
  миниатюры 16:9 кропаются меньше, без серых полос снизу.
- Иконки: `scripts/build.py` генерирует `assets/icon.ico` из `icon.png`;
  `ywallhaven.spec` — `icon=` для exe и `.ico` в данных; `page.window.icon`
  ставит иконку окна приложения (`flet_app.py`).
- `assets/icon.ico` добавлен в `.gitignore` (артефакт сборки).

### Исправлено

- Теги долго подгружались или не появлялись при троттлинге Wallhaven —
  кэш деталей и ретраи устраняют повторяющиеся запросы.

## [0.8.9] - 2026-09-06

### Исправлено

- `unknown control: FilePicker` и `TimeoutException FilePicker.save_file` (`flet_app.py:88`, `app/main.py:108`): `FilePicker` в `flet==0.86.4` — `Service`, а не `control`, регистрация через `page._services` (`service.py:16`), `page.overlay.append` даёт `unknown control`. Пикеры больше не в `page.overlay`, регистрация через `_bind_file_pickers` с пиннингом `page._ywallhaven_file_picker/_theme_picker` (2 сильные ссылки против `unregister_services` GC). Откачен `AppView.WEB_BROWSER` → `AppView.FLET_APP` (`app/main.py:108`).

## [0.8.8] - 2026-09-06

### Исправлено

- Роллинг обоев ломался: `middle_panel` `load_more` (`middle_panel.py:110`) `502 Bad Gateway` (`wallhaven_api.py:88`) маскировался как `No more wallpapers found` → `has_more=False` и пустая сетка. `wallhaven_api` теперь пробрасывает `429/502/503/504` как `raise` (warning `Transient`), `middle_panel` ретрай `page.run_task(_retry_with_delay 1.0)` без `has_more=False`.
- Превью миниатюр `middle_panel.py:182` теперь `Image(error_content=Icon(BROKEN_IMAGE))` fallback при `th.wallhaven.cc` `statusCode 0`.

## [0.8.7] - 2026-09-06

### Исправлено

- Скачивание падало `TimeoutException FilePicker(9).save_file` + `Image has no attribute 'LANCZOS'` (`flet_app.py:308`, `136`): `Pillow 11` удалил `Image.LANCZOS` → `Resampling.LANCZOS`, `FilePicker` один на `save_file`+`pick_files` давал таймаут 10с при конкурентном `invokeMethod`. Возвращены 2 `FilePicker` (`file_picker` для `save_file`, `theme_picker` для `pick_files`), оба `page.overlay.append` до `page.add` (как до `0.8.4` когда `save` работал), без `unknown control`.

## [0.8.6] - 2026-09-06

### Исправлено

- Улучшена логируемость `FilePicker` и отлов `unknown control: FilePicker` там, где он используется (по запросу): `flet_app.py:241` создание `FilePicker()` + `page.overlay.append` с логом `flet_version`/`overlay before/after`/`uid` и `exc_info`, `flet_app.py:220` `on_page_error` с проверкой `FilePicker`/`unknown control` и логом `overlay`+`exc_info`, `flet_app.py:304` `save_file` и `settings.py:237` `pick_files` с логом `overlay`/`web` и `exc_info` до/после вызова.

## [0.8.5] - 2026-09-06

### Исправлено

- `themes` не создавалась во frozen-сборке (`loader.py:_theme_dir`): приоритет `cwd → MEIPASS → exe.parent` ставил `_MEIPASS/themes` (вшит, всегда существует) впереди `exe.parent/themes`, импорты писались в temp extraction и терялись. Приоритет изменён `exe.parent → cwd → repo → MEIPASS`, добавлен `_seed_examples` копирование `README/.example` в пустую папку, лог `Themes dir`.
- Автоочистка повреждённого кэша Flet клиента (`flet_app.py:_log_flet_client_diagnostics` → автоочистка A): при пустой папке или отсутствии `*.exe`/`flet*` внутри `~/.flet/client/flet-desktop-*-0.86.4` кэш удаляется и перекачивается, иначе только лог (без удаления здорового 30МБ).

## [0.8.4] - 2026-09-06

### Исправлено

- `unknown control: FilePicker` поверх левой панели (`settings.py:64`, `flet_app.py:192`): `SettingsPanel` держал отдельный `_theme_picker` с `did_mount` → `page.overlay.append` после `page.add`, клиент получал 2 `FilePicker` сервиса (`FilePicker(9)` + `10`) → `unknown control`. Оставлен **один** `FilePicker` (`file_picker`) для `save_file` и `pick_files`, `SettingsPanel(theme_picker=file_picker)`, `did_mount`/`will_unmount` удалены, убран `import shutil`.

## [0.8.3] - 2026-09-06

### Исправлено

- Апдейтер `WinError 5 Отказано в доступе` при `os.replace` в `C:\Programs\...` (`updater/main.py:155`, `ywallhaven-updater.spec`): `C:\Programs` требует UAC, helper запускался без повышения. Добавлен retry 3× с `chmod 777` + `sleep 0.7` + лог `exists/writable/stat` до `replace`, и `uac_admin=True` в `ywallhaven-updater.spec` (манифест `requireAdministrator`).

## [0.8.2] - 2026-09-06

### Исправлено

- `unknown control: FilePicker` на левой панели (`settings.py:64`, `flet_app.py:192`): `SettingsPanel` создавал `_theme_picker = FilePicker()` и добавлял в `page.overlay` в `did_mount()` (после `page.add`), клиент Flutter не знал сервис. Перенесён в `flet_app._build_ui` — `theme_picker = FilePicker(); page.overlay.append(theme_picker)` до `page.add`, `SettingsPanel(theme_picker=theme_picker)`.

### Изменено

- `themes` примеры сделаны неактивными: `example_ocean.json` → `example_ocean.json.example`, `example_light_paper.json` → `example_light_paper.json.example`; `loader` `glob("*.json")` их не грузит → `Dropdown` только 9 builtin без мусора. `themes/README.md` — подсказка переименовать `*.example` → `*.json`.
- `ywallhaven.spec` — `datas=[('assets/icon.png','assets'),('themes','themes')]` чтобы `README.md` + `.example` попадали в `dist`/`_MEI*`.
- `.gitignore` — `!themes/*.example` вместо `!themes/example_*.json`.

## [0.8.1] - 2026-09-06

### Исправлено

- `FilePicker.__init__() got an unexpected keyword argument 'on_result'` (`app/interface/components/settings.py:64`): `FilePicker` в `flet==0.86.4` не принимает `on_result` в конструкторе, `pick_files` теперь `async` возвращает `list[FilePickerFile]`. Заменено на `FilePicker()` + `await picker.pick_files()` в `SettingsPanel._on_import_theme`/`_handle_theme_files`.
- Апдейтер падал с `Source file missing: ...ywallhaven-0.8.0-update.exe` (`updater/main.py:139`): `main.py:cleanup` (`_cleanup_update_files`) удалял свежий `*update.exe` сразу после `Popen` helper, до проверки `is_file` в хелпере (гонка 0.6с). Добавлен пропуск файлов новее 10 минут + лог `src exists/size` перед `Popen` в `UpdaterService.launch_updater` и листинг `parent.glob` в хелпере.
- Тест `test_main.py::test_cleanup_update_files_removes_leftovers` обновлён: `os.utime` на 700с назад для проверки удаления.

## [0.8.0] - 2026-09-06

### Добавлено

- Система заготовленных тем: 9 builtin — `dark_default`, `light_default`, `midnight`, `forest`, `ocean`, `sunset`, `arctic`, `kanagawa_wave` (dark), `kanagawa_lotus` (light) из `rebelot/kanagawa.nvim` (`lua/kanagawa/colors.lua`, `themes.lua`).
- Система пользовательских тем: `themes/*.json` гибрид `seed` + `colors` (до 40 ключей `ColorScheme` в snake_case, валидация hex), примеры `themes/example_ocean.json`, `themes/example_light_paper.json`, дока `themes/README.md`.
- Модуль `app/interface/themes` (`schema.py`, `builtin.py`, `loader.py`, `__init__.py`): реестр `list_themes`/`get_theme`/`apply_theme`/`reload_user_themes`, `ThemeDefinition.to_flet_theme()` (`Theme(color_scheme_seed)` / `Theme(color_scheme=ColorScheme)`).
- Импорт тем через UI: `SettingsPanel` — кнопка `Import` + `FilePicker` (валидация `ThemeDefinition`, копирование в `themes/<id>.json`, `SnackBar`, обновление `Dropdown`).
- Документация тем в `README.md` (секция 🎨 Темы) и `config.example.json` (`THEME: dark_default` + список 9 + legacy note).
- Тесты `tests/test_themes.py` (14): builtin valid, Kanagawa wave/dark lotus/light, hex/id/color валидация, `to_flet_theme` seed/hybrid/auto, loader ignore/duplicate, registry legacy, `apply_theme` mode.

### Изменено

- `ConfigSchema.THEME` default `dark` → `dark_default` (`app/schemas/config_schema.py:22`); миграция `dark/light` → `dark_default/light_default` в `app/core/config.py:40` и `update()`.
- `flet_app.py` — применение темы через `apply_theme(page, THEME)` + `page.theme`/`dark_theme` + `theme_mode`, header → `SurfaceContainer` Card (16, чип темы, `Divider`), обёртки панелей `Border OUTLINE_VARIANT`, `middle` `SURFACE_CONTAINER_LOW`, responsive `on_resized` (`<900:2/<1200:3/else 4`).
- `left_panel.py` / `right_panel.py` / `middle_panel.py` — `DEEP_PURPLE_500/GREY_500` → `SURFACE_CONTAINER*` токены, секции `Icon PRIMARY + Divider`, `TextField filled`, `FilledButton 48`, тайлы `borderRadius 12 + чип resolution`, empty state с иконкой.
- `settings.py` — `Dropdown` теперь все темы (builtin+user, sorted), `Import` рядом с темой, `_sync_from_config` → `reload_user_themes`.
- `.gitignore` — `themes/user_*.json`, `custom_*.json` игнор, `!example_*.json`.

### Исправлено

- `ThemeDefinition` лимит `colors` 20→40, `surface_variant` удалён (нет в Flet 0.86 `ColorScheme`), `sorted(glob)` для детерминизма, `FilePickerResultEvent` импорт.
- `loader._candidate_theme_dirs` порядок `cwd` > `repo` > `MEIPASS` > `exe` для tmp_path в тестах.

## [0.7.3] - 2026-08-14

### Исправлено

- Автообновление падало при скачивании: HTTP-клиент `UpdaterService`
  закрывался сразу после проверки релизов (`finally` в
  `check_and_offer`), а диалог получал уже закрытый клиент —
  «Cannot send a request, as the client has been closed». Клиент
  теперь живёт, пока открыт диалог, и закрывается при его закрытии
  или после запуска апдейтера.

### Добавлено

- Регрессионные тесты `tests/test_update_flow.py`: клиент остаётся
  открытым при предложении релиза, закрывается при ошибке/пустом
  ответе проверки, при закрытии диалога и перед `window.destroy()`.

## [0.7.2] - 2026-08-14

### Исправлено

- Поле API-ключа убрано из левой панели — ключ вводится только
  в настройках, фильтры и поиск берут его из `config.json`.
- NSFW/Sketchy разблокируются сразу после ввода ключа в настройках,
  без перезапуска приложения.
- Теги у NSFW-обоев — API-ключ теперь передаётся и в запрос деталей,
  и в запрос тегов.
- `NameError: name 'sys' is not defined` в `UpdaterService.launch_updater`
  (модуль не импортировал `sys`).
- Битый `config.json` (невалидный JSON) валил приложение при старте —
  чтение MODE/LOG_LVL выполнялось вне обработки ошибок; теперь битый
  файл пересоздаётся как задокументировано.

### Добавлено

- Покрытие тестами: до 61 теста (60 passed + 1 skipped). Новые наборы:
  `error_handling` (guard, хуки), форматтеры логов, реестр ресурсов,
  `main` (cleanup/ротация лога), фильтры левой панели (purity без
  ключа и с ключом), edge-кейсы апдейтера и конфига. Итог покрытия:
  `config.py` 100%, `updater.py` 82%, `wallhaven_api.py` 97%,
  `error_handling.py` 98%, суммарно по `app/` 51% (UI-слой по природе
  не покрыт).

## [0.7.1] - 2026-08-14

### Исправлено

- Сохранение настроек падало с `'Config' object has no attribute
  'update'` — метод `Config.update` был объявлен на уровне модуля,
  а не внутри класса.
- Автообновление: 404 от GitHub API — лишний слэш в URL
  (`/releases/?per_page=10`), релизы теперь запрашиваются без него.
- Автообновление: `UpdaterError` вместо вводящего в заблуждение
  «everything up to date» при сетевых ошибках.
- `cleanup()`: HTTP-клиенты закрываются через `page.on_disconnect`
  в живом цикле — «Event loop is closed» больше не возникает.

### Добавлено

- Расширенное логирование: диагностический INFO-блок при старте
  (версия, Python, платформа, пути, пид), глобальный перехват
  исключений (`sys.excepthook`, потоки, asyncio) и UI-обработчиков
  с полным traceback.
- Логи действий: сохранение настроек с диффом изменённых полей,
  проверки обновлений, скачивания, полноэкранный просмотр,
  тайминги запросов Wallhaven API (ms, размер ответа).
- JSON-записи логов дополнены полной датой, `pid` и версией
  приложения.
- API-ключ больше не попадает в логи (маскируется).
- Регрессионные тесты `tests/test_config.py` (метод `update`
  внутри класса + персист в файл).

## [0.7.0] - 2026-08-14

### Добавлено

- Полноценная панель настроек: тема, API-ключ, мода, уровень лога,
  порт, флаги обновлений — сохранение в `config.json`.
- Переключатель темы оформления (тёмная/светлая), поле `THEME`
  в конфиге.
- Дозагрузка размеров для обоев без `dimension_x/y` при выборе
  разрешения.
- SnackBar-уведомления о статусе скачивания и проверки обновлений.
- Реальная логика в `cleanup()`: чистка temp-файлов апдейта
  и ротация `ywallhaven_updater.log`.
- Тесты `tests/test_wallhaven_api.py` (моки httpx).
- Метод `Config.update()` для персиста настроек из панели.

### Изменено

- Фон полноэкранного просмотра использует тот же источник, что
  и основной слой, — слои не рассинхронизируются.
- Уведомления показываются через `page.show_dialog()` (SnackBar
  в Flet 0.86).

### Исправлено

- Фуллскрин: дублирующее превью в углу экрана.
- Не все обои показывали выбор разрешения при отсутствии
  `dimension_x/y` в ответе поиска.
- Ненадёжные уведомления об успехе/неуспехе скачивания.
- Мелкий нечитаемый диалог «Up to date» при проверке обновлений.

## [0.6.1] - 2026-08-13

### Исправлено

- `TypeError: check_and_offer()` — падение при стартовой проверке
  обновлений (`flet_app.py`, `settings.py`).
- Иконка приложения не попадала в exe (`datas` в `ywallhaven.spec`).
- `build-release.yml` — явные права `contents: write` для
  `GITHUB_TOKEN` (создание релиза падало с 403).

## [0.6.0] - 2026-08-13

### Добавлено

- Автообновление с GitHub Releases: `UpdaterService`, диалог с прогрессом
  и проверкой SHA-256, helper `ywallhaven-updater.exe`.
- Динамическая версия из git-тегов через `hatch-vcs`.
- `scripts/build.py` — сборка `ywallhaven.exe` и `ywallhaven-updater.exe`.
- Тесты `tests/test_updater.py` (версии, пре-релизы, целостность, апдейт).
- Поля конфига `CHECK_UPDATES` и `CHECK_PRERELEASES`.
- Кнопка «Check for updates» и версия приложения в настройках.
- Тихая проверка обновлений при старте.
- CI-сборка на GitHub Actions с авто-релизом по тегу (суффикс
  `-rc`/`-beta`/`-alpha` → pre-release).

### Изменено

- `.gitignore` — spec-файлы версионируются.
- README.md — инструкция по сборке и автообновлению.

## [0.5.0] - 2026-08-07

### Добавлено

- Выбор разрешения при скачивании (диалог: оригинал + подходящие пресеты).
- Кнопка скачивания в правой панели с выбором разрешения.
- Подгрузка тегов отдельным запросом к Wallhaven API — теги видны в правой панели.

### Изменено

- Скачивание по двойному клику переведено на единый механизм с выбором разрешения.
- Список свойств в правой панели вынесен в прокручиваемый вид — кнопка Download всегда в зоне видимости.
- Кнопки переключения и закрытия полноэкранного просмотра перенесены под изображение по центру.
- Фильтр relevance применяется только при наличии поискового запроса; блок сортировки по релевантности скрыт, пока фильтр не выбран.

### Исправлено

- `NameError`, из-за которого при каждом переподключении сессии `flet_main` запускался заново.
- `AttributeError: TextField.error_text` при вводе запроса — атрибут переименован в `error` для Flet 0.86.4.
- Ссылки `page`/`short` в правой панели.
- Размер кнопки загрузки в диалоге.

## [0.4.0] - 2026-08-05

### Добавлено

- Поле ввода API-ключа Wallhaven в `left_panel.py`.
- Фильтры поиска в `left_panel.py`.
- Полноценный поиск по Wallhaven API из левой панели.
- Кнопка скачивания изображения.
- Скачивание по двойному клику на превью.
- Новые теги для поиска в `wallhaven_api.py`.

### Изменено

- Переработан метод поиска в `wallhaven_api.py`.
- Доработана логика связи панелей в `flet_app.py`.

### Исправлено

- Ошибки отображения результатов поиска в `middle_panel.py`.

## [0.3.0] - 2026-08-05

### Добавлено

- Просмотр превью изображения и его свойств в `right_panel.py`.
- Полноразмерный просмотр по клику на превью.
- `app_mode` в конфиге — управление выводом консоли в prod-режиме.

### Изменено

- Все комментарии в коде переведены на английский язык, добавлены новые.
- `config.py`, `logger.py`, `logger_config.py` доработаны под поддержку `app_mode`.

### Исправлено

- Ошибка консоли в режиме `AppView.FLET_APP` (`main.py`).
- Ошибка прокрутки (scroll) в интерфейсе.

## [0.2.0] - 2026-08-04

### Добавлено

- `run.py` для запуска и сборки приложения под Win11.
- Асинхронные методы — приложение переведено на асинхронный режим.
- `wallhaven_api.py` — сервис для работы с Wallhaven API.
- `middle_panel.py`, реализован на уровне MVP.
- Заготовка `app_mode`.
- Схема и класс-менеджер конфигурации (`config_schema.py`).
- Пример файла конфигурации `config.example.json`.
- Автосоздание конфиг-файла при его отсутствии.
- Автоматическая подстановка значений конфига в приложение.
- Заглушки правой и левой панелей интерфейса.

### Изменено

- `ConfigSchema.py` переименован в `config_schema.py`.
- `app/__init__.py` перенесён в `app/schemas/wallhaven_schema.py`.
- Обновлена структура пакета `app/schemas`.

## [0.1.0] - 2026-08-01

### Добавлено

- Инициализирована основная структура проекта.
- Модуль логирования (`logger.py`, `logger_config.py`).
- Класс конфигурации (`config.py`), схема `ConfigSchema.py`.
- Базовые пакеты `app/core`, `app/schemas`.
- `.python-version`.
- `pyproject.toml` и `uv.lock` — переход на менеджер пакетов `uv`.

### Изменено

- `.gitignore` дополнен новыми правилами.

## [0.0.0] - 2026-07-30

### Добавлено

- Инициализация репозитория.
- Лицензия MIT (`LICENSE`).
- `.gitignore`.
- Черновой `README.md`.

[Unreleased]: https://github.com/Sh1yden/ywallhaven/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/Sh1yden/ywallhaven/compare/v0.8.9...v0.9.0
[0.8.9]: https://github.com/Sh1yden/ywallhaven/compare/v0.8.8...v0.8.9
[0.8.8]: https://github.com/Sh1yden/ywallhaven/compare/v0.8.7...v0.8.8
[0.8.7]: https://github.com/Sh1yden/ywallhaven/compare/v0.8.6...v0.8.7
[0.8.6]: https://github.com/Sh1yden/ywallhaven/compare/v0.8.5...v0.8.6
[0.8.5]: https://github.com/Sh1yden/ywallhaven/compare/v0.8.4...v0.8.5
[0.8.4]: https://github.com/Sh1yden/ywallhaven/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/Sh1yden/ywallhaven/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/Sh1yden/ywallhaven/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/Sh1yden/ywallhaven/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/Sh1yden/ywallhaven/compare/v0.7.3...v0.8.0
[0.7.3]: https://github.com/Sh1yden/ywallhaven/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/Sh1yden/ywallhaven/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/Sh1yden/ywallhaven/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/Sh1yden/ywallhaven/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/Sh1yden/ywallhaven/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/Sh1yden/ywallhaven/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Sh1yden/ywallhaven/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Sh1yden/ywallhaven/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Sh1yden/ywallhaven/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Sh1yden/ywallhaven/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Sh1yden/ywallhaven/compare/v0.0.0...v0.1.0
[0.0.0]: https://github.com/Sh1yden/ywallhaven/releases/tag/v0.0.0
