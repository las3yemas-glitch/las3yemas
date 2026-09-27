import express from "express";
import crypto from "crypto";
import fs from "fs/promises";
import path from "path";

const app = express();
app.use(express.json());

const CLIENT_KEY = process.env.TIKTOK_CLIENT_KEY;
const CLIENT_SECRET = process.env.TIKTOK_CLIENT_SECRET;
const BASE_URL = process.env.RENDER_EXTERNAL_URL;

// Secreto compartido para que GitHub Actions (u otro llamador de confianza)
// pueda disparar la publicación automática en TikTok. NUNCA se expone en
// respuestas ni en logs.
const AUTOMATION_SECRET = process.env.TIKTOK_AUTOMATION_SECRET;

// Nivel de privacidad para las publicaciones automáticas. Mientras la app
// esté en modo Sandbox / cliente no auditado, TikTok solo permite SELF_ONLY.
const PRIVACY_LEVEL = process.env.TIKTOK_PRIVACY_LEVEL || "SELF_ONLY";

// Credenciales de Render, opcionales. Si están presentes, el servidor puede
// persistir el refresh token actualizando la variable de entorno del propio
// servicio en Render, para no perderlo en cada reinicio/redeploy.
const RENDER_API_KEY = process.env.RENDER_API_KEY;
const RENDER_SERVICE_ID = process.env.RENDER_SERVICE_ID;

// Respaldo local opcional (solo sobrevive a reinicios simples del mismo
// contenedor, NO a un redeploy). Se usa si no hay credenciales de Render.
const TOKEN_STORE_PATH =
  process.env.TOKEN_STORE_PATH || "./.data/tiktok-token.json";

// Imágenes semanales, en el mismo orden que usa el workflow de
// publicidad-diaria.yml para Instagram/Facebook (1 = lunes ... 7 = domingo).
const WEEKLY_IMAGES = {
  1: "01_semana.jpg",
  2: "02_semana.jpg",
  3: "03_semana.jpg",
  4: "04_semana.jpg",
  5: "05_semana.jpg",
  6: "06_semana.jpg",
  7: "07_semana.jpg",
};

const CAPTION =
  "🥚 Las 3 Yemas 💗 Huevos frescos y contenido útil para ti. 🚚 Repartimos en " +
  "Viña del Mar, Valparaíso, Quilpué, Belloto y Villa Alemana. #Las3Yemas #HuevosFrescos";

// ---------------------------------------------------------------------------
// Estado en memoria del token. Nunca se imprime ni se envía al cliente.
// ---------------------------------------------------------------------------
let tokenState = {
  accessToken: null,
  refreshToken: null,
  obtainedAt: null, // epoch ms
  expiresIn: null, // segundos, según TikTok
};

let lastPersistError = null;
let lastPublishId = null;
let lastPersistOk = null;

function maskToken(token) {
  if (!token) return null;
  return token.slice(0, 4) + "…" + token.slice(-4);
}

function logSafe(label, data = {}) {
  console.log(label, JSON.stringify(data));
}

// ---------------------------------------------------------------------------
// Persistencia del refresh token
// ---------------------------------------------------------------------------

async function persistRefreshToken(refreshToken) {
  if (RENDER_API_KEY && RENDER_SERVICE_ID) {
    try {
      await persistRefreshTokenToRender(refreshToken);
      lastPersistOk = new Date().toISOString();
      lastPersistError = null;
      logSafe("tiktok:persist:render:ok", {});
      return;
    } catch (err) {
      lastPersistError = err.message;
      logSafe("tiktok:persist:render:error", { message: err.message });
      // No lanzamos: seguimos intentando el respaldo local para no perder
      // el token si Render falló por una razón transitoria.
    }
  }

  try {
    await persistRefreshTokenToDisk(refreshToken);
    logSafe("tiktok:persist:disk:ok", { path: TOKEN_STORE_PATH });
  } catch (err) {
    logSafe("tiktok:persist:disk:error", { message: err.message });
  }
}

