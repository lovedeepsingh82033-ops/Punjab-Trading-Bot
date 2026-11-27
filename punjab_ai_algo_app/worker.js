/**
 * PUNJAB AI ALGO — Cloudflare Telegram webhook + read-only scanner bridge
 * Educational research / paper demo only.
 * No forecasts, trade instructions, broker access, or order execution.
 *
 * Required Cloudflare secrets:
 *   TELEGRAM_BOT_TOKEN
 *   TELEGRAM_WEBHOOK_SECRET
 *   TELEGRAM_SETUP_SECRET
 *
 * Optional private snapshot bridge secrets:
 *   BOT_STATE_BRIDGE_URL
 *   BOT_STATE_BRIDGE_KEY
 *   BOT_STATE_BRIDGE_BUCKET (defaults to scanner-state)
 */

const DISCLAIMER =
  "Educational research / paper demo only. Historical diagnostics are not forecasts or trading instructions. No broker access or order execution.";
const DASHBOARD_URL = "https://punjab-ai-algo.streamlit.app/";
const MAX_TELEGRAM_TEXT = 3900;

function dashboardKeyboard() {
  return {
    inline_keyboard: [[{
      text: "Open PUNJAB AI ALGO Dashboard",
      url: DASHBOARD_URL
    }]]
  };
}

function plainText(value) {
  return String(value ?? "")
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/<\/(?:b|strong|i|em|u|code|pre)>/gi, "")
    .replace(/<(?:b|strong|i|em|u|code|pre)[^>]*>/gi, "")
    .replace(/<[^>]*>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

async function telegramSend(env, chatId, message, replyMarkup) {
  if (!env.TELEGRAM_BOT_TOKEN) return false;
  const text = plainText(message).slice(0, MAX_TELEGRAM_TEXT);
  const payload = {
    chat_id: chatId,
    text,
    disable_web_page_preview: true
  };
  if (replyMarkup) payload.reply_markup = replyMarkup;

  const response = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }
  );
  const result = await response.json().catch(() => ({}));
  if (!response.ok || result.ok !== true) {
    console.error("Telegram sendMessage failed:", response.status);
    return false;
  }
  return true;
}

async function getSnapshot(env) {
  const baseUrl = String(env.BOT_STATE_BRIDGE_URL || "").trim().replace(/\/$/, "");
  const key = String(env.BOT_STATE_BRIDGE_KEY || "").trim();
  const bucket = String(env.BOT_STATE_BRIDGE_BUCKET || "scanner-state").trim();
  if (!baseUrl || !key || !bucket) return { status: "NOT_CONFIGURED" };

  const objectUrl =
    baseUrl + "/storage/v1/object/" + encodeURIComponent(bucket) + "/bot_state.json";

  try {
    const response = await fetch(objectUrl, {
      method: "GET",
      headers: {
        apikey: key,
        Authorization: "Bearer " + key
      },
      signal: AbortSignal.timeout(12000)
    });

    if (response.status === 404) return { status: "MISSING" };
    if (!response.ok) {
      console.error("Snapshot bridge read failed:", response.status);
      return { status: "UNAVAILABLE" };
    }

    const payload = await response.json();
    if (!payload || typeof payload !== "object" || payload.schema_version !== 1) {
      return { status: "INVALID" };
    }
    return { status: "AVAILABLE", payload };
  } catch (error) {
    console.error("Snapshot bridge request failed:", error?.name || "Error");
    return { status: "UNAVAILABLE" };
  }
}

function snapshotStatusText(result) {
  if (result.status === "NOT_CONFIGURED") {
    return "Scanner snapshot bridge: NOT CONFIGURED. Add the private bridge secrets to Cloudflare to enable scanner reports.";
  }
  if (result.status === "MISSING") {
    return "Scanner snapshot: no saved scan has reached the private bridge yet.";
  }
  if (result.status === "INVALID") {
    return "Scanner snapshot: the stored file did not pass schema validation.";
  }
  if (result.status !== "AVAILABLE") {
    return "Scanner snapshot: temporarily unavailable. Check the private bridge configuration.";
  }
  const p = result.payload;
  return [
    "SCANNER SNAPSHOT",
    "Generated (UTC): " + (p.generated_at || "Unknown"),
    "Scanner health: " + (p.scanner_health?.status || "UNKNOWN"),
    "Completed analyses: " + (p.scanner_health?.completed_analyses ?? "N/A") +
      " / " + (p.scanner_health?.expected_analyses ?? "N/A"),
    "Completion: " + (Number.isFinite(Number(p.scanner_health?.completion_pct))
      ? Number(p.scanner_health.completion_pct).toFixed(1) + "%"
      : "N/A"),
    "Saved observations: " + (p.observation_count ?? p.observations?.length ?? 0),
    DISCLAIMER
  ].join("\n");
}

