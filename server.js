import express from "express";
import crypto from "crypto";

const app = express();

const CLIENT_KEY = process.env.TIKTOK_CLIENT_KEY;
const CLIENT_SECRET = process.env.TIKTOK_CLIENT_SECRET;
const BASE_URL = process.env.RENDER_EXTERNAL_URL;

// Solo para la prueba Sandbox.
// El token queda en memoria y NO se muestra en pantalla.
let tiktokAccessToken = null;

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
  `);
});

app.get("/tiktok/login", (req, res) => {
  const state = crypto.randomBytes(16).toString("hex");
  const redirectUri = BASE_URL + "/tiktok/callback";

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
      return res.status(400).send(
        "Error de seguridad: state inválido."
      );
    }

    const redirectUri = BASE_URL + "/tiktok/callback";

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

    tiktokAccessToken = data.access_token;

    res.send(`
      <h1>Las 3 Yemas 🥚</h1>
      <h2>✅ TikTok conectado correctamente</h2>
      <p>La autorización del Sandbox fue completada.</p>

      <p>
        <a href="/tiktok/test">
          <button>Publicar prueba en TikTok</button>
        </a>
      </p>
    `);

  } catch (err) {
    console.error("TikTok callback error:", err.message);
    res.status(500).send("Error al conectar con TikTok.");
  }
});

app.get("/tiktok/test", async (req, res) => {
  try {
    if (!tiktokAccessToken) {
      return res.send(`
        <h2>Primero debemos conectar TikTok</h2>
        <a href="/tiktok/login">
          <button>Conectar TikTok</button>
        </a>
      `);
    }

    // TikTok exige consultar primero la información
    // del creador antes de realizar Direct Post.
    const creatorResponse = await fetch(
      "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${tiktokAccessToken}`,
          "Content-Type": "application/json; charset=UTF-8"
        },
        body: JSON.stringify({})
      }
    );

    const creatorData = await creatorResponse.json();

    if (
      !creatorResponse.ok ||
      creatorData?.error?.code !== "ok"
    ) {
      console.error(
        "TikTok creator info error:",
        JSON.stringify(creatorData)
      );

      return res.status(400).send(`
        <h2>No se pudo consultar la cuenta de TikTok.</h2>
        <p>Revisa los logs de Render.</p>
      `);
    }

    const privacyOptions =
      creatorData?.data?.privacy_level_options || [];

    // En Sandbox / cliente no auditado usamos SELF_ONLY.
    if (!privacyOptions.includes("SELF_ONLY")) {
      return res.status(400).send(`
        <h2>TikTok no permitió SELF_ONLY para esta cuenta.</h2>
        <p>No se realizó ninguna publicación.</p>
      `);
    }

    const imageUrl =
      "https://las3yemas-glitch.github.io/las3yemas/publicidad/01_semana.png";

    const publishResponse = await fetch(
      "https://open.tiktokapis.com/v2/post/publish/content/init/",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${tiktokAccessToken}`,
          "Content-Type": "application/json; charset=UTF-8"
        },
        body: JSON.stringify({
          post_info: {
            title: "Huevos frescos Las 3 Yemas 🥚",
            description:
              "Huevos frescos con reparto en Viña del Mar, Valparaíso, Quilpué, Belloto y Villa Alemana.",
            privacy_level: "SELF_ONLY",
            disable_comment: false,
            auto_add_music: true
          },
          source_info: {
            source: "PULL_FROM_URL",
            photo_cover_index: 0,
            photo_images: [imageUrl]
          },
          post_mode: "DIRECT_POST",
          media_type: "PHOTO"
        })
      }
    );

    const publishData = await publishResponse.json();

    if (
      !publishResponse.ok ||
      publishData?.error?.code !== "ok"
    ) {
      console.error(
        "TikTok publish error:",
        JSON.stringify(publishData)
      );

      return res.status(400).send(`
        <h2>La publicación de prueba no se pudo iniciar.</h2>
        <p>Revisa los logs de Render para ver la respuesta de TikTok.</p>
      `);
    }

    res.send(`
      <h1>Las 3 Yemas 🥚</h1>
      <h2>✅ Publicación enviada a TikTok</h2>
      <p>TikTok recibió correctamente la solicitud de publicación.</p>
      <p>Modo de prueba: SELF_ONLY.</p>
    `);

  } catch (err) {
    console.error("TikTok publish error:", err.message);
    res.status(500).send(
      "Error al realizar la publicación de prueba."
    );
  }
});

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log(`Servidor iniciado en puerto ${PORT}`);
});
