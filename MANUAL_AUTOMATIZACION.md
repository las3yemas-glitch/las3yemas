# Automatización de redes sociales — Las 3 Yemas

Este documento explica cómo funciona la automatización completa (Instagram, Facebook y TikTok),
qué hacer si algo falla, y **qué cosas no tocar**.

Última actualización de este documento: ver fecha del commit que lo introduce.

## 1. Resumen del flujo diario

Todo se dispara desde `.github/workflows/publicidad-diaria.yml`, que corre automáticamente
todos los días a las 13:00 UTC (10:00 en Chile continental, hora de invierno; 09:00 en horario
de verano) y también se puede ejecutar manualmente desde GitHub → Actions → "Publicidad diaria
Las 3 Yemas" → **Run workflow**.

Pasos del workflow, en orden:

1. Elige la imagen del día (`publicidad/01_semana.png` … `07_semana.png`, lunes a domingo).
2. La copia a `publicidad/instagram-<run_id>.png` y la sube al repo (para que quede publicada
   por GitHub Pages con una URL nueva y sin caché).
3. Espera a que esa URL responda 200 (hasta 2.5 minutos).
4. Publica en **Instagram** usando `graph.instagram.com` y el secret `INSTAGRAM_ACCESS_TOKEN`.
5. Publica en **Facebook** usando `graph.facebook.com` y el secret `FACEBOOK_PAGE_ACCESS_TOKEN`.
6. Publica en **TikTok** llamando a un endpoint del servicio de Render (`/tiktok/publish`),
   protegido por el secret `TIKTOK_AUTOMATION_SECRET`. Este paso usa `continue-on-error: true`:
   si TikTok falla, Instagram y Facebook ya se publicaron igual y el workflow no se marca
   como roto por eso (pero sí queda visible en el log del paso).

TikTok usa las imágenes semanales fijas (`01_semana.png`…`07_semana.png`), no la copia con
`run_id` que se genera para Instagram/Facebook, porque esas son las únicas URLs que deberían
quedar cubiertas por la verificación de dominio de TikTok. Ver sección 4.

## 2. Instagram y Facebook — no se tocó nada

El código y los secrets de Instagram y Facebook siguen exactamente igual que antes. Esta
automatización de TikTok se agregó **al final** del mismo workflow, sin modificar los pasos
anteriores. Si algo se rompe en Instagram o Facebook después de este cambio, no debería tener
relación con esto — revisa primero si cambiaron los tokens de esas plataformas (suelen expirar).

## 3. TikTok — cómo quedó armado

### 3.1 Servidor (Render, servicio `las3yemas-tiktok`)

`server.js` ahora expone:

- `GET /tiktok/login` y `GET /tiktok/callback`: flujo OAuth manual, **solo hace falta usarlo
  una vez** (o cuando el refresh token se invalide por completo, algo que no debería pasar en
  operación normal).
- `GET /tiktok/test`: botón de prueba manual, publica ya mismo la imagen `01_semana.png`.
- `GET /tiktok/status`: estado de salud, **sin datos sensibles** — dice si hay token válido,
  cómo se está persistiendo el refresh token, y cuál es la imagen que le tocaría publicar hoy.
  Útil para revisar sin arriesgar nada.
- `POST /tiktok/publish`: el que llama el workflow diario. Requiere el header
  `Authorization: Bearer <TIKTOK_AUTOMATION_SECRET>`. Publica automáticamente la imagen
  semanal que corresponde al día.

### 3.2 Persistencia del token (para no reautorizar a mano en cada reinicio)

TikTok entrega un `access_token` (dura ~24h) y un `refresh_token` que **rota cada vez que se
usa**. El servidor:

1. Al arrancar, intenta cargar el refresh token desde (en este orden): la variable de entorno
   `TIKTOK_REFRESH_TOKEN`, o un archivo local de respaldo (`.data/tiktok-token.json`, solo
   sobrevive a un reinicio simple, no a un redeploy).
2. Cuando necesita un access token nuevo, lo pide con el refresh token que tiene.
3. Si TikTok le devuelve un refresh token nuevo, intenta guardarlo llamando a la **API de
   Render** (`PUT /v1/services/{id}/env-vars`) para actualizar la variable
   `TIKTOK_REFRESH_TOKEN` del propio servicio. Así, en el próximo reinicio o redeploy, el
   servidor arranca con el token correcto sin que nadie tenga que tocar nada.

