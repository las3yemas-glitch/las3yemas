# Integración campaña las3yemas_20261003

Repositorio `las3yemas-glitch/las3yemas`. Todo se publica desde `.github/workflows/publicidad-diaria.yml`
(cron `0 13 * * *` = 10:00 America/Santiago en horario de verano; el día se calcula en hora de Chile).

## Estado

| Formato | Estado | Interruptor en `publicidad/campana-activa.json` |
|---|---|---|
| Feed IG + FB (5–11 oct) | **Activo** | `activa`, `fecha_inicio`, `fecha_fin` |
| Foto TikTok (borrador) | **Activo** con la pieza del día | — |
| Stories IG + FB | **En pausa hasta aprobación** | `canales_story: ["instagram", "facebook"]` |
| Reels IG + FB + TikTok (borrador) | **En pausa hasta aprobación** | `reels.activos: true` + IDs en `reels.aprobados` |

Fuera del 5–11 de octubre vuelve la rotación habitual `publicidad/0N_semana.png` con su leyenda.

## Calendario propuesto (10:00 de Chile)

| Fecha | Feed IG+FB | Foto TikTok | Story IG+FB | Reel IG+FB+TikTok |
|---|---|---|---|---|
| lun 05 | Frescura que llega a tu mesa | ídem (JPG) | 01 frescura | — |
| mar 06 | Así empiezan los buenos días | ídem | 02 buenos días | **L3Y-REEL-01 El sonido de la frescura** |
| mié 07 | De Las 3 Yemas a tu puerta | ídem | 03 a tu puerta | — |
| jue 08 | Frescura que se nota | ídem | 04 frescura que se nota | **L3Y-REEL-02 El desayuno** |
| vie 09 | ¿Ya tienes huevos para el finde? | ídem | 05 finde | — |
| sáb 10 | Sábado sabe mejor así | ídem | 06 sábado | **L3Y-REEL-03 Misión: no quedarse sin huevos** |
| dom 11 | Reserva los de esta semana | ídem | 07 reserva | — |

Las Stories y Reels de días ya pasados al aprobarse no se recuperan solos (el selector solo mira el día de hoy).

## Archivos y requisitos comprobados (documentación oficial de Meta y TikTok, 3-oct-2026)

| Uso | Archivo | Requisito | Comprobado |
|---|---|---|---|
| Feed IG/FB | `01_Feed/*.png` | IG documenta solo JPEG | PNG ya publicado con éxito por el workflow; no se cambió el Feed activo |
| Story IG/FB | `09_Stories_JPG/*.jpg` | JPEG ≤ 8 MB, 9:16 (IG); FB recomienda PNG ≤ 1 MB → se usa JPG | 1080×1920, 0,34–0,48 MB |
| Portada Reel IG | `10_Portadas_JPG/*.jpg` | JPEG ≤ 8 MB | 1080×1920 |
| Reel | `08_Reels/*.mp4` | MP4 H.264, AAC ≤ 48 kHz, 23–60 fps, 3 s–15 min (IG) / 3–90 s (FB), moov al inicio, sin edit lists | 12/15/14 s, 30 fps, 1080×1920, AAC 128 kbps 48 kHz, sin edit lists |
| Foto TikTok | `07_TikTok_JPG/*.jpg` | JPG desde dominio verificado | ya en uso |
| Vídeo TikTok | `08_Reels/*.mp4` | `inbox/video/init` PULL_FROM_URL, scope `video.upload`, dominio verificado | scope ya pedido en `/tiktok/login`; dominio = el mismo de las fotos |

Los MP4 del paquete se ajustaron sin recodificar el vídeo (md5 del vídeo idéntico): solo audio a 128 kbps y sin edit lists.
Hashes originales y nuevos en `08_Reels/manifest_reels.json`. Licencias en `08_Reels/FUENTES_Y_DERECHOS.md`
(tomas de Pexels; no presentarlas como producción propia).

Sticker de enlace en Stories: la API de Instagram no lo ofrece; no se automatiza. Facebook Reels no recibe portada personalizada en esta versión (usa el fotograma que elija Facebook).

## Permisos (no verificables sin usar los tokens)

- Stories y Reels de Instagram: `instagram_business_content_publish` (el mismo que ya publica el Feed) y cuenta profesional.
- Stories y Reels de Facebook: `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` (el Feed de la página ya publica fotos).
- Se comprobarán en la primera ejecución aprobada; si falta un permiso, solo falla ese paso (`continue-on-error`) y queda `fallido`.

## Registro de publicaciones

`publicidad/registro-publicaciones.jsonl` (commit en el repo). Clave `campaña|asset|canal|formato|fecha local`.
Estados `preparado`, `en_curso`, `publicado` (exige ID remoto), `fallido`, `desconocido`.
`en_curso`, `publicado` y `desconocido` bloquean otro intento; ahora también en los días habituales
(el 3-oct se publicó dos veces: ejecución manual + cron atrasado 5 h).

**Resultados desconocidos**: Actions → *Revisar resultados desconocidos* → Run workflow. Solo consulta Instagram y
Facebook (no publica). Si encuentra la publicación la marca `publicado` con su ID; si no aparece, solo la libera
(`fallido`) si se marca la opción. TikTok y Stories de Facebook se revisan a mano.

## Activar lo aprobado

1. Stories: `"canales_story": ["instagram", "facebook"]`.
2. Reels: `"reels": {"activos": true, "aprobados": ["L3Y-REEL-01", ...]}` y revisar `programacion`.
3. Commit en `main`. No hace falta tocar cron, secretos ni Render.

## Reversión

- Pausar formatos nuevos: `canales_story: []`, `reels.activos: false`.
- Pausar campaña: `"activa": false` (vuelve la rotación habitual).
- Volver el código al estado anterior a esta integración: `git revert <commit>` de esta rama (o
  `git checkout 29f579c -- .github/workflows publicidad server.js`). No toca secretos, no borra publicaciones
  remotas, ni el registro, ni imágenes antiguas. Render se redespliega solo desde `main`.

## Pruebas

```
python3 assets/campaigns/las3yemas_20261003/05_Claude/validar_paquete.py
python3 -m unittest publicidad/test_seleccionar.py -v
python3 publicidad/seleccionar.py calendario --forzar-nuevos
```
