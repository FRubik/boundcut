"""Testes automatizados de ponta a ponta: geram vídeos com o ffmpeg, cortam e conferem a saída."""

import subprocess
import tempfile
import unittest
from pathlib import Path

import boundcut as g
from tests.base import app, codec_video, contar_frames, extrair_frame, gerar_video, precisa_ffmpeg, psnr


def exportar(info, start, dur, out, precise=True, frames=("primeiro", "ultimo")):
    """Roda o ExportWorker na thread atual e devolve o que ele emitiu em `done`."""
    w = g.ExportWorker(info, start, dur, out, precise, frames)
    res = []
    w.done.connect(lambda *a: res.append(a))
    w.run()
    return res[0]


@precisa_ffmpeg
class TestExportacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        cls.mp4 = gerar_video(cls.dir / "origem.mp4", fps=30, segundos=10)
        cls.webm = gerar_video(
            cls.dir / "origem.webm", fps=25, segundos=6, vcodec="libvpx-vp9", acodec="libopus"
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _janela_com(self, video):
        w = g.MainWindow()
        w.load(video)
        self.addCleanup(w.close)
        return w

    def test_probe(self):
        i = g.probe(self.mp4)
        self.assertEqual((i.vcodec, i.acodec, i.width, i.height), ("h264", "aac", 320, 180))
        self.assertAlmostEqual(i.fps, 30.0)
        self.assertAlmostEqual(i.duration, 10.0, delta=0.1)

    def test_probe_rejeita_arquivo_sem_video(self):
        f = self.dir / "nao_e_video.txt"
        f.write_text("oi")
        # ffprobe recusa o arquivo (CalledProcessError) ou ele não tem vídeo (ValueError)
        with self.assertRaises((subprocess.CalledProcessError, ValueError)):
            g.probe(f)

    def _corte_preciso(self, origem, in_ms, out_ms, frame_ini, frame_fim, codec):
        w = self._janela_com(origem)
        w.in_ms, w.out_ms = in_ms, out_ms
        start, dur = w._cut_seconds()
        out = self.dir / f"corte_{origem.suffix[1:]}{origem.suffix}"
        ok, msg, video, frames = exportar(w.info, start, dur, out)

        self.assertTrue(ok, msg)
        self.assertEqual(Path(video).suffix, origem.suffix)  # mesmo container
        self.assertEqual(codec_video(out), codec)  # mesmo codec
        self.assertEqual(contar_frames(out), frame_fim - frame_ini + 1)  # inclui os dois extremos

        primeiro, ultimo = (Path(f) for f in frames)
        self.assertEqual(primeiro.name, out.stem + "_primeiro_frame.png")
        self.assertEqual(ultimo.name, out.stem + "_ultimo_frame.png")
        # cada PNG é o frame marcado (início/fim), e não o vizinho de fora do corte
        for png, idx, vizinho_idx in (
            (primeiro, frame_ini, frame_ini - 1),
            (ultimo, frame_fim, frame_fim + 1),
        ):
            ref = extrair_frame(origem, idx, self.dir / "ref.png")
            vizinho = extrair_frame(origem, vizinho_idx, self.dir / "vizinho.png")
            self.assertGreater(psnr(png, ref), 35, png.name)
            self.assertGreater(psnr(png, ref), psnr(png, vizinho) + 10, png.name)

    def test_corte_preciso_mp4(self):
        self._corte_preciso(self.mp4, 2000, 5000, 60, 150, "h264")

    def test_corte_preciso_webm(self):
        self._corte_preciso(self.webm, 1000, 3000, 25, 75, "vp9")

    def test_corte_rapido(self):
        out = self.dir / "rapido.mp4"
        ok, msg, _video, frames = exportar(g.probe(self.mp4), 2.0, 3.0, out, precise=False)
        self.assertTrue(ok, msg)
        self.assertEqual(codec_video(out), "h264")
        self.assertEqual(len(frames), 2)
        self.assertTrue(all(Path(f).exists() for f in frames))

    def test_so_o_primeiro_frame(self):
        out = self.dir / "so_primeiro.mp4"
        ok, msg, _video, frames = exportar(g.probe(self.mp4), 0, 1.0, out, frames=("primeiro",))
        self.assertTrue(ok, msg)
        self.assertEqual([Path(f).name for f in frames], ["so_primeiro_primeiro_frame.png"])
        self.assertFalse(g.frame_png(out, "ultimo").exists())

    def test_sem_salvar_frame(self):
        out = self.dir / "sem_frame.mp4"
        ok, msg, _video, frames = exportar(g.probe(self.mp4), 0, 1.0, out, frames=())
        self.assertTrue(ok, msg)
        self.assertEqual(frames, [])
        self.assertEqual(list(self.dir.glob("sem_frame_*.png")), [])

    def test_falha_nao_deixa_arquivo_pela_metade(self):
        info = g.probe(self.mp4)
        info.path = self.dir / "nao_existe.mp4"
        out = self.dir / "falha.mp4"
        ok, msg, _video, _frame = exportar(info, 0, 1.0, out)
        self.assertFalse(ok)
        self.assertIn("ffmpeg falhou", msg)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