async function persistRefreshTokenToRender(refreshToken) {
  // La API de Render para variables de entorno reemplaza la lista completa,
  // así que primero leemos las actuales y solo pisamos la que nos interesa.
  // IMPORTANTE: revisa la documentación vigente de Render (api-docs.render.com)
  // antes de confiar en este mecanismo — la API puede cambiar.
  const headers = {
    Authorization: `Bearer ${RENDER_API_KEY}`,
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  const getResp = await fetch(
    `https://api.render.com/v1/services/${RENDER_SERVICE_ID}/env-vars`,
    { headers }
  );

  if (!getResp.ok) {
    throw new Error(`Render GET env-vars falló: HTTP ${getResp.status}`);
  }

  const current = await getResp.json();
  // La respuesta es una lista de { envVar: { key, value } }
  const envVars = (Array.isArray(current) ? current : []).map((item) => ({
    key: item.envVar?.key ?? item.key,
    value: item.envVar?.value ?? item.value,
  }));

  const filtered = envVars.filter((v) => v.key !== "TIKTOK_REFRESH_TOKEN");
  filtered.push({ key: "TIKTOK_REFRESH_TOKEN", value: refreshToken });

  const putResp = await fetch(
    `https://api.render.com/v1/services/${RENDER_SERVICE_ID}/env-vars`,
    {
      method: "PUT",
      headers,
      body: JSON.stringify(filtered),
    }
  );

  if (!putResp.ok) {
    const text = await putResp.text().catch(() => "");
    throw new Error(
      `Render PUT env-vars falló: HTTP ${putResp.status} ${text.slice(0, 200)}`
    );
  }

  // Nota: actualizar variables de entorno normalmente dispara un redeploy
  // del servicio en Render. Es esperado: ocurre como mucho una vez al día
  // (cuando se ejecuta la publicación automática), no en cada request.
}

async function persistRefreshTokenToDisk(refreshToken) {
  const dir = path.dirname(TOKEN_STORE_PATH);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(
    TOKEN_STORE_PATH,
    JSON.stringify({ refreshToken, savedAt: new Date().toISOString() }),
    { mode: 0o600 }
  );
}

async function loadPersistedRefreshToken() {
  if (process.env.TIKTOK_REFRESH_TOKEN) {
    return process.env.TIKTOK_REFRESH_TOKEN;
  }
  try {
    const raw = await fs.readFile(TOKEN_STORE_PATH, "utf8");
    const data = JSON.parse(raw);
    return data.refreshToken || null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// OAuth / refresh de TikTok
// ---------------------------------------------------------------------------

async function exchangeCodeForToken(code, redirectUri) {
  const body = new URLSearchParams({
    client_key: CLIENT_KEY,
    client_secret: CLIENT_SECRET,
    code,
    grant_type: "authorization_code",
    redirect_uri: redirectUri,
  });

  const response = await fetch("https://open.tiktokapis.com/v2/oauth/token/", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  const data = await response.json();

  if (!response.ok || !data.access_token) {
    logSafe("tiktok:oauth:exchange:error", {
      status: response.status,
      error: data.error,
      error_description: data.error_description,
    });
    throw new Error(data.error_description || "token exchange failed");
  }

  return data;
}

async function refreshAccessToken(refreshToken) {
  const body = new URLSearchParams({
    client_key: CLIENT_KEY,
    client_secret: CLIENT_SECRET,
    grant_type: "refresh_token",
    refresh_token: refreshToken,
  });

  const response = await fetch("https://open.tiktokapis.com/v2/oauth/token/", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  const data = await response.json();

  if (!response.ok || !data.access_token) {
    logSafe("tiktok:oauth:refresh:error", {
      status: response.status,
      error: data.error,
      error_description: data.error_description,
    });
    throw new Error(data.error_description || "refresh failed");
  }

  return data;
}

function storeTokenData(data) {
  tokenState = {
    accessToken: data.access_token,
    refreshToken: data.refresh_token || tokenState.refreshToken,
    obtainedAt: Date.now(),
    expiresIn: data.expires_in || null,
  };
  logSafe("tiktok:token:stored", {
    accessToken: maskToken(tokenState.accessToken),
    hasRefreshToken: Boolean(tokenState.refreshToken),
    expiresIn: tokenState.expiresIn,
  });
}

function accessTokenIsFresh() {
  if (!tokenState.accessToken || !tokenState.obtainedAt) return false;
  const ageSeconds = (Date.now() - tokenState.obtainedAt) / 1000;
  const safetyMarginSeconds = 10 * 60; // refrescar 10 min antes de expirar
  const expiresIn = tokenState.expiresIn || 24 * 60 * 60;
  return ageSeconds < expiresIn - safetyMarginSeconds;
}

// Devuelve un access token válido, refrescando (y persistiendo el nuevo
// refresh token) si hace falta. Lanza un error legible si no hay forma de
// autenticar sin intervención manual.
async function getValidAccessToken() {
  if (accessTokenIsFresh()) {
    return tokenState.accessToken;
  }

  const refreshToken = tokenState.refreshToken || (await loadPersistedRefreshToken());

  if (!refreshToken) {
    throw new Error(
      "No hay refresh token disponible. Es necesario autorizar TikTok " +
        "manualmente una vez en /tiktok/login."
    );
  }

  const data = await refreshAccessToken(refreshToken);
  storeTokenData(data);

  if (data.refresh_token) {
    await persistRefreshToken(data.refresh_token);
  }

  return tokenState.accessToken;
}

// ---------------------------------------------------------------------------
// Lógica de publicación (compartida entre el botón de prueba manual y el
// endpoint automático que llama GitHub Actions)
// ---------------------------------------------------------------------------

function getTodayImageUrl() {
  const dia = new Date().getUTCDay(); // 0 = domingo ... 6 = sábado
  const isoDay = dia === 0 ? 7 : dia; // 1 = lunes ... 7 = domingo
  const filename = WEEKLY_IMAGES[isoDay];
  return `https://las3yemas-glitch.github.io/las3yemas/publicidad/${filename}`;
}

async function publishToTikTok({ imageUrl, privacyLevel }) {
  const accessToken = await getValidAccessToken();

  const creatorResponse = await fetch(
    "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json; charset=UTF-8",
      },
      body: JSON.stringify({}),
    }
  );

  const creatorData = await creatorResponse.json();

  if (!creatorResponse.ok || creatorData?.error?.code !== "ok") {
    logSafe("tiktok:creator_info:error", { body: creatorData });
    throw new Error("No se pudo consultar la cuenta de TikTok (creator_info).");
  }

  const privacyOptions = creatorData?.data?.privacy_level_options || [];

  if (!privacyOptions.includes(privacyLevel)) {
    throw new Error(
      `TikTok no permite el nivel de privacidad "${privacyLevel}" para esta cuenta. ` +
        `Opciones disponibles: ${privacyOptions.join(", ") || "ninguna"}.`
    );
  }

  const publishResponse = await fetch(
    "https://open.tiktokapis.com/v2/post/publish/content/init/",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json; charset=UTF-8",
      },
      body: JSON.stringify({
        post_info: {
          title: "Huevos frescos Las 3 Yemas 🥚",
          description: CAPTION,
          privacy_level: privacyLevel,
          disable_comment: false,
          auto_add_music: true,
        },
        source_info: {
          source: "PULL_FROM_URL",
          photo_cover_index: 0,
          photo_images: [imageUrl],
        },
        post_mode: "DIRECT_POST",
        media_type: "PHOTO",
      }),
    }
  );

  const publishData = await publishResponse.json();

  if (!publishResponse.ok || publishData?.error?.code !== "ok") {
    logSafe("tiktok:publish:error", { body: publishData });
    throw new Error("TikTok rechazó la publicación. Revisa los logs de Render.");
  }

  lastPublishId = publishData?.data?.publish_id || null;

  logSafe("tiktok:publish:ok", {
    publish_id: publishData?.data?.publish_id,
    imageUrl,
    privacyLevel,
  });

  return publishData;
}

function requireAutomationSecret(req, res, next) {
  if (!AUTOMATION_SECRET) {
    return res.status(500).json({
      error: "server_misconfigured",
      message: "Falta configurar TIKTOK_AUTOMATION_SECRET en Render.",
    });
  }

  const auth = req.headers.authorization || "";
  const expected = `Bearer ${AUTOMATION_SECRET}`;

  // Comparación en tiempo constante para no filtrar el secreto por timing.
  const ok =
    auth.length === expected.length &&
    crypto.timingSafeEqual(Buffer.from(auth), Buffer.from(expected));

  if (!ok) {
    return res.status(401).json({ error: "unauthorized" });
  }

  next();
}

// ---------------------------------------------------------------------------
// Rutas
// ---------------------------------------------------------------------------

app.get("/", (req, res) => {
  res.send(`
    <h1>Las 3 Yemas 🥚</h1>
    <p>Integración TikTok</p>

    <p>
      <a href="/tiktok/login">
        <button>Conectar con TikTok</button>
      </a>
    </p>

    <p>
      <a href="/tiktok/test">
        <button>Publicar prueba en TikTok</button>
      </a>
    </p>

    <p>
      <a href="/tiktok/status">
        <button>Ver estado (sin datos sensibles)</button>
      </a>
    </p>
  `);
});

// Estado de salud, seguro de exponer: nunca incluye tokens.
app.get("/tiktok/status", async (req, res) => {
  const persistedRefreshToken = await loadPersistedRefreshToken();
  res.json({
    hasAccessTokenInMemory: Boolean(tokenState.accessToken),
    accessTokenIsFresh: accessTokenIsFresh(),
    hasRefreshTokenAvailable: Boolean(
      tokenState.refreshToken || persistedRefreshToken
    ),
    persistence: RENDER_API_KEY && RENDER_SERVICE_ID ? "render-api" : "disk-fallback",
    lastPersistOk,
    lastPersistError,
    todayImageUrl: getTodayImageUrl(),
    privacyLevel: PRIVACY_LEVEL,
  });
});

app.get("/tiktok/login", (req, res) => {
  const state = crypto.randomBytes(16).toString("hex");
  const redirectUri = BASE_URL + "/tiktok/callback";

  const params = new URLSearchParams({
    client_key: CLIENT_KEY,
    scope: "user.info.basic,video.upload,video.publish",
    response_type: "code",
    redirect_uri: redirectUri,
    state,
  });

  res.cookie("tiktok_state", state, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    maxAge: 10 * 60 * 1000,
  });

  res.redirect("https://www.tiktok.com/v2/auth/authorize/?" + params.toString());
});

