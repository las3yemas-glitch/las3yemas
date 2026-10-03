# Incorporar la campaña Las 3 Yemas

Trabaja en el repositorio existente de Las 3 Yemas. Este paquete contiene 19 imágenes finales individuales; no son collages. Incorpora los assets a la automatización que ya funciona, preservando secretos, tokens e integraciones.

## Límites obligatorios

- No leer, imprimir, copiar, regenerar, rotar ni cambiar valores de secretos o tokens. Tampoco crear archivos .env con credenciales.
- No crear otra aplicación Meta/TikTok, otra cuenta o un repositorio nuevo.
- No sustituir, redibujar, recolorear ni reinterpretar el logo. El archivo 06_Marca/logo_maestro_original.jpeg se conserva como fuente original.
- No inventar precios, stock, descuentos, horarios ni despacho gratis.
- Zonas de esta campaña: Viña del Mar, Valparaíso, Quilpué, Belloto y Villa Alemana.
- Preservar triggers, cron, permissions, environments, concurrency, dependencias y referencias a secrets de los workflows que funcionan. Cambiar solo la selección de contenido cuando sea necesario y con un diff mínimo.
- Las tres piezas de 03_Portadas_Reels son portadas PNG. No son vídeos y no deben enviarse como Reels ni TikToks de vídeo. Asociarlas a un vídeo real solo cuando exista y esté aprobado.
- No publicar durante pruebas. No reejecutar una publicación con resultado desconocido sin consultar primero el historial remoto.

## Ejecutar de principio a fin

1. Inspecciona el repositorio, AGENTS.md, .github/workflows/marketing.yml, .github/workflows/publicidad-diaria.yml y los scripts que llaman. Verifica cuáles existen realmente. Identifica el workflow activo por canal y el formato que consume; no asumas rutas ni nombres de variables.
2. Registra el commit inicial y los archivos que vas a tocar. Trabaja en una rama de integración y conserva intactos los assets anteriores. No elimines contenido existente.
3. Copia esta carpeta bajo una ruta versionada adecuada, por ejemplo assets/campaigns/las3yemas_20261003/. No sobrescribas los nombres históricos 01–05 que pudieran estar en uso.
4. Ejecuta `python3 05_Claude/validar_paquete.py` desde la raíz de este paquete. Deben existir exactamente 19 assets declarados, todos con dimensiones y hashes correctos.
5. Lee manifest.json: contiene rutas relativas, IDs únicos, leyendas y tipo de pieza. Adapta ese manifest al contrato real del selector existente. No reemplaces todo el workflow para acomodar el paquete.
6. Asegura una rotación de siete días: Feed y Story del mismo día, lunes a domingo. Usa America/Santiago y conserva el horario actual que funcione. El manifest no fija una fecha inicial: usa la próxima semana de campaña configurada en el repositorio; si no hay una, presenta una fecha concreta para revisión antes de activar publicaciones. No alteres el cron por inferir una conversión UTC fija.
7. Trata las dos piezas extra como contenido comercial de reserva. No agregues dos publicaciones inesperadas al calendario diario. Usa una únicamente cuando el selector existente contemple una publicación comercial adicional o sustitución explícita.
8. Publica cada formato solo en los canales que realmente tengan soporte y permisos comprobados. Si Stories no está implementado, deja sus siete piezas listas y registra el bloqueo específico. No fuerces el pipeline de Feed a aceptar Stories. Para Reels deja las portadas vinculables y pendientes de vídeo, sin fabricar un vídeo con una imagen inmóvil.
9. Si el código usa URLs públicas de imágenes, reutiliza el mecanismo ya operativo. No incluyas URLs locales sandbox, temporales, firmadas con caducidad ni credenciales en el manifest de producción. Comprueba acceso al asset mediante la ruta existente.
10. Evita duplicados: reutiliza el registro durable del publicador; clave mínima = ID de campaña + ID de asset + canal + fecha local programada. Marca publicado solo con respuesta exitosa e ID remoto. Distingue preparado / en curso / publicado / fallido / resultado desconocido. Un runner efímero sin persistencia no sirve como historial.
11. Ejecuta pruebas de selección para siete días, resolución de rutas y modo dry-run sin llamadas que publiquen. Verifica que el mismo día no se seleccione dos veces por ejecutar ambos workflows. Conserva el propietario actual de la publicación por canal.
12. Entrega el diff, resultado de validación, calendario concreto, canales habilitados, bloqueos y procedimiento de reversión. La reversión debe devolver el selector al commit inicial sin tocar secretos ni borrar publicaciones remotas.

## Resultado esperado

19 imágenes importadas; siete pares Feed/Story; dos extras de reserva; tres portadas identificadas como portadas; leyendas listas; selección y deduplicación verificadas en dry-run. No afirmes que una publicación o integración funciona sin evidencia real. La autorización de este encargo comprende la preparación de la integración; la activación pública se revisa como paso separado.

## Guiones de referencia para vídeos futuros

Estos guiones acompañan las portadas. El paquete no contiene archivos MP4.

- **El sonido de la frescura, 12 s:** 0–3 s plano macro del huevo y sonido al abrirlo; 3–7 s yema entrando a sartén y chisporroteo; 7–10 s plato terminado; 10–12 s logo original y llamada a pedido. Sin música que tape el sonido del alimento.
- **El desayuno, 15 s:** 0–4 s cocina al amanecer; 4–9 s preparación de huevos y tostadas; 9–12 s desayuno servido; 12–15 s “Todo empieza con un buen huevo”, logo original y web. Música con licencia y luz cálida cinematográfica.
- **Misión: no quedarse sin huevos, 14 s:** 0–3 s caja vacía y pausa dramática; 3–7 s “Pero todavía hay una solución”; 7–11 s bandeja que llega y preparación del desayuno; 11–14 s logo original, “Haz tu pedido” y web. Humor amable y montaje tipo tráiler, sin prometer entrega inmediata.
