"""Selector de la pieza diaria y registro durable de publicaciones.

Lo usa .github/workflows/publicidad-diaria.yml. No hace llamadas de red ni
lee secretos: solo decide qué publicar el día local (America/Santiago) y lleva
el historial en publicidad/registro-publicaciones.jsonl, que el workflow guarda
con commit en el repositorio.

Subcomandos:
  elegir      [--fecha AAAA-MM-DD] [--github-output]
  iniciar     --fecha F --pendientes "campana|asset|canal|formato ..."
  registrar   --campana C --asset A --canal C --formato F --fecha F --estado E [--remote-id ID] [--detalle TXT]
  pendientes  lista las claves en_curso o desconocido (para conciliar.py)
  calendario  [--desde AAAA-MM-DD] [--dias 7] [--forzar-activa] [--forzar-nuevos]

Clave del registro: campaña|asset|canal|formato|fecha local.
Canales: instagram, facebook, tiktok. Formatos: feed, story, reel.
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
# Las variables de entorno solo se usan en pruebas para apuntar a copias temporales.
CONFIG = Path(os.environ.get("PUBLICIDAD_CONFIG", RAIZ / "publicidad/campana-activa.json"))
REGISTRO = Path(os.environ.get("PUBLICIDAD_REGISTRO", RAIZ / "publicidad/registro-publicaciones.jsonl"))

# Rotación habitual (igual que el case del workflow antes de la campaña).
CAMPANA_HABITUAL = "habitual"
IMAGEN_HISTORICA = "publicidad/{:02d}_semana.png"
LEYENDA_HISTORICA = (
    "🥚 Las 3 Yemas 💗 Huevos frescos y contenido útil para ti. 🚚 Repartimos en "
    "Viña del Mar, Valparaíso, Quilpué, Belloto y Villa Alemana. #Las3Yemas #HuevosFrescos"
)

ESTADOS = ("preparado", "en_curso", "publicado", "fallido", "desconocido")
# Estados que impiden volver a publicar la misma clave. "desconocido" y
# "en_curso" exigen revisar el historial remoto (conciliar.py) antes de reintentar.
BLOQUEAN = {"en_curso", "publicado", "desconocido"}
CANALES = ("instagram", "facebook", "tiktok")
FORMATOS = ("feed", "story", "reel")


def cargar_config(ruta=CONFIG):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def cargar_manifest(config):
    return json.loads((RAIZ / config["manifest"]).read_text(encoding="utf-8"))


def cargar_reels(config):
    return json.loads((RAIZ / config["reels"]["manifest"]).read_text(encoding="utf-8"))


def carpeta_campana(config):
    # manifest.json vive en <campaña>/05_Claude/
    return (RAIZ / config["manifest"]).parent.parent


def ruta_asset(config, asset):
    return (carpeta_campana(config) / asset["file"]).relative_to(RAIZ).as_posix()


def ruta_jpg(config, asset, carpeta):
    """JPG equivalente del PNG (Instagram y TikTok foto solo aceptan JPEG)."""
    jpg = carpeta_campana(config) / carpeta / (Path(asset["file"]).stem + ".jpg")
    if not jpg.is_file():
        raise FileNotFoundError(f"Falta el JPG: {jpg}")
    return jpg.relative_to(RAIZ).as_posix()


def fecha_local(ahora=None, zona="America/Santiago"):
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    return ahora.astimezone(ZoneInfo(zona)).date()


def campana_vigente(config, fecha, forzar_activa=False):
    if not (config.get("activa") or forzar_activa):
        return False
    inicio = dt.date.fromisoformat(config["fecha_inicio"])
    fin = dt.date.fromisoformat(config["fecha_fin"])
    return inicio <= fecha <= fin


def clave(campana, asset_id, canal, formato, fecha):
    return f"{campana}|{asset_id}|{canal}|{formato}|{fecha.isoformat()}"


def _normalizar(fila):
    """Filas escritas antes de existir 'formato' (canal instagram_story, etc.)."""
    if "formato" not in fila:
        canal, _, formato = fila["canal"].partition("_")
        fila = dict(fila, canal=canal, formato=formato or "feed")
        fila["clave"] = clave(fila["campana"], fila["asset_id"], fila["canal"], fila["formato"],
                              dt.date.fromisoformat(fila["fecha_local"]))
    return fila


def leer_registro(ruta=REGISTRO):
    """Último estado por clave."""
    estados = {}
    ruta = Path(ruta)
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                fila = _normalizar(json.loads(linea))
                estados[fila["clave"]] = fila
    return estados


def registrar(campana, asset_id, canal, formato, fecha, estado, remote_id="", detalle="",
              ruta=REGISTRO):
    if estado not in ESTADOS:
        raise ValueError(f"Estado inválido: {estado}")
    if canal not in CANALES or formato not in FORMATOS:
        raise ValueError(f"Canal/formato inválido: {canal}/{formato}")
    if estado == "publicado" and not remote_id:
        raise ValueError("'publicado' exige el ID remoto de la publicación")
    fila = {
        "clave": clave(campana, asset_id, canal, formato, fecha),
        "campana": campana,
        "asset_id": asset_id,
        "canal": canal,
        "formato": formato,
        "fecha_local": fecha.isoformat(),
        "estado": estado,
        "remote_id": remote_id or None,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "registrado_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "detalle": detalle or None,
    }
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return fila


def elegir(fecha, config=None, ruta_registro=REGISTRO, forzar_activa=False, forzar_nuevos=False):
    """forzar_nuevos solo existe para pruebas/calendario: simula Stories y Reels aprobados."""
    config = config or cargar_config()
    dia = fecha.isoweekday()  # 1 = lunes ... 7 = domingo
    estados = leer_registro(ruta_registro)
    pendientes = []

    def decidir(habilitado, campana, asset_id, canal, formato):
        previo = estados.get(clave(campana, asset_id, canal, formato, fecha))
        ok = habilitado and (previo is None or previo["estado"] not in BLOQUEAN)
        if ok:
            pendientes.append(f"{campana}|{asset_id}|{canal}|{formato}")
        return "true" if ok else "false"

    salida = {"FECHA_LOCAL": fecha.isoformat()}
    if not campana_vigente(config, fecha, forzar_activa):
        campana, asset = CAMPANA_HABITUAL, f"{dia:02d}_semana"
        salida.update({
            "MODO": "historico",
            "IMAGEN": IMAGEN_HISTORICA.format(dia),
            "CAPTION": LEYENDA_HISTORICA,
            "CAMPANA": campana,
            "ASSET_ID": asset,
            "STORY": "",
            "STORY_ID": "",
            "TIKTOK_IMAGEN": "",
            "PUBLICAR_INSTAGRAM": decidir(True, campana, asset, "instagram", "feed"),
            "PUBLICAR_FACEBOOK": decidir(True, campana, asset, "facebook", "feed"),
            "PUBLICAR_STORY_INSTAGRAM": "false",
            "PUBLICAR_STORY_FACEBOOK": "false",
            "PUBLICAR_TIKTOK": decidir(True, campana, asset, "tiktok", "feed"),
        })
    else:
        manifest = cargar_manifest(config)
        por_id = {a["id"]: a for a in manifest["assets"]}
        feed = next(a for a in manifest["assets"] if a["type"] == "feed" and a["day"] == dia)
        story = next(a for a in manifest["assets"] if a["type"] == "story" and a["day"] == dia)

        # Sustitución explícita (p. ej. un extra comercial) solo si está configurada.
        sustituto = config.get("sustituciones", {}).get(fecha.isoformat())
        if sustituto:
            feed = por_id[sustituto]
            if feed["type"] not in ("feed", "commercial_extra"):
                raise ValueError(f"{sustituto} no es una pieza de Feed")

        campana = config["campana_id"]
        canales_story = ["instagram", "facebook"] if forzar_nuevos else config.get("canales_story", [])
        salida.update({
            "MODO": "campana",
            "IMAGEN": ruta_asset(config, feed),
            "CAPTION": feed["caption"],
            "CAMPANA": campana,
            "ASSET_ID": feed["id"],
            "STORY": ruta_jpg(config, story, "09_Stories_JPG"),
            "STORY_ID": story["id"],
            "TIKTOK_IMAGEN": ruta_jpg(config, feed, "07_TikTok_JPG"),
        })
        for canal in ("instagram", "facebook"):
            salida[f"PUBLICAR_{canal.upper()}"] = decidir(
                canal in config.get("canales_feed", []), campana, feed["id"], canal, "feed")
        for canal in ("instagram", "facebook"):
            salida[f"PUBLICAR_STORY_{canal.upper()}"] = decidir(
                canal in canales_story, campana, story["id"], canal, "story")
        salida["PUBLICAR_TIKTOK"] = decidir(True, campana, feed["id"], "tiktok", "feed")

    salida.update(elegir_reel(fecha, config, decidir, forzar_nuevos))
    salida["PENDIENTES"] = " ".join(pendientes)
    return salida


def programacion_reels(config, forzar_nuevos=False):
    reels = config.get("reels", {})
    if forzar_nuevos:
        return reels.get("programacion", {}), set(reels.get("programacion", {}).values())
    if not reels.get("activos"):
        return {}, set()
    return reels.get("programacion", {}), set(reels.get("aprobados", []))


def elegir_reel(fecha, config, decidir, forzar_nuevos=False):
    """Reel programado para esa fecha, solo si los Reels están activos y aprobados."""
    vacio = {"REEL_CAMPANA": "", "REEL_ID": "", "REEL_VIDEO": "", "REEL_PORTADA": "", "REEL_CAPTION": "",
             "PUBLICAR_REEL_INSTAGRAM": "false", "PUBLICAR_REEL_FACEBOOK": "false",
             "PUBLICAR_REEL_TIKTOK": "false"}
    programacion, aprobados = programacion_reels(config, forzar_nuevos)
    reel_id = programacion.get(fecha.isoformat())
    if not reel_id or reel_id not in aprobados:
        return vacio
    reels = cargar_reels(config)
    reel = next(r for r in reels["assets"] if r["id"] == reel_id)
    campana = reels["campaign_id"]
    canales = ["instagram", "facebook", "tiktok"] if forzar_nuevos else config["reels"].get("canales", [])
    salida = {"REEL_CAMPANA": campana, "REEL_ID": reel_id, "REEL_VIDEO": reel["file"],
              "REEL_PORTADA": reel["cover_jpg"], "REEL_CAPTION": reel["caption"]}
    for canal in ("instagram", "facebook", "tiktok"):
        salida[f"PUBLICAR_REEL_{canal.upper()}"] = decidir(canal in canales, campana, reel_id, canal, "reel")
    return salida


def pendientes_de_revision(ruta=REGISTRO):
    return [f for f in leer_registro(ruta).values() if f["estado"] in ("en_curso", "desconocido")]


def escribir_github_output(datos):
    for k, v in datos.items():
        if "\n" in v:
            raise ValueError(f"{k} no puede tener saltos de línea")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        for k, v in datos.items():
            f.write(f"{k}={v}\n")


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("elegir")
    e.add_argument("--fecha")
    e.add_argument("--github-output", action="store_true")

    i = sub.add_parser("iniciar")
    i.add_argument("--fecha", required=True)
    i.add_argument("--pendientes", default="")

    r = sub.add_parser("registrar")
    r.add_argument("--campana", required=True)
    r.add_argument("--asset", required=True)
    r.add_argument("--canal", required=True, choices=CANALES)
    r.add_argument("--formato", required=True, choices=FORMATOS)
    r.add_argument("--fecha", required=True)
    r.add_argument("--estado", required=True, choices=ESTADOS)
    r.add_argument("--remote-id", default="")
    r.add_argument("--detalle", default="")

    sub.add_parser("pendientes")

    c = sub.add_parser("calendario")
    c.add_argument("--desde")
    c.add_argument("--dias", type=int, default=7)
    c.add_argument("--forzar-activa", action="store_true")
    c.add_argument("--forzar-nuevos", action="store_true")

    a = p.parse_args(argv)
    config = cargar_config()

    if a.cmd == "elegir":
        fecha = dt.date.fromisoformat(a.fecha) if a.fecha else fecha_local(zona=config["zona_horaria"])
        datos = elegir(fecha, config)
        if a.github_output:
            escribir_github_output(datos)
        for k, v in datos.items():
            print(f"{k}={v}")
    elif a.cmd == "iniciar":
        fecha = dt.date.fromisoformat(a.fecha)
        for item in a.pendientes.split():
            campana, asset, canal, formato = item.split("|")
            fila = registrar(campana, asset, canal, formato, fecha, "en_curso")
            print(f"{fila['clave']} -> en_curso")
    elif a.cmd == "registrar":
        fila = registrar(a.campana, a.asset, a.canal, a.formato, dt.date.fromisoformat(a.fecha),
                         a.estado, a.remote_id, a.detalle)
        print(f"{fila['clave']} -> {fila['estado']}")
    elif a.cmd == "pendientes":
        for f in pendientes_de_revision():
            print(json.dumps(f, ensure_ascii=False))
    elif a.cmd == "calendario":
        desde = dt.date.fromisoformat(a.desde or config["fecha_inicio"])
        for n in range(a.dias):
            f = desde + dt.timedelta(days=n)
            d = elegir(f, config, forzar_activa=a.forzar_activa, forzar_nuevos=a.forzar_nuevos)
            print(f"{f.isoformat()} {f.strftime('%a')} {d['MODO']:9} feed={Path(d['IMAGEN']).name} "
                  f"story={Path(d['STORY']).name if d['STORY'] else '-'} reel={d['REEL_ID'] or '-'} "
                  f"| {d['PENDIENTES'].replace(d['CAMPANA'] + '|', '')}")


if __name__ == "__main__":
    sys.exit(main())
