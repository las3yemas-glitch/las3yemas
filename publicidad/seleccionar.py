"""Selector de la pieza diaria y registro durable de publicaciones.

Lo usa .github/workflows/publicidad-diaria.yml. No hace llamadas de red ni
lee secretos: solo decide qué imagen y leyenda corresponden al día local
(America/Santiago) y lleva el historial en publicidad/registro-publicaciones.jsonl,
que el workflow guarda con commit en el repositorio.

Subcomandos:
  elegir      [--fecha AAAA-MM-DD] [--github-output]
  registrar   --canal C --estado E [--remote-id ID] [--detalle TXT] --asset A --fecha F
  calendario  [--desde AAAA-MM-DD] [--dias 7] [--forzar-activa]
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

# Rotación histórica (igual que el case del workflow antes de la campaña).
IMAGEN_HISTORICA = "publicidad/{:02d}_semana.png"
LEYENDA_HISTORICA = (
    "🥚 Las 3 Yemas 💗 Huevos frescos y contenido útil para ti. 🚚 Repartimos en "
    "Viña del Mar, Valparaíso, Quilpué, Belloto y Villa Alemana. #Las3Yemas #HuevosFrescos"
)

ESTADOS = ("preparado", "en_curso", "publicado", "fallido", "desconocido")
# Estados que impiden volver a publicar la misma clave. "desconocido" y
# "en_curso" exigen revisar el historial remoto antes de reintentar a mano.
BLOQUEAN = {"en_curso", "publicado", "desconocido"}


def cargar_config(ruta=CONFIG):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def cargar_manifest(config):
    return json.loads((RAIZ / config["manifest"]).read_text(encoding="utf-8"))


def carpeta_campana(config):
    # manifest.json vive en <campaña>/05_Claude/
    return (RAIZ / config["manifest"]).parent.parent


def ruta_asset(config, asset):
    return (carpeta_campana(config) / asset["file"]).relative_to(RAIZ).as_posix()


def fecha_local(ahora=None, zona="America/Santiago"):
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    return ahora.astimezone(ZoneInfo(zona)).date()


def campana_vigente(config, fecha, forzar_activa=False):
    if not (config.get("activa") or forzar_activa):
        return False
    inicio = dt.date.fromisoformat(config["fecha_inicio"])
    fin = dt.date.fromisoformat(config["fecha_fin"])
    return inicio <= fecha <= fin


def clave(campana, asset_id, canal, fecha):
    return f"{campana}|{asset_id}|{canal}|{fecha.isoformat()}"


def leer_registro(ruta=REGISTRO):
    """Último estado por clave."""
    estados = {}
    ruta = Path(ruta)
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                fila = json.loads(linea)
                estados[fila["clave"]] = fila
    return estados


def registrar(campana, asset_id, canal, fecha, estado, remote_id="", detalle="",
              ruta=REGISTRO):
    if estado not in ESTADOS:
        raise ValueError(f"Estado inválido: {estado}")
    if estado == "publicado" and not remote_id:
        raise ValueError("'publicado' exige el ID remoto de la publicación")
    fila = {
        "clave": clave(campana, asset_id, canal, fecha),
        "campana": campana,
        "asset_id": asset_id,
        "canal": canal,
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


def elegir(fecha, config=None, ruta_registro=REGISTRO, forzar_activa=False):
    config = config or cargar_config()
    dia = fecha.isoweekday()  # 1 = lunes ... 7 = domingo
    if not campana_vigente(config, fecha, forzar_activa):
        return {
            "MODO": "historico",
            "FECHA_LOCAL": fecha.isoformat(),
            "IMAGEN": IMAGEN_HISTORICA.format(dia),
            "CAPTION": LEYENDA_HISTORICA,
            "CAMPANA": "",
            "ASSET_ID": "",
            "STORY": "",
            "PUBLICAR_INSTAGRAM": "true",
            "PUBLICAR_FACEBOOK": "true",
        }

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
    estados = leer_registro(ruta_registro)
    salida = {
        "MODO": "campana",
        "FECHA_LOCAL": fecha.isoformat(),
        "IMAGEN": ruta_asset(config, feed),
        "CAPTION": feed["caption"],
        "CAMPANA": campana,
        "ASSET_ID": feed["id"],
        "STORY": ruta_asset(config, story),
    }
    for canal in ("instagram", "facebook"):
        previo = estados.get(clave(campana, feed["id"], canal, fecha))
        habilitado = canal in config.get("canales_feed", [])
        libre = previo is None or previo["estado"] not in BLOQUEAN
        salida[f"PUBLICAR_{canal.upper()}"] = "true" if habilitado and libre else "false"
    return salida


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

    r = sub.add_parser("registrar")
    r.add_argument("--canal", required=True)
    r.add_argument("--estado", required=True, choices=ESTADOS)
    r.add_argument("--asset", required=True)
    r.add_argument("--fecha", required=True)
    r.add_argument("--remote-id", default="")
    r.add_argument("--detalle", default="")

    c = sub.add_parser("calendario")
    c.add_argument("--desde")
    c.add_argument("--dias", type=int, default=7)
    c.add_argument("--forzar-activa", action="store_true")

    a = p.parse_args(argv)
    config = cargar_config()

    if a.cmd == "elegir":
        fecha = dt.date.fromisoformat(a.fecha) if a.fecha else fecha_local(zona=config["zona_horaria"])
        datos = elegir(fecha, config)
        if a.github_output:
            escribir_github_output(datos)
        for k, v in datos.items():
            print(f"{k}={v}")
    elif a.cmd == "registrar":
        fila = registrar(config["campana_id"], a.asset, a.canal,
                         dt.date.fromisoformat(a.fecha), a.estado, a.remote_id, a.detalle)
        print(f"{fila['clave']} -> {fila['estado']}")
    elif a.cmd == "calendario":
        desde = dt.date.fromisoformat(a.desde or config["fecha_inicio"])
        for i in range(a.dias):
            f = desde + dt.timedelta(days=i)
            d = elegir(f, config, forzar_activa=a.forzar_activa)
            print(f"{f.isoformat()} {f.strftime('%a')} {d['MODO']:9} feed={d['IMAGEN']} "
                  f"story={d['STORY'] or '-'} IG={d['PUBLICAR_INSTAGRAM']} FB={d['PUBLICAR_FACEBOOK']}")


if __name__ == "__main__":
    sys.exit(main())
