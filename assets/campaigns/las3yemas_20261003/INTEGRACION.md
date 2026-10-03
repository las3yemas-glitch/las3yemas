# Integración campaña las3yemas_20261003

Commit inicial: `34d448b` (origin/main). Rama: `integracion/campana-20261003`.
Estado: **preparada, sin activar** (`publicidad/campana-activa.json` → `"activa": false`).
Mientras esté inactiva, el workflow publica exactamente lo mismo que antes (`publicidad/0N_semana.png` + la leyenda de siempre).

## Qué publica cada canal

| Canal | Quién decide la pieza | Formato | Campaña |
|---|---|---|---|
| Instagram Feed | `publicidad-diaria.yml` → `publicidad/seleccionar.py` | PNG por URL de GitHub Pages | Sí, al activar |
| Facebook Página | `publicidad-diaria.yml` → `publicidad/seleccionar.py` | PNG por URL de GitHub Pages | Sí, al activar |
| TikTok | `server.js` en Render (`0N_semana.jpg`, borrador MEDIA_UPLOAD) | JPG | No (sin cambios) |
| Stories IG/FB | — | — | Bloqueado |
| Reels | — | — | Portadas pendientes de vídeo |

`marketing.yml` solo imprime un texto (dispatch manual); `github/workflows/marketing.yml` está fuera de `.github` y no se ejecuta. Ninguno publica.

## Calendario propuesto (revisar antes de activar)

Cron sin cambios: `0 13 * * *` = 10:00 America/Santiago (UTC−3, horario de verano). El día se calcula en hora de Chile.

| Fecha | Feed (IG + FB) | Story (preparada, bloqueada) |
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

## Bloqueos

1. **Stories**: el workflow solo llama a `graph.instagram.com/<id>/media` sin `media_type=STORIES` y a Facebook `/photos`. No hay implementación ni permiso comprobado para Stories. Las 7 piezas están listas en `02_Stories/`.
2. **Reels**: no hay MP4. Las portadas esperan vídeo real aprobado (guiones en `05_Claude/INSTRUCCIONES_CLAUDE.md`).
3. **TikTok**: lo controla `server.js` en Render, con su propia selección por día UTC y JPG. Llevar la campaña a TikTok exige derivados JPG, cambio en `server.js` y redeploy aprobados. El registro de duplicados no cubre TikTok: un dispatch manual repetido vuelve a enviar un borrador.
4. **Concurrencia**: el workflow no tiene `concurrency` (se respetó). Dos ejecuciones simultáneas podrían elegir antes de que una registre `en_curso`; en la práctica el segundo `git push` falla y detiene esa ejecución antes de publicar.
5. Facebook y TikTok tienen `continue-on-error`: un “success” en GitHub no prueba que se publicaron. Instagram sí corta el job si falla.

## Registro de publicaciones

`publicidad/registro-publicaciones.jsonl` (commit en el repo, no en el runner).
Clave: `campaña|asset|canal|fecha local`. Estados: `preparado`, `en_curso`, `publicado` (exige ID remoto), `fallido`, `desconocido`.
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
