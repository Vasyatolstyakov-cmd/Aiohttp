# REST API объявлений на aiohttp

Домашнее задание к лекции «Aiohttp»: Flask-сервис объявлений переписан на
асинхронный `aiohttp`.

## Возможности

- создание объявления — `POST /advertisements`;
- получение списка — `GET /advertisements`;
- получение объявления — `GET /advertisements/<id>`;
- редактирование — `PATCH` или `PUT /advertisements/<id>`;
- удаление — `DELETE /advertisements/<id>`;
- автоматическое сохранение даты создания;
- асинхронная работа с SQLite через SQLAlchemy и aiosqlite;
- валидация JSON и ответы с кодами `400` и `404`.

Объявление содержит `title`, `description`, `created_at` и `owner`.

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

После запуска API доступно по адресу <http://127.0.0.1:8080>.
По умолчанию используется база SQLite `advertisements.db`.

## Пример создания объявления

```bash
curl -i -X POST http://127.0.0.1:8080/advertisements \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Продам велосипед",
    "description": "Городской велосипед в хорошем состоянии",
    "owner": "alexander"
  }'
```

Остальные примеры находятся в файле `requests.http`.

## Тесты

```bash
pytest -q
```

Необязательное задание с Docker в этот проект не включено.