app.get("/tiktok/callback", async (req, res) => {
  try {
    const { code, state, error, error_description } = req.query;

    if (error) {
      return res
        .status(400)
        .send(`TikTok rechazó la autorización: ${error_description || error}`);
    }

    const cookieState = req.headers.cookie
      ?.split(";")
      .map((v) => v.trim())
      .find((v) => v.startsWith("tiktok_state="))
      ?.split("=")[1];

    if (!state || state !== cookieState) {
      return res.status(400).send("Error de seguridad: state inválido.");
    }

    const redirectUri = BASE_URL + "/tiktok/callback";
    const data = await exchangeCodeForToken(code, redirectUri);

    storeTokenData(data);

    if (data.refresh_token) {
      await persistRefreshToken(data.refresh_token);
    }

    res.send(`
      <h1>Las 3 Yemas 🥚</h1>
      <h2>✅ TikTok conectado correctamente</h2>
      <p>La autorización fue completada y el refresh token quedó guardado
      (${RENDER_API_KEY && RENDER_SERVICE_ID ? "vía Render API" : "en disco local, revisa MANUAL_AUTOMATIZACION.md"}).</p>

      <p>
        <a href="/tiktok/test">
          <button>Publicar prueba en TikTok</button>
        </a>
      </p>
    `);
  } catch (err) {
    console.error("TikTok callback error:", err.message);
    res.status(500).send("Error al conectar con TikTok. Revisa los logs de Render.");
  }
});

