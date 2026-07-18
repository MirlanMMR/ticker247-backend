/**
 * Ticker 24/7 — рекламный бот (Cloudflare Worker)
 *
 * Поток: /start → выбор региона → условия и пакеты на языке клиента →
 * клиент присылает готовый пост → бот пересылает администратору.
 *
 * Секреты (Settings → Variables в Cloudflare):
 *   BOT_TOKEN     — токен из BotFather
 *   ADMIN_CHAT_ID — chat_id владельца (куда пересылать заявки)
 *
 * Webhook: https://api.telegram.org/bot<TOKEN>/setWebhook?url=<worker-url>
 */

const PAGES = {
  ru: "https://mirlanmmr.github.io/ticker247/ads.html",
  en: "https://mirlanmmr.github.io/ticker247/ads-en.html",
  es: "https://mirlanmmr.github.io/ticker247/ads-es.html",
  pt: "https://mirlanmmr.github.io/ticker247/ads-pt.html",
};

const T = {
  ru: {
    flag: "🇷🇺",
    name: "Русский (СНГ)",
    terms:
      "⚡ <b>Реклама в Ticker 24/7 — регион СНГ</b>\n\n" +
      "<b>Пакеты:</b>\n" +
      "• Стандарт — карточка в ленте, 24 часа\n" +
      "• Стандарт+ — карточка в ленте, 3 дня\n" +
      "• Премиум — карусель на главной + лента, 3 дня\n" +
      "• Премиум макс — карусель + лента + бейдж «ПАРТНЁР», 7 дней\n\n" +
      "<b>Требования:</b> готовый пост 100–800 знаков + фото (горизонтальное, от 1280×720) " +
      "или ссылка на видео. Ответственность за содержание несёт заказчик.\n\n" +
      "📋 Полные условия: ",
    send:
      "\n\n✍️ <b>Чтобы разместить рекламу</b> — пришлите сюда одним сообщением:\n" +
      "1. Готовый пост (текст + фото/видео)\n" +
      "2. Название пакета\n\n" +
      "Мы ответим в течение 24 часов с ценой и способом оплаты.",
    received: "✅ Заявка принята! Ответим в течение 24 часов.",
    choose: "Выберите регион размещения:",
  },
  en: {
    flag: "🇬🇧",
    name: "English",
    terms:
      "⚡ <b>Advertising on Ticker 24/7 — English region</b>\n\n" +
      "<b>Packages:</b>\n" +
      "• Standard — feed card, 24 hours\n" +
      "• Standard+ — feed card, 3 days\n" +
      "• Premium — main-screen carousel + feed, 3 days\n" +
      "• Premium Max — carousel + feed + PARTNER badge, 7 days\n\n" +
      "<b>Requirements:</b> ready-made post 100–800 characters + landscape image (min 1280×720) " +
      "or a video link. The client is responsible for the content.\n\n" +
      "📋 Full terms: ",
    send:
      "\n\n✍️ <b>To place an ad</b> — send here in one message:\n" +
      "1. Your ready-made post (text + photo/video)\n" +
      "2. Package name\n\n" +
      "We reply within 24 hours with the price and payment method.",
    received: "✅ Request received! We'll reply within 24 hours.",
    choose: "Choose your placement region:",
  },
  es: {
    flag: "🇪🇸",
    name: "Español",
    terms:
      "⚡ <b>Publicidad en Ticker 24/7 — región en español</b>\n\n" +
      "<b>Paquetes:</b>\n" +
      "• Estándar — tarjeta en el feed, 24 horas\n" +
      "• Estándar+ — tarjeta en el feed, 3 días\n" +
      "• Premium — carrusel principal + feed, 3 días\n" +
      "• Premium Max — carrusel + feed + insignia SOCIO, 7 días\n\n" +
      "<b>Requisitos:</b> publicación lista de 100–800 caracteres + imagen horizontal (mín. 1280×720) " +
      "o enlace de video. El cliente es responsable del contenido.\n\n" +
      "📋 Condiciones completas: ",
    send:
      "\n\n✍️ <b>Para publicar</b> — envía aquí en un solo mensaje:\n" +
      "1. Tu publicación lista (texto + foto/video)\n" +
      "2. Nombre del paquete\n\n" +
      "Respondemos en 24 horas con el precio y la forma de pago.",
    received: "✅ ¡Solicitud recibida! Respondemos en 24 horas.",
    choose: "Elige la región de publicación:",
  },
  pt: {
    flag: "🇧🇷",
    name: "Português",
    terms:
      "⚡ <b>Publicidade no Ticker 24/7 — região em português</b>\n\n" +
      "<b>Pacotes:</b>\n" +
      "• Padrão — card no feed, 24 horas\n" +
      "• Padrão+ — card no feed, 3 dias\n" +
      "• Premium — carrossel principal + feed, 3 dias\n" +
      "• Premium Max — carrossel + feed + selo PARCEIRO, 7 dias\n\n" +
      "<b>Requisitos:</b> publicação pronta de 100–800 caracteres + imagem horizontal (mín. 1280×720) " +
      "ou link de vídeo. O cliente é responsável pelo conteúdo.\n\n" +
      "📋 Condições completas: ",
    send:
      "\n\n✍️ <b>Para anunciar</b> — envie aqui em uma única mensagem:\n" +
      "1. Sua publicação pronta (texto + foto/vídeo)\n" +
      "2. Nome do pacote\n\n" +
      "Respondemos em 24 horas com o preço e a forma de pagamento.",
    received: "✅ Solicitação recebida! Respondemos em 24 horas.",
    choose: "Escolha a região de publicação:",
  },
};

