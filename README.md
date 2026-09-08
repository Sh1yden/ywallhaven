# 🖼 ywallhaven

![icon](docs/assets/icon.svg)

> **Краткое описание:** 🖼️🔍 Десктопное GUI-приложение для поиска, просмотра и скачивания обоев с [Wallhaven](https://wallhaven.cc/). Построено на асинхронном стеке Python и [Flet](https://flet.dev/) - без браузера и лишнего интерфейса, только нативное окно.

## ❔ Зачем вообще проект?

Личный клиент для Wallhaven: искать, фильтровать и скачивать обои сразу из отдельного приложения, без открытия сайта в браузере.

## 🛠 Техно-стек

- **Язык:** `Python 3.13`
- **GUI-фреймворк:** `Flet`
- **HTTP-клиент:** `httpx` (async)
- **Валидация/конфигурация:** `Pydantic` + `pydantic-settings`
- **Пакетный менеджер:** `uv` (`hatchling` под капотом)
- **Сборка в exe:** `PyInstaller` (Windows)
- **Источник данных:** [Wallhaven API](https://wallhaven.cc/help/api)

## Предпоказ/галерея

Увидеть полную галерею тем: [SHOWING THEMES](docs/SHOWING%20THEMES.md). Тут представлена тема: `dark_default`:

![](docs/assets/{234A4FDB-8DF3-414D-A6EC-A4709040AC74}.png)
![](docs/assets/{C3C21669-B1B3-4894-8AA6-AEDC2CA57FEF}.png)
![](docs/assets/{897FBC1B-9227-4DBD-A538-7CA9609A8470}.png)
![](docs/assets/{08A8660D-E4F3-46FA-8CE1-C7409394E5C3}.png)

## 🔽 Установка

По плану:
1. Зайти на страничку релизов: [Releases](https://github.com/Sh1yden/ywallhaven/releases).
2. Скачать `wallhaven.exe` и `updater` впридачу.
3. Скинуть файлы из 2 пункта в любую папку пк.
4. Запустить и пользоваться 💜.

При первом запуске в корне проекта автоматически создастся `config.json` со значениями по умолчанию (см. [`config.example.json`](config.example.json)). Папка `logs` для логов и папка `themes` для собственных тем приложения(там же внутри и гайд с примерами по созданию своих тем).

## 💻 Разделы для разработчиков

### 🧰 Разворачивание проекта

1. Клонируйте репозиторий:

```shell
git clone "https://github.com/Sh1yden/ywallhaven.git"
cd ywallhaven
```

2. Синхронизируйте окружение через `uv`:

```shell
uv sync
``` 

3. Запуск

```shell
uv run app/main.py
```

### 📦 Сборка в exe(Windows)

Основной путь - CI: пушится тег вида `vX.Y.Z`, GitHub Actions на `windows-latest` собирает оба exe и сам публикует релиз с ними:

- тег `v0.7.0` → обычный Release;
- тег `v0.7.0-rc1` / `-beta` / `-alpha` → pre-release.

В релиз всегда попадают два файла: `ywallhaven.exe` (основное приложение) и `ywallhaven-updater.exe` (помощник автообновления).

Локальная сборка (запасной вариант, только на Windows, т.к. PyInstaller не умеет кросс-компиляцию):

```shell
uv run python scripts/build.py
```

Скрипт определяет версию из git-тегов (hatch-vcs), генерирует `app/core/_version.py` и version-info, после чего собирает оба исполняемых файла в `dist/`.

### ♻ Система автообновления

Приложение проверяет GitHub Releases при старте и по кнопке «Check for updates» в настройках. Порядок работы:

1. Сравнение версий семвером по последнему релизу репозитория.
2. Скачивание `ywallhaven.exe` во временную папку с прогресс-баром.
3. Проверка SHA-256 по digest из GitHub API.
4. Запуск `ywallhaven-updater.exe`, который дожидается закрытия приложения, заменяет исполняемый файл и перезапускает его.

Поведением управляют поля в `config.json`(посмотреть стандартные значения: [`config.example.json`](config.example.json)).

### 🎨 Система тем

#### Встроенные

[SHOWING THEMES](docs/SHOWING%20THEMES.md)

Всего 9 встроенных тем: `dark_default`, `light_default`, `midnight`, `forest`, `ocean`, `sunset`, `arctic`, `kanagawa_wave` (dark, из `rebelot/kanagawa.nvim`), `kanagawa_lotus` (light). Выбор в приложении: Settings → Theme.

#### Собственные

##### Вкраце

кинь `themes/my_theme.json` рядом с `config.json` или нажми `Import` в настройках. Формат:

```json
{
  "id": "my_ocean",
  "name": "My Ocean",
  "mode": "dark",
  "seed": "#0066CC",
  "colors": { "primary": "#0066CC", "surface": "#101418" }
}
```

`seed` обязателен (генерирует M3 палитру), `colors` опционально перетирает любые токены `ColorScheme` (см. `themes/README.md` и `app/interface/themes/schema.py`). Легаси `"dark"/"light"` в `config.json` мигрируют на `dark_default/light_default`.

##### Более подробно в [THEMES README](themes/README.md).

### 🧪 Тесты

### 📑 Структура конфига

[config.example.json](config.example.json)

```json
{
    "MODE": "dev or prod",
    "LOG_LVL": "DEBUG, WARNING, INFO, and etc.",
    "PORT": 8550,
    "APIK": "YOUR_WALLHAVEN_API_KEY",
    "CHECK_UPDATES": true,
    "CHECK_PRERELEASES": false,
    "THEME": "dark_default"
}
```

- `MODE` - может быть либо `dev`, либо `prod`. 
- `LOG_LVL` - выбор режима логов.
- `PORT` - порт на котором запуститься веб приложение, если выбран такой способ запуска.
- `APIK` - ключ от сайта: [Wallhaven](https://wallhaven.cc/). Нужен для снятия ограничений на запросы + доступ к `sketchy`, `nsfw` постам.
- `CHECK_UPDATES` - проверять обновления при старте (по умолчанию `true`);
- `CHECK_PRERELEASES` - предлагать пре-релизы (по умолчанию `false`).
- `THEME` - выбор темы приложения, подробнее в разделе [🎨 Система тем](#система-тем).

## 🗄 Структура проекта

- `app` - папка всего приложения.
  - `core` - ядро проекта: конфигурация (`config.py`), логирование (`logger.py` + `logger_config.py`), обработка ошибок (`error_handling.py`), реестр закрываемых ресурсов (`resources.py`), определение версии (`version.py`).
  - `interface` - весь UI на `Flet`.
    - `components` - панели интерфейса: `left_panel.py` (поиск, фильтры), `middle_panel.py` (сетка), `right_panel.py` (превью), `settings.py` (настройки + темы), `update_dialog.py` (диалог автообновления).
    - `themes` - `schema.py`/`builtin.py`/`loader.py` - реестр тем, Kanagawa из `rebelot/kanagawa.nvim`, гибрид `seed+colors`.
    - `flet_app.py` - сборка панелей в единый layout.
  - `schemas` - `pydantic`-схемы: конфигурации (`config_schema.py`), Wallhaven API (`wallhaven_schema.py`), апдейтера (`updater_schema.py`).
  - `service` - бизнес-логика: `wallhaven_api.py` (клиент Wallhaven API), `updater.py` (автообновление).
  - `main.py` - точка входа: режим приложения, логирование, запуск Flet.
- `updater/` - отдельный executable для автообновления (`main.py`).
- `docs/` - документация и ассеты: `docs/assets/` (иконки `icon.{png,svg,ico}`).
- `themes/` - пользовательские темы `*.json` + примеры `example_*.json` (см. `themes/README.md`).
- `scripts/` - `build.py` - скрипт сборки exe (версия, иконка, PyInstaller).
- `tests/` - pytest-тесты.
- `ywallhaven.spec` и `ywallhaven-updater.spec` - PyInstaller-спеки для сборки обоих exe.
- `run.py` - точка запуска/сборки приложения.
- `config.example.json` - пример конфигурации.
- `pyproject.toml` и `uv.lock` - конфигурация проекта и зависимости.
- [`README.md`](README.md) - этот файл.
- [`CHANGELOG.md`](CHANGELOG.md) - список изменений в проекте.
- [`LICENSE`](LICENSE) - лицензия проекта.

## ☑ Roadmap / Планируется

Можно посмотреть в файле [CHANGELOG.md](CHANGELOG.md).

## Лицензия

Этот проект распространяется под лицензией MIT. Подробности в файле [LICENSE](LICENSE).

## 💜 Вопросы, контакты / FAQ

Для вопросов и предложений создавайте Issues в репозитории или же пишите в телеграмм который указан в профиле.

PS Любой помощи или совету буду очень благодарен.