Esto **solo funciona si configuras `RENDER_API_KEY` y `RENDER_SERVICE_ID`** como variables de
entorno del servicio (ver sección 5, es la única configuración manual imprescindible). Si no
las configuras, el servidor sigue funcionando con el respaldo en disco, pero si Render mueve el
servicio a un contenedor nuevo (redeploy, cambio de plan, etc.) vas a tener que reautorizar a
mano en `/tiktok/login` una vez más.

Nota importante: actualizar variables de entorno en Render normalmente dispara un redeploy del
servicio. Como el refresh solo ocurre cuando llega una publicación (como mucho una vez al día),
esto en la práctica es un redeploy diario, no algo constante. Si Render cambió su API desde que
se escribió este código, revisa `api-docs.render.com` — el código está aislado en la función
`persistRefreshTokenToRender` de `server.js` y falla de forma segura (sin cortar la publicación)
si la llamada no funciona.

### 3.2b Modo borrador (activo por defecto)

Desde el 27-09-2026 el servidor usa `TIKTOK_POST_MODE=MEDIA_UPLOAD` (valor por defecto): cada día
TikTok recibe la foto y el texto como **borrador en la bandeja de entrada** de la cuenta
`las3yemitas`. La dueña de la cuenta abre la app de TikTok, entra a la notificación / bandeja,
toca **Publicar** y elige "Todos". Así las publicaciones pueden ser públicas aunque la app siga
en Sandbox. En `/tiktok/last-status` el estado final correcto de este modo es
`SEND_TO_USER_INBOX`.

Cuando TikTok apruebe la app para publicar en público, se puede volver a la publicación 100%
automática agregando en Render `TIKTOK_POST_MODE=DIRECT_POST` y
`TIKTOK_PRIVACY_LEVEL=PUBLIC_TO_EVERYONE`.

### 3.3 Nivel de privacidad (Sandbox vs. producción)

Mientras la app de TikTok esté en modo Sandbox / "cliente no auditado", **solo se puede publicar
con `privacy_level: SELF_ONLY`** (visible solo para la propia cuenta). Esto es una restricción
de TikTok, no del código. El código lee esto de la variable `TIKTOK_PRIVACY_LEVEL` (por defecto
`SELF_ONLY`), así que el día que TikTok apruebe la app para audiencia pública, solo hay que
cambiar esa variable en Render (por ejemplo a `PUBLIC_TO_EVERYONE`) — no hace falta tocar código.
Para eso, hay que pasar por el proceso de revisión de la app en TikTok Developers (solicitud de
"Content Posting API" para audiencia pública), que es un trámite manual con TikTok, no algo que
se resuelva desde el repo.

## 4. `url_ownership_unverified` — RESUELTO (27-09-2026)

La app de TikTok tiene dos ambientes con verificaciones de dominio **separadas**: Production y
Sandbox ("Las 3 Yemas Pruebas", el que usa el servidor). Production ya estaba verificado, pero el
Sandbox nunca lo estuvo: esa era la causa del error.

Se resolvió así:

1. En TikTok Developers → app → Sandbox "Las 3 Yemas Pruebas" → Content Posting API → Verify
   domains → URL prefix `https://las3yemas-glitch.github.io/las3yemas/`.
