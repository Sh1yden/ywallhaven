# 🖼 ywallhaven

🌐 Language / Язык **README**: [Русский](README.md) · **English**

![icon](docs/assets/icon.svg)

> **Short description:** 🖼️🔍 A desktop GUI app for searching, browsing and downloading wallpapers from [Wallhaven](https://wallhaven.cc/). Built on an async Python stack and [Flet](https://flet.dev/) — no browser, no clutter, just a native window.

## ❔ Why this project?

A personal Wallhaven client: search, filter and download wallpapers straight from a standalone app, without opening the site in a browser.

## 🛠 Tech stack

- **Language:** `Python 3.13`
- **GUI framework:** `Flet`
- **HTTP client:** `httpx` (async)
- **Validation/config:** `Pydantic` + `pydantic-settings`
- **Package manager:** `uv` (`hatchling` under the hood)
- **exe build:** `PyInstaller` (Windows)
- **Data source:** [Wallhaven API](https://wallhaven.cc/help/api)

## Preview/gallery

Full theme gallery: [SHOWING THEMES](docs/SHOWING%20THEMES.md). The `dark_default` theme is shown here:

![](docs/assets/{234A4FDB-8DF3-414D-A6EC-A4709040AC74}.png)
![](docs/assets/{C3C21669-B1B3-4894-8AA6-AEDC2CA57FEF}.png)
![](docs/assets/{897FBC1B-9227-4DBD-A538-7CA9609A8470}.png)
![](docs/assets/{08A8660D-E4F3-46FA-8CE1-C7409394E5C3}.png)

## 💜 User guide

### 🔽 Install / Quick start

The plan:
1. Go to the releases page: [Releases](https://github.com/Sh1yden/ywallhaven/releases).
2. Download `ywallhaven_portable-vX.Y.Z.zip` (it contains a `ywallhaven` folder with both `exe` files). Prefer single files — grab `ywallhaven.exe` + `ywallhaven-updater.exe` separately.
3. Optionally verify integrity (compare the hash against `SHA256SUMS.txt` from the same release):

```shell
certutil -hashfile ywallhaven.exe SHA256
```

4. Unpack wherever you like and run `ywallhaven.exe` 💜.

On first launch, `config.json` (default settings, see [`config.example.json`](config.example.json)), a `logs` folder (logs) and a `themes` folder (custom themes + in-folder guide with examples) are created next to the exe.

### 🖱 Daily use

- **Search:** type a query on the left, tune filters (categories, `purity`, sorting, resolution) and hit search. You can also search by tag by clicking a tag under the preview — the query fills itself in.
- **Preview:** clicking a gallery image in the middle shows its properties and tags on the right. Double-click opens the download dialog right away.
- **Download:** the `Download` button → pick a resolution (`Original` or a preset matching your screen) → save dialog.
- **Wallpaper in one click:** the wallpaper button next to `Download` sets the current art as your desktop background.
- **Fullscreen:** click the preview → `←/→` buttons flip through, wheel/`−/+` buttons zoom (zoom follows the cursor), tapping the backdrop while zoomed does not close (misclick protection).
- **Themes:** Settings → Theme (9 built-in, including Kanagawa). For your own — drop `themes/my_theme.json` next to it or use the `Import` button in settings.

### ♻ Auto-update

The app checks releases on startup (and via the `Check for updates` button in settings). The flow:
1. Offers the new version in a dialog.
2. Downloads `ywallhaven.exe` with a progress bar and verifies SHA-256.
3. Shows the standard Windows UAC prompt (that's fine — the helper updates the exe in the install folder) → replaces the file and restarts the app.
4. Declined the UAC prompt — no harm done, you stay on the current version and get asked again later.

### ❓ FAQ

- **A "Wallhaven is down" banner + `Retry` button in the gallery.** The wallhaven site itself is down (happens); the app is not at fault — the error code is right on the banner. Hit `Retry` or wait: it re-checks on its own every minute.
- **Empty grid / everything hangs while scrolling.** Most likely wallhaven throttling — paste in an API key (section below) and it gets noticeably snappier.
- **Windows complained on launch (SmartScreen).** Softly speaking — happens with unsigned builds. Verified: recent releases don't complain anymore; if it does ask — it's still us, verify the hash against `SHA256SUMS.txt`.
- **NSFW/sketchy doesn't search.** The site won't serve those without a key — paste in an API key (section below), it unlocks instantly with no restart.
- **Found a bug.** Open an Issue in the repo and attach a chunk from `logs\` plus the version from settings — that makes fixes way faster 💜.

### 🔑 API key: lifting Wallhaven limits

When scrolling the wallpaper gallery too fast you may hit limits on the `wallhaven` side.
So best to follow this short plan:
1. go to the [Wallhaven](https://wallhaven.cc/) site.
2. register on the site.
3. go here [Account Settings](https://wallhaven.cc/settings/account). The `API Key` item.
4. copy the `API Key` and paste it into the app (the API key field lives in the settings section).
5. Use it calmly with no limits 💜.

If you fear for your data privacy, namely theft of your API key.
It is stored locally in `config.json`. Even if stolen,
you can simply regenerate it using step 3 of the instructions above.

## 💻 Developer sections

### 🧰 Project setup

1. Clone the repository:

```shell
git clone "https://github.com/Sh1yden/ywallhaven.git"
cd ywallhaven
```

2. Sync the environment with `uv`:

```shell
uv sync
``` 

3. Run

```shell
uv run app/main.py
```

### 📦 Building the exe (Windows)

The main path is CI: a tag like `vX.Y.Z` is pushed, GitHub Actions on `windows-latest` builds both exes and publishes the release itself:

- tag `v0.7.0` → regular Release;
- tag `v0.7.0-rc1` / `-beta` / `-alpha` → pre-release.

Every release always contains four files: `ywallhaven.exe` (the main app), `ywallhaven-updater.exe` (the auto-update helper), `ywallhaven_portable-vX.Y.Z.zip` (a `ywallhaven` folder with both exes) and `SHA256SUMS.txt` (checksums).

Local build (fallback, Windows only, since PyInstaller can't cross-compile):

```shell
uv run python scripts/build.py
```

The script resolves the version from git tags (hatch-vcs), generates `app/core/_version.py` and version-info, then builds both executables into `dist/`.

### ♻ Auto-update system

The app checks GitHub Releases on startup and via the «Check for updates» button in settings. The flow:

1. Semver comparison against the latest repo release.
2. Downloading `ywallhaven.exe` to a temp folder with a progress bar.
3. SHA-256 check against the digest from the GitHub API.
4. Launching `ywallhaven-updater.exe` through the standard UAC prompt (an elevated helper) that waits for the app to close, replaces the executable and restarts it.

Behavior is controlled by fields in `config.json`(for defaults see [`config.example.json`](config.example.json)).

### 🎨 Theme system

#### Built-in

[SHOWING THEMES](docs/SHOWING%20THEMES.md)

9 built-in themes in total: `dark_default`, `light_default`, `midnight`, `forest`, `ocean`, `sunset`, `arctic`, `kanagawa_wave` (dark, from `rebelot/kanagawa.nvim`), `kanagawa_lotus` (light). Pick in the app: Settings → Theme.

#### Custom

##### In brief

drop `themes/my_theme.json` next to `config.json` or hit `Import` in settings. Format:

```json
{
  "id": "my_ocean",
  "name": "My Ocean",
  "mode": "dark",
  "seed": "#0066CC",
  "colors": { "primary": "#0066CC", "surface": "#101418" }
}
```

`seed` is required (generates the M3 palette), `colors` optionally overrides any `ColorScheme` tokens (see `themes/README.md` and `app/interface/themes/schema.py`). Legacy `"dark"/"light"` in `config.json` migrate to `dark_default/light_default`.

##### More details in [THEMES README](themes/README.md).

### 🧪 Tests

Live in the `tests` directory.
Coverage at the moment: 74%.

### 📑 Config structure

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

- `MODE` - either `dev` or `prod`. 
- `LOG_LVL` - log mode selection.
- `PORT` - port the web app starts on, if that launch mode is chosen.
- `APIK` - key from the site: [Wallhaven](https://wallhaven.cc/). Needed to lift request limits + access `sketchy`, `nsfw` posts.
- `CHECK_UPDATES` - check for updates on startup (default `true`);
- `CHECK_PRERELEASES` - offer pre-releases (default `false`).
- `THEME` - app theme selection, more in the [🎨 Theme system](#-theme-system) section.

## 🗄 Project structure

- `app` - the whole application folder.
  - `core` - project core: configuration (`config.py`), logging (`logger.py` + `logger_config.py`), error handling (`error_handling.py`), closable-resource registry (`resources.py`), version resolution (`version.py`).
  - `interface` - all UI on `Flet`.
    - `bus.py` - `page.pubsub` event bus between panels (7 `ywallhaven/*` topics).
    - `components` - interface panels: `left_panel.py` (search, filters), `middle_panel.py` (grid), `right_panel.py` (preview), `settings.py` (settings + themes), `update_dialog.py` (auto-update dialog).
    - `themes` - `schema.py`/`builtin.py`/`loader.py` - theme registry, Kanagawa from `rebelot/kanagawa.nvim`, hybrid `seed+colors`.
    - `flet_app.py` - assembles the panels into a single layout.
  - `schemas` - `pydantic` schemas: configuration (`config_schema.py`), Wallhaven API (`wallhaven_schema.py`), updater (`updater_schema.py`).
  - `service` - business logic: `wallhaven_api.py` (Wallhaven API client), `updater.py` (auto-update), `wallpaper.py` (setting wallpapers on Windows).
  - `main.py` - entry point: app mode, logging, Flet launch.
- `updater/` - standalone executable for auto-update (`main.py`).
- `docs/` - docs and assets: `docs/assets/` (icons `icon.{png,svg,ico}`).
- `themes/` - custom themes `*.json` + `example_*.json` samples (see `themes/README.md`).
- `scripts/` - `build.py` (exe build: version, icon, PyInstaller), `package_release.py` (zip + `SHA256SUMS.txt`), `smoke_wallhaven.py` (live API check with no mocks).
- `tests/` - pytest tests.
- `ywallhaven.spec` and `ywallhaven-updater.spec` - PyInstaller specs for building both exes.
- `run.py` - app launch/build entry point.
- `config.example.json` - config sample.
- `pyproject.toml` and `uv.lock` - project config and dependencies.
- [`README.md`](README.md) - the Russian readme.
- [`CHANGELOG.md`](CHANGELOG.md) - project changelog.
- [`LICENSE`](LICENSE) - project license.

## ☑ Roadmap / Planned

See the [CHANGELOG.md](CHANGELOG.md) file.

## License

This project is distributed under the MIT license. Details in the [LICENSE](LICENSE) file.

## 💜 Questions, contacts / FAQ

For questions and suggestions open Issues in the repo or message the Telegram listed in the profile.

PS Thank you very much for any help or advice.
