# Librarian — витрина и MCP-дистрибуция (публичный релиз v0.1.0)

Дата: 2026-07-08. Статус: дизайн утверждён устно, ждёт ревью текста.

## Цель

Сделать репозиторий публичным «топ-репо»: незнакомец понимает продукт за 10 секунд
(README + GIF), пробует за 30 (`uv tool install` / `uvx`-однострочник), находит сервер
в MCP-экосистеме (официальный реестр, каталоги). Продукт и код конвейера не меняются.

## Не-цели (осознанно отложено)

- `.mcpb`-бандл для Claude Desktop, `lib serve --http` — uvx-однострочник закрывает
  основной сценарий; вернёмся по спросу (v2).
- MOBI/AZW3, OCR, эмбеддинги, веб-UI — вне релиза (кандидаты на следующие вехи).
- Рефакторинг кода — структурных долгов не найдено (макс. модуль 333 строки, ~330 тестов).

## Инварианты

- **Выходные байты конвейера не меняются.** `PIPELINE_VERSION` не трогается, golden не
  регенерируются. Все работы — раскладка, метаданные, доки, CI.
- Реальные книги в репо не попадают (история проверена: только синтетические фикстуры).

## Принятые решения

| Вопрос | Решение |
|--------|---------|
| Имя пакета на PyPI | `librarian-cli` (`librarian`, `libby`, `librarian-mcp` заняты); импорт `librarian` и команда `lib` без изменений |
| Имя репо | `libby` → `librarian-cli` (`gh repo rename`, GitHub ставит редирект) |
| Раскладка | пакет сплющивается из `librarian/` в корень репо (один README для GitHub и PyPI, стандартная раскладка) |
| Лицензия | MIT, копирайт «Temirlan Jumabayev» |
| Язык | корневой `README.md` — английский (канон); русский — `README.ru.md` |
| Демо | `examples/` с 1–2 крошечными public-domain книгами (Gutenberg) + GIF, записанный `vhs` |
| Публичность | включается **последним шагом, только с явного подтверждения пользователя** |

## Работы

### W1. Сплющивание раскладки
`git mv` содержимого `librarian/` в корень: `pyproject.toml`, `src/`, `tests/`,
`scripts/`, `uv.lock`; слить `librarian/.gitignore` в корневой. Обновить пути в
`.github/workflows/ci.yml` (убрать `working-directory: librarian`), `CLAUDE.md`,
`docs/MILESTONES.md`. Пересоздать venv (`uv sync` из корня).
**Проверка:** `uv run pytest -q` зелёный из корня, golden без регенерации.

### W2. Метаданные пакета
`pyproject.toml`: `name = "librarian-cli"`, английское `description`, `readme`,
`license = "MIT"`, `keywords`, `classifiers`, `[project.urls]`. Побочный эффект: wheel
переименуется в `librarian_cli-*.whl` — обновить глобы в `tests/test_install.py`,
`scripts/smoke_wheel.sh` и job `wheel-offline` в CI (где паттерн зависит от имени).

### W3. LICENSE и CHANGELOG
`LICENSE` (MIT, 2026 Temirlan Jumabayev). `CHANGELOG.md` с записью v0.1.0
(сжатое содержание M1–M6 по-английски).

### W4. README
- `README.md` (EN, канон, корень — его же видит PyPI): питч «Turn any ebook into clean,
  token-counted Markdown chapters — and let Claude read your bookshelf over MCP.
  Deterministic RAG: no embeddings, no network, no API keys»; бейджи (CI, PyPI, Python,
  MIT); демо-GIF; quick start (`uv tool install librarian-cli`, `lib ingest`, `lib find`,
  `lib get --budget`); таблица команд; секция установки MCP в Claude Code / Claude
  Desktop / Cursor; модель качества; детерминизм (зачем); ограничения; ссылка на RU.
