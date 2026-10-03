"""Pruebas sin red: python3 -m unittest publicidad/test_seleccionar.py -v"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seleccionar as sel  # noqa: E402

RAIZ = sel.RAIZ
LUNES = dt.date(2026, 10, 5)
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
            self.assertTrue(ruta.is_file(), ruta)
            self.assertEqual(hashlib.sha256(ruta.read_bytes()).hexdigest(), a["sha256"])
            self.assertNotIn("\n", a["caption"])
            self.assertNotRegex(a["caption"].lower(), r"\$|gratis|descuento|oferta|stock")
            tipos[a["type"]] = tipos.get(a["type"], 0) + 1
        self.assertEqual(tipos, {"feed": 7, "story": 7, "reel_cover": 3, "commercial_extra": 2})

    def test_nombres_historicos_intactos(self):
        for d in range(1, 8):
            self.assertTrue((RAIZ / f"publicidad/{d:02d}_semana.png").is_file())


class Seleccion(Base):
    def test_siete_dias_feed_y_story_mismo_dia(self):
        self.config["canales_story"] = ["instagram", "facebook"]
        manifest = {a["id"]: a for a in sel.cargar_manifest(self.config)["assets"]}
        vistos = set()
        for i in range(7):
            f = LUNES + dt.timedelta(days=i)
            d = self.elegir(f, forzar_activa=True)
            feed = manifest[d["ASSET_ID"]]
            self.assertEqual(d["MODO"], "campana")
            self.assertEqual(feed["type"], "feed")
            self.assertEqual(feed["day"], f.isoweekday())
            self.assertEqual(Path(d["IMAGEN"]).name[:2], Path(d["STORY"]).name[:2])
            self.assertIn("/02_Stories/", d["STORY"])
            self.assertEqual(d["CAPTION"], feed["caption"])
            self.assertEqual(manifest[d["STORY_ID"]]["type"], "story")
            self.assertEqual(manifest[d["STORY_ID"]]["day"], f.isoweekday())
            self.assertEqual((d["PUBLICAR_STORY_INSTAGRAM"], d["PUBLICAR_STORY_FACEBOOK"]), ("true", "true"))
            jpg = RAIZ / d["TIKTOK_IMAGEN"]
            self.assertTrue(jpg.is_file())
            self.assertEqual(jpg.stem, Path(d["IMAGEN"]).stem)
            self.assertEqual(jpg.read_bytes()[:3], b"\xff\xd8\xff")
            vistos.add(d["ASSET_ID"])
        self.assertEqual(len(vistos), 7)

    def test_portadas_y_extras_no_entran_al_calendario(self):
        for i in range(7):
            d = self.elegir(LUNES + dt.timedelta(days=i), forzar_activa=True)
            self.assertNotIn("03_Portadas_Reels", d["IMAGEN"] + d["STORY"])
            self.assertNotIn("04_Extras", d["IMAGEN"])

    def test_sustitucion_explicita_con_extra(self):
        self.config["sustituciones"] = {"2026-10-07": "L3Y-20261003-18"}
        d = self.elegir(dt.date(2026, 10, 7), forzar_activa=True)
        self.assertEqual(d["ASSET_ID"], "L3Y-20261003-18")
        self.config["sustituciones"] = {"2026-10-07": "L3Y-20261003-15"}
        with self.assertRaises(ValueError):
            self.elegir(dt.date(2026, 10, 7), forzar_activa=True)

    def test_inactiva_repite_rotacion_anterior(self):
        self.config["activa"] = False
        for i in range(7):
            f = LUNES + dt.timedelta(days=i)
            d = self.elegir(f)
            self.assertEqual(d["MODO"], "historico")
            self.assertEqual(d["IMAGEN"], f"publicidad/{f.isoweekday():02d}_semana.png")
            self.assertEqual(d["CAPTION"], LEYENDA_ANTERIOR)
            self.assertEqual((d["PUBLICAR_INSTAGRAM"], d["PUBLICAR_FACEBOOK"]), ("true", "true"))
            # Sin campaña: sin Stories y TikTok con la imagen del servidor.
            self.assertEqual((d["PUBLICAR_STORY_INSTAGRAM"], d["PUBLICAR_STORY_FACEBOOK"]), ("false", "false"))
            self.assertEqual((d["PUBLICAR_TIKTOK"], d["TIKTOK_IMAGEN"]), ("true", ""))

    def test_fuera_de_rango_vuelve_a_historico(self):
        self.config["activa"] = True
        self.assertEqual(self.elegir(dt.date(2026, 10, 4))["MODO"], "historico")
        self.assertEqual(self.elegir(dt.date(2026, 10, 12))["MODO"], "historico")
        self.assertEqual(self.elegir(dt.date(2026, 10, 11))["MODO"], "campana")

    def test_hora_del_cron_en_santiago(self):
        # 13:00 UTC (cron actual) cae el mismo día local con y sin horario de verano.
        for f in (dt.date(2026, 10, 5), dt.date(2026, 10, 11), dt.date(2027, 4, 5), dt.date(2027, 6, 7)):
            ahora = dt.datetime(f.year, f.month, f.day, 13, tzinfo=dt.timezone.utc)
            self.assertEqual(sel.fecha_local(ahora), f)
        # Un disparo manual de noche usa el día de Chile, no el de UTC.
        noche = dt.datetime(2026, 10, 6, 1, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(sel.fecha_local(noche), dt.date(2026, 10, 5))


class Registro(Base):
    def registrar(self, canal, estado, rid=""):
        return sel.registrar("las3yemas_20261003", "L3Y-20261003-01", canal, LUNES, estado, rid,
                             ruta=self.registro)

    def test_estados_que_bloquean(self):
        for estado, esperado in (("en_curso", "false"), ("publicado", "false"),
                                 ("desconocido", "false"), ("fallido", "true")):
            self.registro.unlink(missing_ok=True)
            self.registrar("instagram", estado, "123" if estado == "publicado" else "")
            d = self.elegir(LUNES, forzar_activa=True)
            self.assertEqual(d["PUBLICAR_INSTAGRAM"], esperado, estado)
            self.assertEqual(d["PUBLICAR_FACEBOOK"], "true")

    def test_story_y_tiktok_tienen_su_propia_clave(self):
        self.config["canales_story"] = ["instagram", "facebook"]
        sel.registrar("las3yemas_20261003", "L3Y-20261003-08", "instagram_story", LUNES, "publicado", "9",
                      ruta=self.registro)
        self.registrar("tiktok", "desconocido")
        d = self.elegir(LUNES, forzar_activa=True)
        self.assertEqual(d["PUBLICAR_STORY_INSTAGRAM"], "false")
        self.assertEqual(d["PUBLICAR_STORY_FACEBOOK"], "true")
        self.assertEqual(d["PUBLICAR_TIKTOK"], "false")
        self.assertEqual(d["PUBLICAR_INSTAGRAM"], "true")

    def test_publicado_exige_id_remoto(self):
        with self.assertRaises(ValueError):
            self.registrar("instagram", "publicado")

    def test_clave_por_canal_y_fecha(self):
        self.registrar("instagram", "publicado", "123")
        martes = self.elegir(LUNES + dt.timedelta(days=1), forzar_activa=True)
        self.assertEqual(martes["PUBLICAR_INSTAGRAM"], "true")


class Reels(Base):
    def setUp(self):
        super().setUp()
        self.video = RAIZ / "publicidad/_prueba_reel.mp4"

    def tearDown(self):
        self.video.unlink(missing_ok=True)
        super().tearDown()

    def test_sin_video_aprobado_no_hay_reel(self):
        for asset in ("L3Y-20261003-15", "L3Y-20261003-16", "L3Y-20261003-17"):
            with self.assertRaises(ValueError):
                sel.preparar_reel(asset, LUNES, self.config, self.registro)
        self.video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        self.config["portadas_reels"]["L3Y-20261003-15"].update(video="publicidad/_prueba_reel.mp4")
        with self.assertRaises(ValueError):  # falta aprobado=true
            sel.preparar_reel("L3Y-20261003-15", LUNES, self.config, self.registro)

    def test_portada_con_video_aprobado(self):
        self.video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        self.config["portadas_reels"]["L3Y-20261003-16"].update(video="publicidad/_prueba_reel.mp4", aprobado=True)
        d = sel.preparar_reel("L3Y-20261003-16", LUNES, self.config, self.registro)
        self.assertEqual(d["VIDEO"], "publicidad/_prueba_reel.mp4")
        self.assertIn("03_Portadas_Reels/02_el_desayuno", d["PORTADA"])
        self.assertEqual(d["PUBLICAR_REEL"], "true")
        sel.registrar("las3yemas_20261003", "L3Y-20261003-16", "instagram_reel", LUNES, "en_curso",
                      ruta=self.registro)
        d = sel.preparar_reel("L3Y-20261003-16", LUNES, self.config, self.registro)
        self.assertEqual(d["PUBLICAR_REEL"], "false")

    def test_solo_portadas(self):
        self.video.write_bytes(b"x")
        self.config["portadas_reels"]["L3Y-20261003-01"] = {"video": "publicidad/_prueba_reel.mp4", "aprobado": True}
        with self.assertRaises(ValueError):
            sel.preparar_reel("L3Y-20261003-01", LUNES, self.config, self.registro)


class FlujoCLI(Base):
    """Simula dos ejecuciones del workflow el mismo día, sin llamadas de red."""

    def correr(self, *args, salida=None):
        cfg = Path(self.tmp.name) / "config.json"
        datos = dict(self.config, activa=True)
        cfg.write_text(json.dumps(datos), encoding="utf-8")
        env = dict(os.environ, PUBLICIDAD_CONFIG=str(cfg), PUBLICIDAD_REGISTRO=str(self.registro),
                   PYTHONIOENCODING="utf-8")
        if salida:
            env["GITHUB_OUTPUT"] = str(salida)
        r = subprocess.run([sys.executable, str(RAIZ / "publicidad/seleccionar.py"), *args],
                           env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def salida(self, nombre):
        ruta = Path(self.tmp.name) / nombre
        ruta.write_text("", encoding="utf-8")
        return ruta

    def test_segunda_ejecucion_del_dia_no_publica(self):
        out1 = self.salida("out1")
        self.correr("elegir", "--fecha", "2026-10-05", "--github-output", salida=out1)
        o1 = dict(l.split("=", 1) for l in out1.read_text(encoding="utf-8").splitlines())
        self.assertEqual((o1["PUBLICAR_INSTAGRAM"], o1["PUBLICAR_FACEBOOK"]), ("true", "true"))
        for canal in ("instagram", "facebook"):
            self.correr("registrar", "--canal", canal, "--estado", "en_curso",
                        "--asset", o1["ASSET_ID"], "--fecha", o1["FECHA_LOCAL"])
        self.correr("registrar", "--canal", "instagram", "--estado", "publicado", "--remote-id", "1789",
                    "--asset", o1["ASSET_ID"], "--fecha", o1["FECHA_LOCAL"])
        self.correr("registrar", "--canal", "facebook", "--estado", "desconocido",
                    "--asset", o1["ASSET_ID"], "--fecha", o1["FECHA_LOCAL"])

        out2 = self.salida("out2")
        self.correr("elegir", "--fecha", "2026-10-05", "--github-output", salida=out2)
        o2 = dict(l.split("=", 1) for l in out2.read_text(encoding="utf-8").splitlines())
        self.assertEqual((o2["PUBLICAR_INSTAGRAM"], o2["PUBLICAR_FACEBOOK"]), ("false", "false"))

        filas = [json.loads(l) for l in self.registro.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(filas[2]["clave"], "las3yemas_20261003|L3Y-20261003-01|instagram|2026-10-05")
        self.assertEqual(filas[2]["remote_id"], "1789")


class Workflows(unittest.TestCase):
    def test_solo_publicidad_diaria_publica(self):
        wf = RAIZ / ".github/workflows"
        marketing = (wf / "marketing.yml").read_text(encoding="utf-8")
        self.assertNotIn("curl", marketing)
        self.assertNotIn("schedule", marketing)
        diaria = (wf / "publicidad-diaria.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "0 13 * * *"', diaria)
        self.assertNotIn("media_type=REELS", diaria)
        reels = (wf / "reels.yml").read_text(encoding="utf-8")
        self.assertNotIn("schedule", reels)  # Reels solo a mano

    def test_selector_sin_red(self):
        fuente = (RAIZ / "publicidad/seleccionar.py").read_text(encoding="utf-8")
        for modulo in ("urllib", "requests", "socket", "http.client", "subprocess"):
            self.assertNotIn(f"import {modulo}", fuente)


if __name__ == "__main__":
    unittest.main()
