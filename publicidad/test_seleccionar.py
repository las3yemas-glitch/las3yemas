"""Pruebas sin red: python3 -m unittest publicidad/test_seleccionar.py -v"""
import datetime as dt
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import conciliar  # noqa: E402
import seleccionar as sel  # noqa: E402

RAIZ = sel.RAIZ
LUNES = dt.date(2026, 10, 5)
CAMP = "las3yemas_20261003"
LEYENDA_ANTERIOR = (
    "🥚 Las 3 Yemas 💗 Huevos frescos y contenido útil para ti. 🚚 Repartimos en Viña del Mar, "
    "Valparaíso, Quilpué, Belloto y Villa Alemana. #Las3Yemas #HuevosFrescos"
)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registro = Path(self.tmp.name) / "registro.jsonl"
        self.config = sel.cargar_config()

    def tearDown(self):
        self.tmp.cleanup()

    def elegir(self, fecha, **kw):
        return sel.elegir(fecha, self.config, ruta_registro=self.registro, **kw)

    def registrar(self, campana, asset, canal, formato, estado, rid="", fecha=LUNES):
        return sel.registrar(campana, asset, canal, formato, fecha, estado, rid, ruta=self.registro)

    def aprobar_todo(self):
        self.config["canales_story"] = ["instagram", "facebook"]
        self.config["reels"]["activos"] = True
        self.config["reels"]["aprobados"] = ["L3Y-REEL-01", "L3Y-REEL-02", "L3Y-REEL-03"]