async function tg(env, method, body) {
  const r = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

const regionKeyboard = {
  inline_keyboard: [
    [
      { text: "🇷🇺 Русский", callback_data: "region:ru" },
      { text: "🇬🇧 English", callback_data: "region:en" },
    ],
    [
      { text: "🇪🇸 Español", callback_data: "region:es" },
      { text: "🇧🇷 Português", callback_data: "region:pt" },
    ],
  ],
};

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("Ticker 24/7 ads bot");
    let update;
    try { update = await request.json(); } catch { return new Response("bad request", { status: 400 }); }

    try {
      // ── Нажатие кнопки региона ──────────────────────────────────────────
      if (update.callback_query) {
        const cb = update.callback_query;
        const lang = (cb.data || "").split(":")[1];
        if (T[lang]) {
          await tg(env, "sendMessage", {
            chat_id: cb.message.chat.id,
            text: T[lang].terms + PAGES[lang] + T[lang].send,
            parse_mode: "HTML",
            disable_web_page_preview: true,
          });
        }
        await tg(env, "answerCallbackQuery", { callback_query_id: cb.id });
        return new Response("ok");
      }

      const msg = update.message;
      if (!msg) return new Response("ok");
      const chatId = msg.chat.id;

      // ── /start → выбор региона (на 4 языках сразу) ──────────────────────
      if ((msg.text || "").startsWith("/start")) {
        await tg(env, "sendMessage", {
          chat_id: chatId,
          text:
            "⚡ Ticker 24/7 — Advertising\n\n" +
            `${T.ru.choose}\n${T.en.choose}\n${T.es.choose}\n${T.pt.choose}`,
          reply_markup: regionKeyboard,
        });
        return new Response("ok");
      }

      // ── /id — узнать свой chat_id (для настройки ADMIN_CHAT_ID) ─────────
      if ((msg.text || "") === "/id") {
        await tg(env, "sendMessage", { chat_id: chatId, text: `chat_id: ${chatId}` });
        return new Response("ok");
      }

      // ── Сообщение от администратора: ответ клиенту через reply ──────────
      // Ответь (reply) на пересланную заявку — бот отправит текст клиенту
      if (String(chatId) === String(env.ADMIN_CHAT_ID) && msg.reply_to_message) {
        const m = (msg.reply_to_message.text || "").match(/#id(\d+)/);
        if (m && msg.text) {
          await tg(env, "sendMessage", { chat_id: m[1], text: msg.text });
          await tg(env, "sendMessage", { chat_id: chatId, text: "✅ Отправлено клиенту" });
        }
        return new Response("ok");
      }

      // ── Любое другое сообщение = заявка → пересылаем администратору ─────
      const from = msg.from || {};
      const who = [from.first_name, from.last_name].filter(Boolean).join(" ") +
        (from.username ? ` (@${from.username})` : "");
      await tg(env, "sendMessage", {
        chat_id: env.ADMIN_CHAT_ID,
        text: `📩 Заявка от ${who}\n#id${chatId}\n\n(ответь reply на это сообщение — я передам клиенту)`,
      });
      await tg(env, "forwardMessage", {
        chat_id: env.ADMIN_CHAT_ID,
        from_chat_id: chatId,
        message_id: msg.message_id,
      });
      // Подтверждение клиенту на 4 языках коротко
      await tg(env, "sendMessage", {
        chat_id: chatId,
        text: `${T.ru.received}\n${T.en.received}`,
      });
    } catch (e) {
      // не роняем webhook — Telegram повторяет неудачные доставки
      console.log("error:", e.message);
    }
    return new Response("ok");
  },
};
