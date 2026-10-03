"""Revisa en Instagram/Facebook las publicaciones "en_curso" o "desconocido".

Solo hace consultas GET (no publica). Lo usa .github/workflows/conciliar.yml.
Si encuentra la publicación de esa fecha (misma leyenda o, en Stories, mismo
día), la registra como "publicado" con su ID remoto. Si no la encuentra, solo la
marca "fallido" cuando se pide explícitamente (--marcar-no-encontrados), para
permitir reintentarla. Los tokens llegan por variables de entorno y nunca se
imprimen. TikTok no permite listar borradores: se revisa a mano en la app.
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seleccionar as sel  # noqa: E402

PAGE_ID = "1349788938213993"
ZONA = ZoneInfo("America/Santiago")


def get_json(url, params):
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=60) as r:
        return json.load(r)


def leyenda_esperada(fila, config):
    if fila["campana"] == sel.CAMPANA_HABITUAL:
        return sel.LEYENDA_HISTORICA
    if fila["formato"] == "reel":
        reels = sel.cargar_reels(config)["assets"]
        return next(r["caption"] for r in reels if r["id"] == fila["asset_id"])
    if fila["formato"] == "story":
        return None  # las Stories no llevan leyenda
    return next(a["caption"] for a in sel.cargar_manifest(config)["assets"] if a["id"] == fila["asset_id"])


def fecha_de(marca):
    """'2026-10-05T13:02:11+0000' -> fecha en Chile."""
    marca = marca.replace("+0000", "+00:00")
    return dt.datetime.fromisoformat(marca).astimezone(ZONA).date().isoformat()


def buscar(fila, publicaciones, leyenda):
    """publicaciones: [{'id', 'texto', 'fecha', 'tipo'}] ya normalizadas."""
    tipo = {"feed": "FEED", "story": "STORY", "reel": "REELS"}[fila["formato"]]
    for p in publicaciones:
        if p["fecha"] != fila["fecha_local"] or p["tipo"] != tipo:
            continue
        if leyenda is None or (p["texto"] or "").strip() == leyenda.strip():
            return p["id"]
    return None


def publicaciones_instagram(token):
    yo = get_json("https://graph.instagram.com/me", {"fields": "id", "access_token": token})["id"]
    media = get_json(f"https://graph.instagram.com/{yo}/media",
                     {"fields": "id,caption,media_product_type,timestamp", "limit": 50, "access_token": token})
    salida = [{"id": m["id"], "texto": m.get("caption"), "fecha": fecha_de(m["timestamp"]),
               "tipo": m.get("media_product_type", "FEED")} for m in media.get("data", [])]
    try:
        historias = get_json(f"https://graph.instagram.com/{yo}/stories",
                             {"fields": "id,timestamp", "access_token": token})
    except Exception as err:  # noqa: BLE001 - el error no incluye el token
        print(f"Aviso: no se pudieron listar Stories de Instagram ({err.__class__.__name__})")
        historias = {}
    salida += [{"id": m["id"], "texto": None, "fecha": fecha_de(m["timestamp"]), "tipo": "STORY"}
               for m in historias.get("data", [])]
    return salida


def publicaciones_facebook(token):
    base = f"https://graph.facebook.com/v26.0/{PAGE_ID}"
    pagina = get_json(base, {"fields": "access_token", "access_token": token}).get("access_token") or token
    posts = get_json(f"{base}/published_posts", {"fields": "id,message,created_time", "limit": 50,
                                                  "access_token": pagina})
    salida = [{"id": p["id"], "texto": p.get("message"), "fecha": fecha_de(p["created_time"]), "tipo": "FEED"}
              for p in posts.get("data", [])]
    reels = get_json(f"{base}/video_reels", {"fields": "id,description,created_time", "limit": 25,
                                             "access_token": pagina})
    salida += [{"id": r["id"], "texto": r.get("description"), "fecha": fecha_de(r["created_time"]),
                "tipo": "REELS"} for r in reels.get("data", [])]
    return salida


def conciliar(pendientes, config, fuentes, marcar_no_encontrados=False, ruta=sel.REGISTRO, salida=print):
    for fila in pendientes:
        if fila["canal"] not in fuentes:
            salida(f"MANUAL  {fila['clave']} ({fila['estado']}): revisar en la app")
            continue
        if fila["canal"] == "facebook" and fila["formato"] == "story":
            salida(f"MANUAL  {fila['clave']} ({fila['estado']}): la API no lista Stories de la página")
            continue
        remote_id = buscar(fila, fuentes[fila["canal"]], leyenda_esperada(fila, config))
        fecha = dt.date.fromisoformat(fila["fecha_local"])
        args = (fila["campana"], fila["asset_id"], fila["canal"], fila["formato"], fecha)
        if remote_id:
            sel.registrar(*args, "publicado", remote_id, "conciliado", ruta=ruta)
            salida(f"PUBLICADO {fila['clave']} -> {remote_id}")
        elif marcar_no_encontrados:
            sel.registrar(*args, "fallido", "", "conciliado: no aparece en la cuenta", ruta=ruta)
            salida(f"NO ESTÁ  {fila['clave']} -> fallido (se puede reintentar)")
        else:
            salida(f"NO ESTÁ  {fila['clave']} sigue {fila['estado']} (usa marcar_no_encontrados para liberar)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--marcar-no-encontrados", action="store_true")
    a = p.parse_args()
    pendientes = sel.pendientes_de_revision()
    if not pendientes:
        print("No hay publicaciones en curso ni desconocidas.")
        return
    fuentes = {}
    for canal, variable, funcion in (("instagram", "INSTAGRAM_ACCESS_TOKEN", publicaciones_instagram),
                                     ("facebook", "FACEBOOK_PAGE_ACCESS_TOKEN", publicaciones_facebook)):
        if not os.environ.get(variable):
            continue
        try:
            fuentes[canal] = funcion(os.environ[variable])
        except Exception as err:  # noqa: BLE001 - solo se muestra el tipo de error, nunca la URL
            print(f"Aviso: no se pudo consultar {canal} ({err.__class__.__name__}); queda para revisión manual")
    conciliar(pendientes, sel.cargar_config(), fuentes, a.marcar_no_encontrados)


if __name__ == "__main__":
    main()