- `README.ru.md`: текущий русский README, выправленный под новую раскладку и имена.
- MCP-однострочник (ключевой CTA):
  `claude mcp add librarian -- uvx --from "librarian-cli[serve]" lib serve --library ~/books`

### W5. examples/ и демо-GIF
- `examples/`: 1–2 маленькие public-domain книги с Project Gutenberg (EN, суммарно
  < 500 КБ; кандидат — «The Yellow Wallpaper» Gilman). В wheel не входят (hatch пакует
  только `src/librarian`).
- `docs/assets/demo.tape` (vhs-сценарий: ingest → list → find → get --budget) и
  `docs/assets/demo.gif`. Сценарий коммитится — GIF воспроизводим.

### W6. Release-workflow (PyPI)
`.github/workflows/release.yml`: на push тега `v*` → `uv build` → публикация через
PyPA `gh-action-pypi-publish` c **Trusted Publishing (OIDC)**, environment `pypi`.
Никаких токенов в секретах.
**Шаг пользователя:** аккаунт на PyPI + pending trusted publisher
(project `librarian-cli`, repo `Terobyte/librarian-cli`, workflow `release.yml`).

### W7. MCP registry
`server.json` (io.modelcontextprotocol registry, тип пакета `pypi`, транспорт stdio,
пакет `librarian-cli` extra `serve`). Публикация `mcp-publisher`-ом **после** выхода
пакета на PyPI (реестр валидирует существование пакета).
**Шаг пользователя:** GitHub device-flow аутентификация в mcp-publisher.

### W8. Репо и релиз
`gh repo rename librarian-cli`; description + topics (`mcp`, `mcp-server`, `rag`,
`ebooks`, `epub`, `fb2`, `pdf`, `claude`, `llm`, `markdown`, `cli`). Затем — с явного
подтверждения — `gh repo edit --visibility public`; тег `v0.1.0`; GitHub Release с
нотами из CHANGELOG (запускает W6).

### W9. Каталоги
Подготовленные тексты заявок: PR в `awesome-mcp-servers`, сабмиты mcp.so / PulseMCP.
Отправка — с аккаунтов пользователя (PR можно через его `gh`).

## Порядок и зависимости

```
W1 → { W2, W3, W4, W5 } → W6(workflow-файл) → [ревью пользователя]
  → W8(rename, topics, PUBLIC, тег) → PyPI-релиз → W7(registry) → W9(каталоги)
```

Всё до «PUBLIC» готовится и коммитится в приватном репо; публичность и внешние
сабмиты — только после финального ревью.

## Шаги, требующие пользователя

1. PyPI: создать аккаунт, добавить pending trusted publisher (W6).
2. Подтвердить перевод репо в public (W8).
3. mcp-publisher: GitHub device-flow (W7).
4. Сабмиты форм каталогов / PR в awesome-списки (W9).

## Риски

| Риск | Смягчение |
|------|-----------|
| Сплющивание ломает пути в CI/тестах | W1 проверяется полным прогоном тестов и dry-run джобов локально (`uv build`, smoke) |
| Глобы wheel-имени после переименования | W2 явно перечисляет все три места (test_install, smoke_wheel.sh, CI) |
| Редирект старого URL после rename | GitHub делает автоматически; локальный remote обновить `git remote set-url` |
| PD-статус демо-книг | только Project Gutenberg (US public domain), мелкие тексты |
| `uvx --from "librarian-cli[serve]"` синтаксис | проверить локально до фиксации в README |

## Критерии приёмки

- `uv run pytest -q` зелёный из корня репо; golden не регенерированы.
- `uv build` даёт `librarian_cli-0.1.0-py3-none-any.whl`; офлайн-smoke проходит.
- README.md (EN) с работающим GIF; README.ru.md актуален.
- Тег v0.1.0 публикует пакет на PyPI через OIDC; `uv tool install librarian-cli`
  ставит команду `lib`.
- `librarian-cli` виден в официальном MCP registry; однострочник из README подключает
  сервер к Claude Code.