// Botón manual de prueba (deja el comportamiento original, pero reutiliza
// la lógica compartida y ya no depende de que el token siga en memoria).
app.get("/tiktok/test", async (req, res) => {
  try {
    const result = await publishToTikTok({
      imageUrl:
        "https://las3yemas-glitch.github.io/las3yemas/publicidad/01_semana.jpg",
      privacyLevel: PRIVACY_LEVEL,
    });

    res.send(`
      <h1>Las 3 Yemas 🥚</h1>
      <h2>✅ Publicación enviada a TikTok</h2>
      <p>Modo: ${PRIVACY_LEVEL}.</p>
      <p>ID de publicación: ${result?.data?.publish_id || "(sin id)"}</p>
      <p>Espera 1 minuto y revisa el resultado final:
        <a href="/tiktok/last-status?id=${encodeURIComponent(result?.data?.publish_id || "")}">ver estado</a></p>
    `);
  } catch (err) {
    console.error("TikTok publish error:", err.message);

    if (err.message.includes("refresh token")) {
      return res.send(`
        <h2>Primero debemos conectar TikTok</h2>
        <a href="/tiktok/login"><button>Conectar TikTok</button></a>
      `);
    }

    res.status(400).send(`
      <h2>La publicación de prueba no se pudo completar.</h2>
      <p>${err.message}</p>
      <p>Revisa los logs de Render para más detalle.</p>
    `);
  }
});