2. Se publicó en la raíz del repo el archivo `tiktokP5C0HmZ0gHsdjeDANNvEpCew8GjryOew.txt`
   (PR #1, fusionado).
3. TikTok lo verificó ("Verified") y se guardaron los cambios del Sandbox.

**No borres** `tiktokP5C0HmZ0gHsdjeDANNvEpCew8GjryOew.txt` (Sandbox) ni el archivo de Production.
Los archivos `tiktok88EYk...txt` y `tiktokVWxE1...txt` son de intentos anteriores; uno de ellos
corresponde a la verificación de Production, así que conviene dejarlos. Si algún día creas un
Sandbox nuevo o cambias de dominio, habrá que repetir este proceso con el código nuevo que dé TikTok.

## 5. Configuración manual imprescindible (una sola vez)

### En Render (servicio `las3yemas-tiktok`), agregar como variables de entorno:

| Variable | Para qué | Cómo se obtiene |
|---|---|---|
| `TIKTOK_AUTOMATION_SECRET` | Protege `/tiktok/publish` para que solo GitHub Actions pueda dispararlo | Generar un valor aleatorio largo, por ejemplo con `openssl rand -hex 32` |
| `RENDER_API_KEY` | Para que el servidor pueda persistir el refresh token nuevo automáticamente | Render Dashboard → Account Settings → API Keys |
| `RENDER_SERVICE_ID` | Identifica el servicio a actualizar | Aparece en la URL del servicio en el dashboard de Render (`srv-...`) |
| `TIKTOK_PRIVACY_LEVEL` (opcional) | Nivel de privacidad de la publicación | Dejar en `SELF_ONLY` hasta que TikTok apruebe la app para público |

**No se necesita tocar `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` ni `RENDER_EXTERNAL_URL`** —
ya existen y siguen funcionando igual.

### En GitHub (repo `las3yemas-glitch/las3yemas`):

- **Settings → Secrets and variables → Actions → Secrets**: agregar `TIKTOK_AUTOMATION_SECRET`
  con el **mismo valor** que pusiste en Render.
- **Settings → Secrets and variables → Actions → Variables**: agregar `RENDER_TIKTOK_URL` con
  la URL pública del servicio, por ejemplo `https://las3yemas-tiktok.onrender.com`.

### Autorización inicial de TikTok (una sola vez, o si el refresh token se invalida del todo):

1. Abre `https://<tu-servicio>.onrender.com/tiktok/login`.
2. Inicia sesión con la cuenta `las3yemitas` y autoriza la app.
3. Confirma en `/tiktok/status` que `hasRefreshTokenAvailable` es `true`.

## 6. Qué probar después de aplicar estos cambios

Ya que esta sesión no tuvo acceso de red a Render ni a la API de TikTok para probar en vivo,
prueba en este orden:

1. `GET /tiktok/status` → confirma que el servidor levantó bien y qué modo de persistencia usa.
2. `GET /tiktok/test` → intenta una publicación manual real en Sandbox (SELF_ONLY).
3. Si el paso 2 funciona, ejecuta el workflow manualmente (`workflow_dispatch`) y revisa el log
   del paso "Publicar en TikTok".

## 7. Qué NO tocar

- No cambies el `client_key` (`sbawns5v9whht47tl3`) ni los scopes
  (`user.info.basic,video.upload,video.publish`) a menos que vuelvas a crear la app en TikTok
  Developers.
- No borres `tiktok-demo.html`, `privacy.html` ni `terms.html` — TikTok los usa para validar la
  app (páginas de privacidad/términos y demo de login exigidas por su revisión).
- No cambies `post_mode: DIRECT_POST` ni `source: PULL_FROM_URL` sin revisar antes la
  documentación vigente de la Content Posting API — hay combinaciones que TikTok rechaza según
  el estado de auditoría de la app.
- No pongas nunca `TIKTOK_CLIENT_SECRET`, `TIKTOK_AUTOMATION_SECRET`, `RENDER_API_KEY` ni ningún
  access/refresh token directamente en el código o en un commit. Todo eso vive únicamente como
  variable de entorno en Render y como secret en GitHub Actions.
- El archivo `github/workflows/marketing.yml` (sin el punto, dentro de una carpeta `github/`
  suelta) **no lo ejecuta GitHub Actions** — solo reconoce `.github/workflows/`. Es inofensivo
  pero puede confundir; se puede borrar cuando quieras, no se tocó en este cambio.

## 8. Recuperación ante errores comunes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `url_ownership_unverified` | Verificación de dominio no confirmada en el portal de TikTok, o código desactualizado | Ver sección 4 |
| `unaudited_client_can_only_post_to_private_accounts` | La cuenta de TikTok dejó de ser privada, o `TIKTOK_PRIVACY_LEVEL` no es `SELF_ONLY` mientras la app sigue en Sandbox | Vuelve a poner la cuenta en privado, o revisa la variable |
| El workflow dice "RENDER_TIKTOK_URL no está configurado" | Falta la variable en GitHub Actions | Agrega la variable (sección 5) |
| El workflow dice `HTTP 401` en el paso de TikTok | El secret `TIKTOK_AUTOMATION_SECRET` no coincide entre Render y GitHub | Iguala ambos valores |
| `/tiktok/publish` responde "No hay refresh token disponible" | Nunca se hizo la autorización inicial, o Render perdió el token porque no estaban configuradas `RENDER_API_KEY`/`RENDER_SERVICE_ID` | Repite `/tiktok/login` y confirma la configuración de la sección 5 |
| Instagram o Facebook dejan de publicar | No relacionado con este cambio — revisa expiración de `INSTAGRAM_ACCESS_TOKEN` / `FACEBOOK_PAGE_ACCESS_TOKEN` | Renovar esos tokens en Meta for Developers |
