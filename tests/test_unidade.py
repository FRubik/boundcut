"""Testes de unidade: funções puras e lógica da interface, sem precisar do ffmpeg."""

import unittest
from pathlib import Path

from boundcut import exportacao, janela, midia, timeline
from tests.base import app


def info(vcodec="h264", fps=30.0, duration=10.0, pix_fmt="yuv420p", acodec="aac"):
    return midia.VideoInfo(
        path=Path("/tmp/x.mp4"),
        duration=duration,
        fps=fps,
        vcodec=vcodec,
        pix_fmt=pix_fmt,
        acodec=acodec,
        width=320,
        height=180,
    )


class TestParseRate(unittest.TestCase):
    def test_fracao(self):
        self.assertAlmostEqual(midia._parse_rate("30000/1001"), 29.97, places=2)

    def test_inteiro_e_decimal(self):
        self.assertEqual(midia._parse_rate("25"), 25.0)
        self.assertEqual(midia._parse_rate("23.976"), 23.976)

    def test_valores_invalidos_viram_zero(self):
        for v in (None, "", "0/0", "0", "abc", "1/0", "x/y"):
            self.assertEqual(midia._parse_rate(v), 0.0, v)


class TestFmtTime(unittest.TestCase):
    def test_minutos(self):
        self.assertEqual(midia.fmt_time(0), "00:00.000")
        self.assertEqual(midia.fmt_time(65.5), "01:05.500")

    def test_horas(self):
        self.assertEqual(midia.fmt_time(3661.25), "01:01:01.250")

    def test_negativo_vira_zero(self):
        self.assertEqual(midia.fmt_time(-3), "00:00.000")


class TestEncoders(unittest.TestCase):
    def test_mantem_o_codec_original(self):
        casos = {
            "h264": "libx264",
            "hevc": "libx265",
            "vp9": "libvpx-vp9",
            "vp8": "libvpx",
            "av1": "libsvtav1",
            "mpeg4": "mpeg4",
            "prores": "prores_ks",
        }
        for codec, encoder in casos.items():
            args = midia.video_encoder_args(info(codec), ".mkv")
            self.assertEqual(args[args.index("-c:v") + 1], encoder, codec)

    def test_hevc_em_mp4_recebe_tag_hvc1(self):
        self.assertIn("hvc1", midia.video_encoder_args(info("hevc"), ".mp4"))
        self.assertNotIn("hvc1", midia.video_encoder_args(info("hevc"), ".mkv"))

    def test_codec_desconhecido_usa_padrao_do_container(self):
        self.assertIn("libvpx-vp9", midia.video_encoder_args(info("rawvideo"), ".webm"))
        self.assertIn("libx264", midia.video_encoder_args(info("rawvideo"), ".mov"))

    def test_audio_reserva(self):
        self.assertIn("libopus", midia.audio_fallback_args(".webm"))
        self.assertIn("libopus", midia.audio_fallback_args(".mkv"))
        self.assertIn("aac", midia.audio_fallback_args(".mp4"))


class TestComandosExportacao(unittest.TestCase):
    def test_modo_preciso_tem_tentativa_reserva(self):
        w = exportacao.ExportWorker(info(), 2.0, 3.0, Path("/tmp/saida.mp4"), precise=True)
        cmds = w._build_cmds()
        self.assertEqual(len(cmds), 2)
        self.assertIn("copy", cmds[0])  # 1ª: áudio copiado
        self.assertIn("aac", cmds[1])  # 2ª: áudio reencodado
        self.assertNotIn("-pix_fmt", cmds[1])
        for c in cmds:
            self.assertEqual(c[c.index("-ss") + 1], "2.000000")
            self.assertEqual(c[c.index("-t") + 1], "3.000000")
            self.assertIn("+faststart", c)
            self.assertEqual(c[-1], "/tmp/saida.mp4")

    def test_modo_rapido_copia_streams(self):
        w = exportacao.ExportWorker(info(), 0, 1, Path("/tmp/saida.webm"), precise=False, frames=())
        (cmd,) = w._build_cmds()
        self.assertEqual(cmd[cmd.index("-c") + 1], "copy")
        self.assertNotIn("+faststart", cmd)  # só faz sentido em mp4/mov


