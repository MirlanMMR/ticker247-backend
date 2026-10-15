# Внешний планировщик ленты (Cloudflare Worker)

**Зачем.** Расписание GitHub Actions ненадёжно: дозор за неделю выполнил 28 запусков из ~290. Слоты
ленты (четыре в дневные часы главных поясов каждого пула, `schedule_pools.py`) должны отрабатывать
в срок. Планировщик Cloudflare срабатывает точно и запускает workflow `fetch.yml` через API.
Строки `cron:` в `fetch.yml` остаются запасными: они видят свежую ленту и выходят, не тратя денег.

**Деньги.** Тот же объём работы, что у слотов: 20 «пул-прогонов» в сутки. Планировщик Cloudflare
бесплатен (Workers Free: 100 000 запросов в сутки, у нас 12 запусков).

## Развёртывание (делает владелец: нужен его аккаунт и токен)

1. GitHub → Settings → Developer settings → Fine-grained personal access tokens → новый токен:
   репозиторий **только** `MirlanMMR/ticker247-backend`, право **Actions: Read and write**, срок до года.
2. В папке `scheduler/`:
   ```bash
   npx wrangler deploy
   npx wrangler secret put GH_DISPATCH_TOKEN   # вставить токен из шага 1
   ```
3. Проверка: открыть адрес воркера (покажет слоты); в Cloudflare → Workers → ticker247-scheduler →
   Triggers убедиться, что 12 cron-триггеров на месте; в Actions через 2 минуты после слота должен
   появиться запуск «Fetch» с событием `workflow_dispatch`.

## Если что-то сломалось
- Токен истёк или отозван → воркер пишет в лог `HTTP 401`; запасные строки cron в `fetch.yml` продолжают
  обновлять ленту (с пропусками GitHub). Новый токен — шаг 1 и `wrangler secret put`.
- Менять слоты — в `schedule_pools.py`, затем перегенерировать `worker.js`, `wrangler.toml` и строки
  `cron:` в `fetch.yml`; `test_schedule.py` не даст расходиться трём местам.
