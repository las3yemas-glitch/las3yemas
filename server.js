import express from "express";
import crypto from "crypto";

const app = express();

const CLIENT_KEY = process.env.TIKTOK_CLIENT_KEY;
const CLIENT_SECRET = process.env.TIKTOK_CLIENT_SECRET;

const BASE_URL = process.env.RENDER_EXTERNAL_URL;

app.get("/", (req, res) => {
  res.send(`
    <h1>Las 3 Yemas 🥚</h1>
    <p>Integración TikTok</p>
    <a href="/tiktok/login">
      <button>Conectar con TikTok</button>
    </a>
  `);
});

app.get("/tiktok/login", (req, res) => {
  const state = crypto.randomBytes(16).toString("hex");

  const redirectUri =
    BASE_URL + "/tiktok/callback";

  const params = new URLSearchParams({
    client_key: CLIENT_KEY,
    scope: "user.info.basic,video.upload,video.publish",
    response_type: "code",
    redirect_uri: redirectUri,
    state
  });

  res.cookie("tiktok_state", state, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    maxAge: 10 * 60 * 1000
  });

  res.redirect(
    "https://www.tiktok.com/v2/auth/authorize/?" +
    params.toString()
  );
});

app.get("/tiktok/callback", async (req, res) => {
  try {
    const { code, state, error, error_description } = req.query;

    if (error) {
      return res.status(400).send(
        `TikTok rechazó la autorización: ${error_description || error}`
      );
    }

    const cookieState = req.headers.cookie
      ?.split(";")
      .map(v => v.trim())
      .find(v => v.startsWith("tiktok_state="))
      ?.split("=")[1];

    if (!state || state !== cookieState) {
      return res.status(400).send("Error de seguridad: state inválido.");
    }

    const redirectUri =
      BASE_URL + "/tiktok/callback";

    const body = new URLSearchParams({
      client_key: CLIENT_KEY,
      client_secret: CLIENT_SECRET,
      code,
      grant_type: "authorization_code",
      redirect_uri: redirectUri
    });

    const response = await fetch(
      "https://open.tiktokapis.com/v2/oauth/token/",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded"
        },
        body
      }
    );

    const data = await response.json();

    if (!response.ok || !data.access_token) {
      console.error("TikTok token exchange failed", {
        status: response.status,
        error: data.error,
        error_description: data.error_description
      });

      return res.status(400).send(
        "No se pudo completar la autorización con TikTok."
      );
    }

    res.send(`
      <h1>Las 3 Yemas 🥚</h1>
      <h2>✅ TikTok conectado correctamente</h2>
      <p>La autorización del Sandbox fue completada.</p>
    `);

  } catch (err) {
    console.error("TikTok callback error:", err.message);
    res.status(500).send("Error al conectar con TikTok.");
  }
});

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log(`Servidor iniciado en puerto ${PORT}`);
});