// Consulta el estado final de la última publicación (TikTok la procesa en
// segundo plano; "init" ok no garantiza que se haya publicado).
app.get("/tiktok/last-status", async (req, res) => {
  try {
    const publishId = req.query.id || lastPublishId;
    if (!publishId) {
      return res.json({ ok: false, message: "Aún no hay publicaciones desde que arrancó el servidor. Usa /tiktok/last-status?id=<publish_id>." });
    }
    const accessToken = await getValidAccessToken();
    const r = await fetch("https://open.tiktokapis.com/v2/post/publish/status/fetch/", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json; charset=UTF-8",
      },
      body: JSON.stringify({ publish_id: publishId }),
    });
    const data = await r.json();
    res.json({ publish_id: publishId, status: data?.data?.status, fail_reason: data?.data?.fail_reason, error: data?.error?.code });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Endpoint automático: lo llama el workflow diario de GitHub Actions.
// Requiere el header Authorization: Bearer <TIKTOK_AUTOMATION_SECRET>.
app.post("/tiktok/publish", requireAutomationSecret, async (req, res) => {
  try {
    const imageUrl = getTodayImageUrl();
    const result = await publishToTikTok({
      imageUrl,
      privacyLevel: PRIVACY_LEVEL,
    });

    res.json({
      ok: true,
      publish_id: result?.data?.publish_id || null,
      imageUrl,
      privacyLevel: PRIVACY_LEVEL,
    });
  } catch (err) {
    console.error("TikTok automated publish error:", err.message);
    res.status(500).json({ ok: false, error: err.message });
  }
});

const PORT = process.env.PORT || 3000;

app.listen(PORT, async () => {
  console.log(`Servidor iniciado en puerto ${PORT}`);

  const persisted = await loadPersistedRefreshToken();
  if (persisted) {
    tokenState.refreshToken = persisted;
    logSafe("tiktok:startup:refresh_token_loaded", {
      source: process.env.TIKTOK_REFRESH_TOKEN ? "env" : "disk",
    });
  } else {
    logSafe("tiktok:startup:no_refresh_token", {
      message: "Se requiere autorizar manualmente en /tiktok/login.",
    });
  }
});