function researchText(result) {
  if (result.status !== "AVAILABLE") return snapshotStatusText(result);
  const p = result.payload;
  const intelligence = p.intelligence || {};
  const dashboard = p.dashboard || {};
  const findings = Array.isArray(intelligence.findings)
    ? intelligence.findings.slice(0, 5)
    : [];
  const notes = Array.isArray(intelligence.recommendations)
    ? intelligence.recommendations.slice(0, 4)
    : [];

  const lines = [
    "PUNJAB AI ALGO — RESEARCH BRIEF",
    "Generated (UTC): " + (p.generated_at || "Unknown"),
    "Scanner health: " + (intelligence.scanner_health || p.scanner_health?.status || "UNKNOWN"),
    "Analyses: " + (intelligence.analyses ?? dashboard.analyses ?? 0),
    "Data quality: " + JSON.stringify(intelligence.quality_counts || {}),
    "Market regimes: " + JSON.stringify(intelligence.regime_counts || {}),
    "Volatility regimes: " + JSON.stringify(intelligence.volatility_counts || {}),
    "Unusual historical observations: " + (intelligence.anomaly_count ?? dashboard.anomalies ?? 0),
    "Economic calendar: " + (intelligence.calendar_status || dashboard.calendar_status || "UNKNOWN"),
    "",
    "Priority findings:"
  ];
  lines.push(...(findings.length ? findings.map(x => "• " + x) : ["• No findings stored."]));
  lines.push("", "Research / maintenance notes:");
  lines.push(...(notes.length ? notes.map(x => "• " + x) : ["• No notes stored."]));
  lines.push("", DISCLAIMER);
  return lines.join("\n");
}

function observationText(result) {
  if (result.status !== "AVAILABLE") return snapshotStatusText(result);
  const p = result.payload;
  const observations = Array.isArray(p.observations) ? p.observations.slice(-12).reverse() : [];
  if (!observations.length) {
    return "No scanner observations are stored in the latest snapshot.\n" + DISCLAIMER;
  }
  const lines = [
    "RECENT SAVED RESEARCH OBSERVATIONS",
    "Snapshot (UTC): " + (p.generated_at || "Unknown")
  ];
  for (const item of observations) {
    lines.push(
      "• " + (item.symbol || "Unknown") + " · " + (item.timeframe || "Unknown") +
      " · " + (item.candle_time || "time unavailable") +
      " · data " + (item.data_quality?.status || "UNKNOWN") +
      " · regime " + (item.market_regime?.label || "UNKNOWN") +
      " · volatility " + (item.volatility?.regime || "UNKNOWN")
    );
  }
  lines.push("", "Historical context only; not a forecast or trading instruction.");
  return lines.join("\n");
}