class Paquete(Base):
    def test_validador_del_paquete(self):
        carpeta = sel.carpeta_campana(self.config)
        r = subprocess.run([sys.executable, "05_Claude/validar_paquete.py"], cwd=carpeta,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_rutas_y_hashes(self):
        manifest = sel.cargar_manifest(self.config)
        tipos = {}
        for a in manifest["assets"]:
            ruta = RAIZ / sel.ruta_asset(self.config, a)
            self.assertEqual(hashlib.sha256(ruta.read_bytes()).hexdigest(), a["sha256"])
            self.assertNotIn("\n", a["caption"])
            self.assertNotRegex(a["caption"].lower(), r"\$|gratis|descuento|oferta|stock")
            tipos[a["type"]] = tipos.get(a["type"], 0) + 1
        self.assertEqual(tipos, {"feed": 7, "story": 7, "reel_cover": 3, "commercial_extra": 2})

    def test_jpg_para_meta_y_tiktok(self):
        c = sel.carpeta_campana(self.config)
        for carpeta, n, alto in (("07_TikTok_JPG", 9, 1350), ("09_Stories_JPG", 7, 1920), ("10_Portadas_JPG", 3, 1920)):
            jpgs = sorted((c / carpeta).glob("*.jpg"))
            self.assertEqual(len(jpgs), n, carpeta)
            for j in jpgs:
                datos = j.read_bytes()
                self.assertEqual(datos[:3], b"\xff\xd8\xff")
                self.assertLess(len(datos), 8_000_000)  # límite Instagram
                self.assertIn(struct.pack(">HH", alto, 1080), datos[:2000])  # SOF: alto, ancho

    def test_reels_cumplen_especificacion(self):
        reels = sel.cargar_reels(self.config)
        self.assertEqual(len(reels["assets"]), 3)
        for r in reels["assets"]:
            datos = (RAIZ / r["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(datos).hexdigest(), r["sha256"])
            self.assertEqual(datos[4:8], b"ftyp")
            self.assertLess(datos.find(b"moov"), datos.find(b"mdat"))  # moov al inicio
            self.assertNotIn(b"elst", datos[:datos.find(b"mdat")])    # sin edit lists
            self.assertIn(b"avc1", datos)
            self.assertIn(b"mp4a", datos)
            self.assertLess(len(datos), 100_000_000)
            self.assertTrue((RAIZ / r["cover_jpg"]).is_file())
            self.assertGreaterEqual(r["duration_seconds"], 3)
            self.assertLessEqual(r["duration_seconds"], 90)  # límite Reels de Facebook

    def test_nombres_historicos_intactos(self):
        for d in range(1, 8):
            self.assertTrue((RAIZ / f"publicidad/{d:02d}_semana.png").is_file())


class Seleccion(Base):
    def test_formatos_nuevos_en_pausa(self):
        # Con los interruptores apagados: solo Feed + foto TikTok, sin Stories ni Reels.
        self.config["canales_story"] = []
        self.config["reels"]["activos"] = False
        for i in range(7):
            d = self.elegir(LUNES + dt.timedelta(days=i))
            self.assertEqual(d["MODO"], "campana")
            self.assertEqual((d["PUBLICAR_STORY_INSTAGRAM"], d["PUBLICAR_STORY_FACEBOOK"]), ("false", "false"))
            self.assertEqual(d["REEL_ID"], "")
            self.assertNotIn("|story", d["PENDIENTES"])
            self.assertNotIn("|reel", d["PENDIENTES"])

    def test_siete_dias_feed_y_story_mismo_dia(self):
        self.aprobar_todo()
        manifest = {a["id"]: a for a in sel.cargar_manifest(self.config)["assets"]}
        for i in range(7):
            f = LUNES + dt.timedelta(days=i)
            d = self.elegir(f)
            self.assertEqual(manifest[d["ASSET_ID"]]["day"], f.isoweekday())
            self.assertEqual(manifest[d["STORY_ID"]]["day"], f.isoweekday())
            self.assertEqual(manifest[d["STORY_ID"]]["type"], "story")
            self.assertEqual(Path(d["STORY"]).stem, Path(manifest[d["STORY_ID"]]["file"]).stem)
            self.assertTrue(d["STORY"].endswith(".jpg"))
            self.assertEqual(Path(d["TIKTOK_IMAGEN"]).stem, Path(d["IMAGEN"]).stem)
            self.assertEqual((d["PUBLICAR_STORY_INSTAGRAM"], d["PUBLICAR_STORY_FACEBOOK"]), ("true", "true"))

    def test_reels_solo_en_su_fecha_y_con_aprobacion(self):
        self.config["reels"]["activos"] = True
        self.config["reels"]["aprobados"] = ["L3Y-REEL-02"]
        dias = {}
        for i in range(7):
            f = LUNES + dt.timedelta(days=i)
            dias[f.isoformat()] = self.elegir(f)["REEL_ID"]
        self.assertEqual(dias["2026-10-08"], "L3Y-REEL-02")
        self.assertEqual(dias["2026-10-06"], "")  # programado pero no aprobado
        self.assertEqual(sum(1 for v in dias.values() if v), 1)

    def test_reel_lleva_su_portada(self):
        self.aprobar_todo()
        esperado = {"2026-10-06": ("L3Y-REEL-01", "01_sonido"), "2026-10-08": ("L3Y-REEL-02", "02_el_desayuno"),
                    "2026-10-10": ("L3Y-REEL-03", "03_mision")}
        for fecha, (reel, nombre) in esperado.items():
            d = self.elegir(dt.date.fromisoformat(fecha))
            self.assertEqual(d["REEL_ID"], reel)
            self.assertIn(nombre, d["REEL_VIDEO"])
            self.assertTrue(d["REEL_VIDEO"].endswith(".mp4"))
            self.assertIn(nombre, d["REEL_PORTADA"])
            self.assertTrue(d["REEL_PORTADA"].endswith(".jpg"))
            self.assertEqual(sum(d[f"PUBLICAR_REEL_{c}"] == "true" for c in ("INSTAGRAM", "FACEBOOK", "TIKTOK")), 3)

    def test_reels_desactivados_no_salen_aunque_esten_aprobados(self):
        self.config["reels"]["activos"] = False
        self.config["reels"]["aprobados"] = ["L3Y-REEL-01"]
        self.assertEqual(self.elegir(dt.date(2026, 10, 6))["REEL_ID"], "")

    def test_portadas_y_extras_no_entran_al_feed(self):
        self.aprobar_todo()
        for i in range(7):
            d = self.elegir(LUNES + dt.timedelta(days=i))
            self.assertNotIn("Portadas", d["IMAGEN"] + d["STORY"])
            self.assertNotIn("04_Extras", d["IMAGEN"])

    def test_sustitucion_explicita_con_extra(self):
        self.config["sustituciones"] = {"2026-10-07": "L3Y-20261003-18"}
        self.assertEqual(self.elegir(dt.date(2026, 10, 7))["ASSET_ID"], "L3Y-20261003-18")
        self.config["sustituciones"] = {"2026-10-07": "L3Y-20261003-15"}
        with self.assertRaises(ValueError):
            self.elegir(dt.date(2026, 10, 7))

    def test_regreso_al_contenido_habitual(self):
        for f in (dt.date(2026, 10, 4), dt.date(2026, 10, 12), dt.date(2026, 10, 18)):
            d = self.elegir(f)
            self.assertEqual(d["MODO"], "historico")
            self.assertEqual(d["IMAGEN"], f"publicidad/{f.isoweekday():02d}_semana.png")
            self.assertEqual(d["CAPTION"], LEYENDA_ANTERIOR)
            self.assertEqual(d["TIKTOK_IMAGEN"], "")
            self.assertEqual(d["PUBLICAR_STORY_INSTAGRAM"], "false")
        self.config["activa"] = False
        self.assertEqual(self.elegir(LUNES)["MODO"], "historico")

    def test_limites_del_dia_local(self):
        for f in (dt.date(2026, 10, 5), dt.date(2026, 10, 11), dt.date(2027, 4, 5), dt.date(2027, 6, 7)):
            ahora = dt.datetime(f.year, f.month, f.day, 13, tzinfo=dt.timezone.utc)
            self.assertEqual(sel.fecha_local(ahora), f)
        # 23:59 de Chile del domingo 11 = 02:59 UTC del lunes 12: sigue siendo el 11.
        self.assertEqual(sel.fecha_local(dt.datetime(2026, 10, 12, 2, 59, tzinfo=dt.timezone.utc)),
                         dt.date(2026, 10, 11))
        self.assertEqual(sel.fecha_local(dt.datetime(2026, 10, 12, 3, 0, tzinfo=dt.timezone.utc)),
                         dt.date(2026, 10, 12))
        # El ejecutor atrasado (como el 3-oct, 18:18 UTC) sigue en el mismo día local.
        self.assertEqual(sel.fecha_local(dt.datetime(2026, 10, 3, 18, 18, tzinfo=dt.timezone.utc)),
                         dt.date(2026, 10, 3))


class Registro(Base):
    def test_estados_que_bloquean(self):
        for estado, esperado in (("en_curso", "false"), ("publicado", "false"),
                                 ("desconocido", "false"), ("fallido", "true"), ("preparado", "true")):
            self.registro.unlink(missing_ok=True)
            self.registrar(CAMP, "L3Y-20261003-01", "instagram", "feed", estado,
                           "123" if estado == "publicado" else "")
            d = self.elegir(LUNES)
            self.assertEqual(d["PUBLICAR_INSTAGRAM"], esperado, estado)
            self.assertEqual(d["PUBLICAR_FACEBOOK"], "true")

    def test_publicado_exige_id_remoto(self):
        with self.assertRaises(ValueError):
            self.registrar(CAMP, "L3Y-20261003-01", "instagram", "feed", "publicado")

    def test_formato_en_la_clave(self):
        self.aprobar_todo()
        self.registrar(CAMP, "L3Y-20261003-08", "instagram", "story", "publicado", "9")
        d = self.elegir(LUNES)
        self.assertEqual(d["PUBLICAR_STORY_INSTAGRAM"], "false")
        self.assertEqual(d["PUBLICAR_INSTAGRAM"], "true")
        self.assertEqual(d["PUBLICAR_STORY_FACEBOOK"], "true")

    def test_filas_antiguas_sin_formato(self):
        self.aprobar_todo()
        with open(self.registro, "w", encoding="utf-8") as f:
            for canal, asset in (("instagram_story", "L3Y-20261003-08"), ("tiktok", "L3Y-20261003-01")):
                f.write(json.dumps({"clave": f"{CAMP}|{asset}|{canal}|2026-10-05", "campana": CAMP,
                                    "asset_id": asset, "canal": canal, "fecha_local": "2026-10-05",
                                    "estado": "desconocido"}) + "\n")
        d = self.elegir(LUNES)
        self.assertEqual(d["PUBLICAR_STORY_INSTAGRAM"], "false")
        self.assertEqual(d["PUBLICAR_TIKTOK"], "false")

    def test_dias_habituales_tambien_evitan_duplicados(self):
        # Caso real del 3-oct: ejecución manual y luego la programada atrasada.
        sabado = dt.date(2026, 10, 3)
        primera = self.elegir(sabado)
        self.assertEqual(primera["PUBLICAR_INSTAGRAM"], "true")
        for item in primera["PENDIENTES"].split():
            campana, asset, canal, formato = item.split("|")
            self.registrar(campana, asset, canal, formato, "publicado", "id", fecha=sabado)
        segunda = self.elegir(sabado)
        self.assertEqual((segunda["PUBLICAR_INSTAGRAM"], segunda["PUBLICAR_FACEBOOK"], segunda["PUBLICAR_TIKTOK"]),
                         ("false", "false", "false"))
        self.assertEqual(segunda["PENDIENTES"], "")


class FlujoCLI(Base):
    """Dos ejecuciones del workflow el mismo día, por la línea de comandos."""

    def correr(self, *args, salida=None):
        cfg = Path(self.tmp.name) / "config.json"
        self.aprobar_todo()
        cfg.write_text(json.dumps(self.config), encoding="utf-8")
        env = dict(os.environ, PUBLICIDAD_CONFIG=str(cfg), PUBLICIDAD_REGISTRO=str(self.registro),
                   PYTHONIOENCODING="utf-8")
        if salida:
            env["GITHUB_OUTPUT"] = str(salida)
        r = subprocess.run([sys.executable, str(RAIZ / "publicidad/seleccionar.py"), *args],
                           env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def elegir_cli(self, fecha, nombre):
        out = Path(self.tmp.name) / nombre
        out.write_text("", encoding="utf-8")
        self.correr("elegir", "--fecha", fecha, "--github-output", salida=out)
        return dict(l.split("=", 1) for l in out.read_text(encoding="utf-8").splitlines())

    def test_segunda_ejecucion_no_repite_nada(self):
        o1 = self.elegir_cli("2026-10-06", "o1")  # martes: Feed + Story + Reel 01
        self.assertEqual(len(o1["PENDIENTES"].split()), 8)
        self.correr("iniciar", "--fecha", "2026-10-06", "--pendientes", o1["PENDIENTES"])
        o2 = self.elegir_cli("2026-10-06", "o2")
        self.assertEqual(o2["PENDIENTES"], "")
        self.assertTrue(all(o2[k] == "false" for k in o2 if k.startswith("PUBLICAR_")))

    def test_recuperar_desconocido(self):
        o1 = self.elegir_cli("2026-10-06", "o1")
        self.correr("registrar", "--campana", CAMP, "--asset", o1["ASSET_ID"], "--canal", "instagram",
                    "--formato", "feed", "--fecha", "2026-10-06", "--estado", "desconocido")
        pend = self.correr("pendientes")
        self.assertIn('"estado": "desconocido"', pend)
        self.assertEqual(self.elegir_cli("2026-10-06", "o2")["PUBLICAR_INSTAGRAM"], "false")
        # La conciliación lo encontró como fallido -> se libera para reintentar.
        self.correr("registrar", "--campana", CAMP, "--asset", o1["ASSET_ID"], "--canal", "instagram",
                    "--formato", "feed", "--fecha", "2026-10-06", "--estado", "fallido")
        self.assertEqual(self.elegir_cli("2026-10-06", "o3")["PUBLICAR_INSTAGRAM"], "true")


class Conciliacion(Base):
    def setUp(self):
        super().setUp()
        self.aprobar_todo()
        self.lineas = []

    def pendientes(self, *filas):
        for f in filas:
            self.registrar(*f, "desconocido", fecha=dt.date(2026, 10, 6))
        return sel.pendientes_de_revision(self.registro)

    def test_encuentra_feed_y_reel_por_leyenda_y_fecha(self):
        pend = self.pendientes((CAMP, "L3Y-20261003-02", "instagram", "feed"),
                               ("L3Y-20261003-REELS", "L3Y-REEL-01", "instagram", "reel"),
                               (CAMP, "L3Y-20261003-09", "instagram", "story"))
        feed_cap = sel.cargar_manifest(self.config)["assets"][1]["caption"]
        ig = [
            {"id": "A", "texto": feed_cap, "fecha": "2026-10-05", "tipo": "FEED"},   # otro día
            {"id": "B", "texto": feed_cap, "fecha": "2026-10-06", "tipo": "FEED"},
            {"id": "C", "texto": "El sonido de la frescura. Haz tu pedido en www.las3yemas.cl.",
             "fecha": "2026-10-06", "tipo": "REELS"},
        ]
        conciliar.conciliar(pend, self.config, {"instagram": ig}, ruta=self.registro, salida=self.lineas.append)
        estados = sel.leer_registro(self.registro)
        ids = {k.split("|")[1] + "|" + k.split("|")[3]: v["remote_id"] for k, v in estados.items()
               if v["estado"] == "publicado"}
        self.assertEqual(ids, {"L3Y-20261003-02|feed": "B", "L3Y-REEL-01|reel": "C"})
        self.assertTrue(any("NO ESTÁ" in l and "story" in l for l in self.lineas))
        self.assertEqual(len(sel.pendientes_de_revision(self.registro)), 1)

    def test_no_encontrado_solo_se_libera_si_se_pide(self):
        pend = self.pendientes((CAMP, "L3Y-20261003-02", "facebook", "feed"),
                               (CAMP, "L3Y-20261003-02", "tiktok", "feed"))
        conciliar.conciliar(pend, self.config, {"facebook": []}, ruta=self.registro, salida=self.lineas.append)
        self.assertEqual(len(sel.pendientes_de_revision(self.registro)), 2)
        self.assertTrue(any(l.startswith("MANUAL") and "tiktok" in l for l in self.lineas))
        conciliar.conciliar(pend, self.config, {"facebook": []}, marcar_no_encontrados=True,
                            ruta=self.registro, salida=self.lineas.append)
        restantes = sel.pendientes_de_revision(self.registro)
        self.assertEqual([f["canal"] for f in restantes], ["tiktok"])

    def test_fecha_remota_en_hora_de_chile(self):
        self.assertEqual(conciliar.fecha_de("2026-10-07T02:30:00+0000"), "2026-10-06")


class Workflows(unittest.TestCase):
    def leer(self, nombre):
        return (RAIZ / ".github/workflows" / nombre).read_text(encoding="utf-8")

    def test_disparadores_intactos(self):
        self.assertNotIn("curl", self.leer("marketing.yml"))
        self.assertNotIn("schedule", self.leer("marketing.yml"))
        self.assertIn('cron: "0 13 * * *"', self.leer("publicidad-diaria.yml"))
        self.assertNotIn("schedule", self.leer("conciliar.yml"))
        self.assertFalse((RAIZ / ".github/workflows/reels.yml").exists())

    def test_conciliar_no_publica(self):
        fuente = (RAIZ / "publicidad/conciliar.py").read_text(encoding="utf-8")
        self.assertNotIn("POST", fuente)
        self.assertNotIn("media_publish", fuente)
        self.assertNotIn("print(token", fuente)

    def test_selector_sin_red(self):
        fuente = (RAIZ / "publicidad/seleccionar.py").read_text(encoding="utf-8")
        for modulo in ("urllib", "requests", "socket", "http.client", "subprocess"):
            self.assertNotIn(f"import {modulo}", fuente)

    def test_ningun_secreto_en_texto(self):
        diaria = self.leer("publicidad-diaria.yml")
        for linea in diaria.splitlines():
            if "secrets." in linea:
                self.assertRegex(linea.strip(), r"^[A-Z_]+: \$\{\{ secrets\.[A-Z_]+ \}\}$")


if __name__ == "__main__":
    unittest.main()
