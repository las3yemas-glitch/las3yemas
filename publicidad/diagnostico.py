"""Diagnóstico de permisos para Stories y Reels. Solo consultas GET: no publica.

Muestra tipo de cuenta, permisos concedidos y si la cuenta puede publicar.
Nunca imprime tokens: los errores se muestran solo con código y mensaje de Meta.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PAGE_ID = "1349788938213993"
NECESARIOS_FB = ["pages_manage_posts", "pages_read_engagement", "pages_show_list"]
lineas = []


def salida(texto=""):
    print(texto)
    lineas.append(texto)


def get(url, **params):
    try:
        with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=60) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e).get("error", {})
            return None, f"HTTP {e.code} · código {err.get('code')} · {err.get('message', '')[:160]}"
        except Exception:  # noqa: BLE001
            return None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, e.__class__.__name__


def ok(cond):
    return "✅" if cond else "❌"


def instagram(token):
    salida("## Instagram")
    yo, err = get("https://graph.instagram.com/me", fields="user_id,username,account_type", access_token=token)
    if err:
        salida(f"- ❌ No se pudo leer la cuenta: {err}")
        return
    tipo = yo.get("account_type", "?")
    salida(f"- Cuenta: @{yo.get('username')} · tipo **{tipo}** "
           f"{ok(tipo in ('BUSINESS', 'MEDIA_CREATOR'))} (Stories/Reels exigen cuenta profesional)")
    uid = yo.get("user_id") or yo.get("id")
    limite, err = get(f"https://graph.instagram.com/{uid}/content_publishing_limit",
                      fields="quota_usage,config", access_token=token)
    if err:
        salida(f"- ❌ Permiso de publicación (instagram_business_content_publish): {err}")
    else:
        d = (limite.get("data") or [{}])[0]
        salida(f"- ✅ Permiso de publicación (instagram_business_content_publish): "
               f"{d.get('quota_usage', '?')} de {d.get('config', {}).get('quota_total', '?')} publicaciones usadas en 24 h")
    historias, err = get(f"https://graph.instagram.com/{uid}/stories", fields="id,timestamp", access_token=token)
    salida(f"- {ok(not err)} Lectura de Stories: " + (err or f"{len(historias.get('data', []))} Stories activas"))
    media, err = get(f"https://graph.instagram.com/{uid}/media", fields="id,timestamp,media_product_type",
                     limit=4, access_token=token)
    if not err:
        salida("- Últimas publicaciones: " + ", ".join(
            f"{m.get('media_product_type')} {m['timestamp'][:16]}" for m in media.get("data", [])))
    salida("- Nota: la API de Instagram no lista los permisos del token; que la cuenta sea profesional y "
           "tenga permiso de publicación es lo que exige `media_type=STORIES` y `REELS`.")


def facebook(token):
    salida("\n## Facebook")
    yo, err = get("https://graph.facebook.com/v26.0/me", fields="id,name", access_token=token)
    if err:
        salida(f"- ❌ No se pudo leer el token guardado: {err}")
        return
    es_pagina = yo.get("id") == PAGE_ID
    salida(f"- Token guardado: {'de la página' if es_pagina else 'de usuario/usuario del sistema'} ({yo.get('name')})")
    concedidos = set()
    if not es_pagina:
        permisos, err = get("https://graph.facebook.com/v26.0/me/permissions", access_token=token)
        if err:
            salida(f"- ❌ No se pudieron leer los permisos: {err}")
        else:
            concedidos = {p["permission"] for p in permisos.get("data", []) if p.get("status") == "granted"}
            for p in NECESARIOS_FB:
                salida(f"- {ok(p in concedidos)} {p}")
            otros = sorted(concedidos - set(NECESARIOS_FB))
            if otros:
                salida(f"- Otros concedidos: {', '.join(otros)}")
        cuentas, err = get("https://graph.facebook.com/v26.0/me/accounts", fields="id,name,tasks", access_token=token)
        if not err:
            pag = next((c for c in cuentas.get("data", []) if c["id"] == PAGE_ID), None)
            tareas = pag.get("tasks", []) if pag else []
            salida(f"- {ok('CREATE_CONTENT' in tareas)} Tarea CREATE_CONTENT en la página"
                   + (f" ({', '.join(tareas)})" if tareas else " (página no encontrada en el token)"))
    else:
        salida("- Es un token de página: Meta no permite listar sus permisos desde aquí; se prueba con lecturas.")
    pagina, _ = get(f"https://graph.facebook.com/v26.0/{PAGE_ID}", fields="access_token", access_token=token)
    tp = (pagina or {}).get("access_token") or token
    posts, err = get(f"https://graph.facebook.com/v26.0/{PAGE_ID}/published_posts",
                     fields="id,created_time", limit=4, access_token=tp)
    salida(f"- {ok(not err)} Lectura de publicaciones de la página: " + (err or ", ".join(
        p["created_time"][:16] for p in posts.get("data", []))))
    reels, err = get(f"https://graph.facebook.com/v26.0/{PAGE_ID}/video_reels", fields="id", limit=1, access_token=tp)
    salida(f"- {ok(not err)} Acceso a Reels de la página (video_reels): " + (err or "OK"))


def main():
    if os.environ.get("INSTAGRAM_ACCESS_TOKEN"):
        instagram(os.environ["INSTAGRAM_ACCESS_TOKEN"])
    else:
        salida("## Instagram\n- ❌ Falta el secreto INSTAGRAM_ACCESS_TOKEN")
    if os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN"):
        facebook(os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"])
    else:
        salida("\n## Facebook\n- ❌ Falta el secreto FACEBOOK_PAGE_ACCESS_TOKEN")
    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write("# Diagnóstico de permisos (solo lectura)\n\n" + "\n".join(lineas) + "\n")


if __name__ == "__main__":
    sys.exit(main())
