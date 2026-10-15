/**
 * Ticker 24/7 — внешний планировщик ленты (Cloudflare Worker, 15.10.2026).
 *
 * Зачем: расписание GitHub Actions ненадёжно (28 запусков дозора из ~290 за неделю), а слоты
 * ленты привязаны к дневным часам читателей (schedule_pools.py: 8 поясов, 4 слота на пул).
 * Планировщик Cloudflare срабатывает точно и дёргает workflow fetch.yml через API; строки
 * `cron:` в fetch.yml остаются запасными (:07 и :37) и выходят, увидев свежую ленту.
 *
 * Расписание — wrangler.toml (минута :02 каждого слота). Таблица SLOTS ниже обязана совпадать с
 * schedule_pools.SLOTS_UTC: это проверяет test_schedule.py.
 *
 * Секрет (один): GH_DISPATCH_TOKEN — fine-grained токен GitHub, ТОЛЬКО репозиторий
 * MirlanMMR/ticker247-backend, право «Actions: Read and write», срок до года.
 *   npx wrangler secret put GH_DISPATCH_TOKEN
 */

const REPO = "MirlanMMR/ticker247-backend";
const WORKFLOW = "fetch.yml";
const SHELVES_HOUR = 5;   // schedule_pools.COUNTRY_SHELVES_HOUR: «полки стран» раз в сутки

// час UTC → пулы
const SLOTS = {"0": ["es"], "5": ["ru"], "8": ["ru", "fr"], "11": ["ru", "fr"], "12": ["pt"], "14": ["ru", "fr", "en"], "15": ["pt", "es"], "17": ["fr", "en"], "18": ["pt", "es"], "20": ["en"], "21": ["pt", "es"], "23": ["en"]};

async function dispatch(env, pools, shelves) {
  const body = JSON.stringify({
    ref: "main",
    inputs: { pools: pools.join(","), from_scheduler: "true", shelves: shelves ? "true" : "false" },
  });
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "ticker247-scheduler",
          "Content-Type": "application/json",
        },
        body,
      });
      if (r.status === 204) return { ok: true, pools };
      console.log(`dispatch ${pools}: HTTP ${r.status} ${(await r.text()).slice(0, 200)} (попытка ${attempt})`);
    } catch (e) {
      console.log(`dispatch ${pools}: ${e} (попытка ${attempt})`);
    }
    await new Promise((res) => setTimeout(res, attempt * 5000));
  }
  return { ok: false, pools };
}

export default {
  // Cloudflare вызывает по строкам cron из wrangler.toml: «2 5 * * *» → час 5
  async scheduled(event, env, ctx) {
    const hour = String(parseInt(event.cron.split(" ")[1], 10));
    const pools = SLOTS[hour];
    if (!pools) {
      console.log(`нет слота для '${event.cron}' — ничего не запускаю`);
      return;
    }
    ctx.waitUntil(dispatch(env, pools, Number(hour) === SHELVES_HOUR));
  },

  // GET / — какие слоты и пулы известны (без секретов); запуск вручную только через GitHub
  async fetch() {
    return new Response(JSON.stringify({ repo: REPO, workflow: WORKFLOW, slots: SLOTS }, null, 2),
      { headers: { "content-type": "application/json" } });
  },
};
