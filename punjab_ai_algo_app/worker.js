/**
 * PUNJAB AI ALGO — Telegram webhook companion
 * Educational demo only. No market signals, financial advice, or order execution.
 *
 * Cloudflare Worker secrets required:
 *   TELEGRAM_BOT_TOKEN
 *   TELEGRAM_WEBHOOK_SECRET
 */
const DISCLAIMER =
  "Educational research / paper demo only. No live prices, trade recommendations, or order execution.";
const DASHBOARD_URL = "https://punjab-ai-algo.streamlit.app/";

function keyboard() {
  return {
    inline_keyboard: [[{
      text: "🌐 Open PUNJAB AI ALGO Dashboard",
      web_app: { url: DASHBOARD_URL }
    }]]
  };
}

async function telegramSend(env, chatId, text, replyMarkup) {
  const payload = { chat_id: chatId, text };
  if (replyMarkup) payload.reply_markup = replyMarkup;
  const response = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }
  );
  if (!response.ok) {
    console.error("Telegram sendMessage failed:", response.status);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return new Response("PUNJAB AI ALGO webhook is running. Educational demo only.", {
        headers: { "content-type": "text/plain; charset=utf-8" }
      });
    }

    if (request.method !== "POST" || url.pathname !== "/telegram") {
      return new Response("Not found", { status: 404 });
    }

    if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("Worker secrets are not configured", { status: 503 });
    }

    const suppliedSecret = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (suppliedSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("Bad request", { status: 400 });
    }

    const message = update.message;
    if (!message?.chat?.id || typeof message.text !== "string") {
      return new Response("OK");
    }

    const chatId = message.chat.id;
    const command = message.text.trim().split(/\\s+/)[0].split("@")[0].toLowerCase();

    switch (command) {
      case "/start":
        await telegramSend(
          env,
          chatId,
          "⚡ PUNJAB AI ALGO\\n\\nWelcome!\\n" + DISCLAIMER +
            "\\n\\nUse /status, /research, /markets, /app, or /help.",
          keyboard()
        );
        break;
      case "/app":
        await telegramSend(env, chatId, "Open the educational research dashboard:", keyboard());
        break;
      case "/status":
        await telegramSend(
          env,
          chatId,
          "🟢 BOT: WEBHOOK WORKER\\n📊 DATA: DEMO ONLY\\n🔒 ORDER EXECUTION: DISABLED\\n📡 LIVE FEED: NOT CONFIGURED"
        );
        break;
      case "/research":
        await telegramSend(
          env,
          chatId,
          "📚 Educational topics: market terminology, chart concepts, and hypothetical paper-journal notes. No BUY/SELL instructions are generated.\\n" + DISCLAIMER
        );
        break;
      case "/markets":
        await telegramSend(
          env,
          chatId,
          "🌍 Planned educational coverage: FX, commodities, and crypto concepts. Current quotes are unavailable; no live market feed is configured."
        );
        break;
      case "/help":
        await telegramSend(
          env,
          chatId,
          "/start — welcome and dashboard\\n/app — open dashboard\\n/status — bot status\\n/research — educational research\\n/markets — planned coverage\\n/help — commands"
        );
        break;
      default:
        await telegramSend(env, chatId, "Use /help to see the available educational demo commands.");
    }

    return new Response("OK");
  }
};
