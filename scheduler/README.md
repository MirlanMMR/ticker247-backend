# Внешний планировщик ленты (Cloudflare Worker)

**Зачем.** Расписание GitHub Actions ненадёжно: дозор за неделю выполнил 28 запусков из ~290. Слоты
ленты (три в дневные часы главных поясов каждого пула, `schedule_pools.py`) должны отрабатывать
в срок. Планировщик Cloudflare срабатывает точно и запускает workflow `fetch.yml` через API.
Строки `cron:` в `fetch.yml` остаются запасными: они видят свежую ленту и выходят, не тратя денег.

**Деньги.** Тот же объём работы, что у слотов: 15 «пул-прогонов» в сутки. Планировщик Cloudflare
бесплатен (Workers Free: 100 000 запросов в сутки, у нас 13 запусков).

## Развёртывание через сайт Cloudflare (Node и консоль не нужны)

1. **Токен GitHub.** github.com → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token. Имя `ticker247-scheduler`, срок до года, Resource owner —
   `MirlanMMR`, Repository access — **Only select repositories → ticker247-backend**, Permissions →
   Repository permissions → **Actions: Read and write**. Generate и скопировать токен (покажут один раз).
2. **Воркер.** dash.cloudflare.com → Workers & Pages → Create → Create Worker → имя `ticker247-scheduler` →
   Deploy → Edit code → удалить пример, вставить весь файл `scheduler/worker.js` → Deploy.
3. **Секрет.** Воркер → Settings → Variables and Secrets → Add → тип **Secret**, имя `GH_DISPATCH_TOKEN`,
   значение — токен из шага 1 → Deploy.
4. **Расписание.** Воркер → Settings → Trigger Events → Cron Triggers → Add → `2 * * * *` (один триггер,
   каждый час на :02, время UTC). Слот выбирает сам воркер по часу.
5. **Проверка.** Адрес воркера (`…workers.dev`) показывает таблицу слотов. Ближайший слот (по UTC: 5, 8, 9, 12,
   13, 14, 15, 16, 18, 19, 20, 22, 23): через 2–3 минуты после :02 в GitHub → Actions → Fetch должен
   появиться запуск с событием `workflow_dispatch`. Если запуска нет — Workers → воркер → Logs.

Через консоль (если есть Node): `cd scheduler && npx wrangler deploy && npx wrangler secret put GH_DISPATCH_TOKEN`.

## Если что-то сломалось
- Токен истёк или отозван → воркер пишет в лог `HTTP 401`; запасные строки cron в `fetch.yml` продолжают
  обновлять ленту (с пропусками GitHub). Новый токен — шаг 1 и `wrangler secret put`.
- Менять слоты — в `schedule_pools.py`, затем обновить таблицу `SLOTS` в `worker.js` и строки `cron:` в
  `fetch.yml` (триггер Cloudflare остаётся один); `test_schedule.py` не даст расходиться трём местам.