async function handleTelegramUpdate(request, env) {
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

  const message = update?.message;
  if (!message?.chat?.id || typeof message.text !== "string") {
    return new Response("OK");
  }

  const chatId = message.chat.id;
  const command = message.text.trim().split(/\s+/)[0].split("@")[0].toLowerCase();

  try {
    switch (command) {
      case "/start":
        await telegramSend(
          env,
          chatId,
          "⚡ PUNJAB AI ALGO\n\nTelegram research companion is online.\n" +
            DISCLAIMER + "\n\nCommands: /status /health /research /snapshot /history /calendar /markets /app /help",
          dashboardKeyboard()
        );
        break;

      case "/help":
        await telegramSend(
          env,
          chatId,
          "/start — welcome\n/status — bot and bridge status\n/health — latest scanner health\n/research — latest research brief\n/snapshot — latest scan timestamp and counts\n/history — recent saved research observations\n/calendar — saved calendar context\n/markets — scanner coverage overview\n/app — dashboard link\n/help — commands"
        );
        break;

      case "/app":
        await telegramSend(env, chatId, "Open the educational research dashboard:", dashboardKeyboard());
        break;

      case "/status": {
        const bridge = await getSnapshot(env);
        const bridgeText = bridge.status === "AVAILABLE"
          ? "Scanner bridge: CONNECTED"
          : "Scanner bridge: " + bridge.status;
        await telegramSend(
          env,
          chatId,
          "PUNJAB AI ALGO STATUS\nWebhook worker: ONLINE\nTelegram: CONFIGURED\n" +
            bridgeText + "\nLive market feed in this Worker: NOT PROVIDED\nOrder execution: DISABLED\n\n" +
            DISCLAIMER,
          dashboardKeyboard()
        );
        break;
      }

      case "/health":
      case "/snapshot": {
        const snapshot = await getSnapshot(env);
        await telegramSend(env, chatId, snapshotStatusText(snapshot));
        break;
      }

      case "/research": {
        const snapshot = await getSnapshot(env);
        await telegramSend(env, chatId, researchText(snapshot));
        break;
      }

      case "/history": {
        const snapshot = await getSnapshot(env);
        await telegramSend(env, chatId, observationText(snapshot));
        break;
      }

      case "/calendar": {
        const snapshot = await getSnapshot(env);
        if (snapshot.status !== "AVAILABLE") {
          await telegramSend(env, chatId, snapshotStatusText(snapshot));
          break;
        }
        const calendar = snapshot.payload.calendar || {};
        const events = Array.isArray(calendar.events) ? calendar.events.slice(0, 8) : [];
        const lines = [
          "SAVED ECONOMIC CALENDAR CONTEXT",
          "Status: " + (calendar.status || "UNKNOWN"),
          "Matching events: " + (calendar.count ?? events.length)
        ];
        for (const event of events) {
          lines.push(
            "• " + (event.event_time_utc || "time unknown") + " · " +
            (event.currency || "N/A") + " · " + (event.impact || "N/A") +
            " · " + (event.event || "Unnamed event") + " · " + (event.source || "Source unavailable")
          );
        }
        lines.push("", calendar.message || "Manually maintained context; not a live calendar feed.", DISCLAIMER);
        await telegramSend(env, chatId, lines.join("\n"));
        break;
      }

      case "/markets":
        await telegramSend(
          env,
          chatId,
          "SCANNER COVERAGE\n28 Forex pairs are organized into four rotating batches of seven. The GitHub scanner workflow runs every two hours; full pair rotation is designed for an eight-hour cycle.\nThis Worker does not fetch live quotes. Use /snapshot for the latest saved scan.\n\n" +
            DISCLAIMER
        );
        break;

      default:
        await telegramSend(env, chatId, "Unknown command. Use /help.\n" + DISCLAIMER);
    }
  } catch (error) {
    console.error("Update handling failed:", error?.name || "Error");
    await telegramSend(env, chatId, "The request could not be completed right now. Please try again later.");
  }

  return new Response("OK");
}

async function setupWebhook(request, env, url) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_WEBHOOK_SECRET || !env.TELEGRAM_SETUP_SECRET) {
    return new Response("Required setup secrets are missing", { status: 503 });
  }
  if (request.headers.get("X-Setup-Secret") !== env.TELEGRAM_SETUP_SECRET) {
    return new Response("Unauthorized", { status: 401 });
  }

  const webhookUrl = url.origin + "/telegram";
  const response = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setWebhook`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        url: webhookUrl,
        secret_token: env.TELEGRAM_WEBHOOK_SECRET,
        allowed_updates: ["message"],
        drop_pending_updates: false
      })
    }
  );
  const result = await response.json().catch(() => ({}));
  if (!response.ok || result.ok !== true) {
    console.error("Telegram setWebhook failed:", response.status);
    return new Response("Telegram webhook setup failed; check Worker logs.", { status: 502 });
  }
  return new Response("Telegram webhook successfully registered: " + webhookUrl, {
    headers: { "content-type": "text/plain; charset=utf-8" }
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return new Response(
        "PUNJAB AI ALGO webhook worker is running. Educational research only.",
        { headers: { "content-type": "text/plain; charset=utf-8" } }
      );
    }

    if (request.method === "POST" && url.pathname === "/setup") {
      return setupWebhook(request, env, url);
    }

    if (request.method === "POST" && url.pathname === "/telegram") {
      return handleTelegramUpdate(request, env);
    }

    return new Response("Not found", { status: 404 });
  }
};
