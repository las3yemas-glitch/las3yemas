# Integración campaña las3yemas_20261003

Commit inicial: `34d448b` (origin/main). Rama: `integracion/campana-20261003`.
Estado: **activada el 2026-10-03** para 2026-10-05 a 2026-10-11 (`publicidad/campana-activa.json` → `"activa": true`).
Fuera de esas fechas, o con `"activa": false`, el workflow publica exactamente lo mismo que antes (`publicidad/0N_semana.png` + la leyenda de siempre).

## Qué publica cada canal

| Canal | Quién decide la pieza | Formato | Campaña |
|---|---|---|---|
| Instagram Feed | `publicidad-diaria.yml` → `publicidad/seleccionar.py` | PNG por URL de GitHub Pages | Sí |
| Facebook Página | `publicidad-diaria.yml` → `publicidad/seleccionar.py` | PNG por URL de GitHub Pages | Sí |
| Story Instagram | `publicidad-diaria.yml` (`media_type=STORIES`) | PNG 1080×1920 | Sí (permiso por comprobar en la 1.ª ejecución) |
| Story Facebook | `publicidad-diaria.yml` (`/photo_stories`) | PNG 1080×1920 | Sí (permiso por comprobar en la 1.ª ejecución) |
| TikTok | el workflow pide a `server.js` (Render) el JPG de `07_TikTok_JPG/` | JPG, borrador MEDIA_UPLOAD | Sí, cuando Render despliegue la nueva versión |
| Reels Instagram | `reels.yml` (solo manual) | MP4 real + portada PNG | Cuando haya vídeo aprobado |

`marketing.yml` solo imprime un texto (dispatch manual); `github/workflows/marketing.yml` está fuera de `.github` y no se ejecuta. Ninguno publica.

## Calendario propuesto (revisar antes de activar)

Cron sin cambios: `0 13 * * *` = 10:00 America/Santiago (UTC−3, horario de verano). El día se calcula en hora de Chile.

| Fecha | Feed (IG + FB + borrador TikTok) | Story (IG + FB) |
|---|---|---|
| lun 2026-10-05 | L3Y-20261003-01 Frescura que llega a tu mesa | L3Y-20261003-08 |
| mar 2026-10-06 | L3Y-20261003-02 Así empiezan los buenos días | L3Y-20261003-09 |
| mié 2026-10-07 | L3Y-20261003-03 De Las 3 Yemas a tu puerta | L3Y-20261003-10 |
| jue 2026-10-08 | L3Y-20261003-04 Frescura que se nota | L3Y-20261003-11 |
| vie 2026-10-09 | L3Y-20261003-05 ¿Ya tienes huevos para el finde? | L3Y-20261003-12 |
| sáb 2026-10-10 | L3Y-20261003-06 Sábado sabe mejor así | L3Y-20261003-13 |
| dom 2026-10-11 | L3Y-20261003-07 Reserva los de esta semana | L3Y-20261003-14 |

Fuera de ese rango vuelve sola la rotación anterior. Leyendas: las del `manifest.json`, sin cambios.

- **Extras** L3Y-20261003-18/19: reserva. Solo salen si se agrega una sustitución explícita, p. ej. `"sustituciones": {"2026-10-07": "L3Y-20261003-18"}`. Nunca suman publicaciones.
- **Portadas** L3Y-20261003-15/16/17: `pendiente_video` en `campana-activa.json`. El selector no las elige.

## Riesgos y pendientes

1. **Stories**: nunca se han probado con estas cuentas. Si el token no tiene permiso, solo falla ese paso (continue-on-error), el Feed sigue y el registro queda `fallido` (se reintenta en la siguiente ejecución manual del mismo día).
2. **Reels**: no hay MP4. Para publicar uno: subir el vídeo al repo (p. ej. `assets/campaigns/las3yemas_20261003/08_Reels_MP4/01_sonido_de_la_frescura.mp4`), poner en `publicidad/campana-activa.json` → `portadas_reels.<ID>`: `"video": "<ruta>"`, `"aprobado": true`, y lanzar **Actions → Reel Las 3 Yemas → Run workflow** eligiendo la portada. Guiones en `05_Claude/INSTRUCCIONES_CLAUDE.md`.
3. **TikTok**: `07_TikTok_JPG/` son los mismos PNG del Feed/Extras convertidos a JPG (calidad 95, mismo tamaño). Si Render aún no desplegó el nuevo `server.js`, ignora la imagen pedida y manda su `0N_semana.jpg` (comprobar `acceptsRequestedImage: true` en `/tiktok/status`). Sigue siendo borrador: hay que publicarlo desde la app.
4. **Concurrencia**: el workflow no tiene `concurrency` (se respetó). Dos ejecuciones simultáneas podrían elegir antes de que una registre `en_curso`; en la práctica el segundo `git push` falla y detiene esa ejecución antes de publicar.
5. Facebook y TikTok tienen `continue-on-error`: un “success” en GitHub no prueba que se publicaron. Instagram sí corta el job si falla.

## Registro de publicaciones

`publicidad/registro-publicaciones.jsonl` (commit en el repo, no en el runner).
Clave: `campaña|asset|canal|fecha local`; canales `instagram`, `facebook`, `instagram_story`, `facebook_story`, `tiktok`, `instagram_reel`. Estados: `preparado`, `en_curso`, `publicado` (exige ID remoto), `fallido`, `desconocido`.
`en_curso`, `publicado` y `desconocido` bloquean otro intento ese día. Ante `desconocido`/`en_curso`: revisar Instagram/Facebook a mano; si no se publicó, agregar una línea `fallido` con `python3 publicidad/seleccionar.py registrar ... --estado fallido` antes de relanzar.

## Activar (paso separado, requiere aprobación)

1. Confirmar fecha de inicio/fin en `publicidad/campana-activa.json`.
2. Cambiar `"activa": true`, fusionar la rama en `main` y hacer push.
3. Opcional: comprobar después del primer día que `registro-publicaciones.jsonl` tenga `publicado` con ID.

## Reversión

- Pausar sin revertir: `"activa": false` en `publicidad/campana-activa.json` (vuelve la rotación anterior).
- Volver el selector al commit inicial: `git checkout 34d448b -- .github/workflows/publicidad-diaria.yml` y commit. No toca secretos ni borra publicaciones remotas; los assets y el registro pueden quedar en el repo sin efecto.

## Pruebas

```
python3 assets/campaigns/las3yemas_20261003/05_Claude/validar_paquete.py
python3 -m unittest publicidad/test_seleccionar.py -v
python3 publicidad/seleccionar.py calendario --forzar-activa
```