class TestFrames(unittest.TestCase):
    def test_nome_do_png(self):
        out = Path("/tmp/video_corte.mp4")
        self.assertEqual(midia.frame_png(out, "primeiro"), Path("/tmp/video_corte_primeiro_frame.png"))
        self.assertEqual(midia.frame_png(out, "ultimo"), Path("/tmp/video_corte_ultimo_frame.png"))

    def test_comando_do_primeiro_le_um_frame_do_inicio(self):
        cmd = midia.frame_cmd(Path("v.mp4"), "primeiro", Path("p.png"))
        self.assertNotIn("-sseof", cmd)
        self.assertEqual(cmd[cmd.index("-frames:v") + 1], "1")
        self.assertEqual(cmd[-1], "p.png")

    def test_comando_do_ultimo_le_o_fim(self):
        cmd = midia.frame_cmd(Path("v.mp4"), "ultimo", Path("u.png"))
        self.assertLess(cmd.index("-sseof"), cmd.index("-i"))  # busca na entrada, antes do -i
        self.assertIn("-update", cmd)

    def test_frame_desconhecido(self):
        with self.assertRaises(ValueError):
            midia.frame_cmd(Path("v.mp4"), "meio", Path("m.png"))

    def test_worker_ignora_desconhecidos_e_ordena(self):
        w = exportacao.ExportWorker(
            info(), 0, 1, Path("/tmp/s.mp4"), precise=True, frames=("ultimo", "x", "primeiro")
        )
        self.assertEqual(w.frames, ("primeiro", "ultimo"))

    def test_padrao_continua_sendo_o_ultimo(self):
        self.assertEqual(
            exportacao.ExportWorker(info(), 0, 1, Path("/tmp/s.mp4"), precise=True).frames, ("ultimo",)
        )


class TestTimeline(unittest.TestCase):
    def setUp(self):
        app()
        self.t = timeline.Timeline()
        self.t.resize(1024, 54)
        self.t.set_duration(10_000)

    def test_conversao_ms_pixel_ida_e_volta(self):
        for ms in (0, 2500, 5000, 10_000):
            self.assertAlmostEqual(self.t._ms(self.t._x(ms)), ms, delta=10)

    def test_clique_fora_da_trilha_fica_nos_limites(self):
        self.assertEqual(self.t._ms(-100), 0)
        self.assertEqual(self.t._ms(5000), 10_000)

    def test_acerta_os_marcadores(self):
        self.t.set_range(2000, 8000)
        self.assertEqual(self.t._hit(self.t._x(2000)), "in")
        self.assertEqual(self.t._hit(self.t._x(8000)), "out")
        self.assertEqual(self.t._hit(self.t._x(5000)), "seek")


class TestCorteNaJanela(unittest.TestCase):
    """O frame marcado como fim precisa entrar no corte, e o seguinte não."""

    def setUp(self):
        app()
        self.w = janela.MainWindow()
        self.w.info = info(fps=30.0, duration=10.0)
        self.w.timeline.set_duration(10_000)

    def tearDown(self):
        self.w.close()

    def test_frame_index(self):
        self.assertEqual(self.w.frame_index(0), 0)
        self.assertEqual(self.w.frame_index(32), 0)
        self.assertEqual(self.w.frame_index(34), 1)
        self.assertEqual(self.w.frame_index(5000), 150)

    def test_passo_de_frame_ida_e_volta(self):
        # step_frames posiciona em ceil(idx * frame_ms); o índice lido de volta tem de ser o mesmo
        import math

        for fps in (23.976, 25, 29.97, 30, 60):
            self.w.info = info(fps=fps)
            for idx in range(0, 400):
                self.assertEqual(self.w.frame_index(math.ceil(idx * self.w.frame_ms)), idx, (fps, idx))

    def test_duracao_inclui_o_frame_do_fim(self):
        self.w.in_ms, self.w.out_ms = 2000, 5000  # frames 60..150 → 91 frames
        start, dur = self.w._cut_seconds()
        self.assertAlmostEqual(start, 2.0)
        self.assertAlmostEqual(dur * 30, 90.5)  # meio frame depois do frame 150

    def test_duracao_nao_passa_do_fim_do_video(self):
        self.w.in_ms, self.w.out_ms = 9000, 10_000
        start, dur = self.w._cut_seconds()
        self.assertLessEqual(start + dur, 10.0 + 1e-9)

    def test_marcadores_nao_se_cruzam(self):
        self.w.in_ms, self.w.out_ms = 2000, 5000
        self.w._set_in(7000)
        self.assertEqual(self.w.in_ms, 5000)
        self.w._set_out(1000)
        self.assertEqual(self.w.out_ms, 5000)

    def test_nome_padrao_nao_sobrescreve(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "video.mp4"
            src.touch()
            self.w.info = info()
            self.w.info.path = src
            self.assertEqual(self.w._default_out().name, "video_corte.mp4")
            (Path(d) / "video_corte.mp4").touch()
            self.assertEqual(self.w._default_out().name, "video_corte_2.mp4")


if __name__ == "__main__":
    unittest.main()
