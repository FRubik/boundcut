"""Testes da estrutura do projeto: pyproject.toml, arquivos referenciados e links do README."""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

import boundcut as g

RAIZ = Path(__file__).resolve().parent.parent

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None


@unittest.skipIf(tomllib is None, "tomllib requer Python 3.11+")
class TestPyproject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))

    def test_versao_vem_do_modulo(self):
        self.assertIn("version", self.cfg["project"]["dynamic"])
        self.assertEqual(self.cfg["tool"]["hatch"]["version"]["path"], "boundcut.py")
        self.assertRegex(g.__version__, r"^\d+\.\d+\.\d+$")

    def test_comando_aponta_para_funcao_existente(self):
        alvo = self.cfg["project"]["gui-scripts"]["boundcut"]
        modulo, funcao = alvo.split(":")
        self.assertEqual(modulo, "boundcut")
        self.assertTrue(callable(getattr(g, funcao)))

    def test_arquivos_empacotados_existem(self):
        wheel = self.cfg["tool"]["hatch"]["build"]["targets"]["wheel"]
        for f in [*wheel["only-include"], *wheel["force-include"]]:
            self.assertTrue((RAIZ / f).exists(), f)

    def test_sdist_nao_leva_pasta_pessoal(self):
        # include é lista branca ancorada na raiz; sem "/" um padrão casaria dentro de sessoes/
        for padrao in self.cfg["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]:
            self.assertTrue(padrao.startswith("/"), padrao)
            self.assertNotIn("sessoes", padrao)


class TestArquivosDoProjeto(unittest.TestCase):
    def test_icone_existe(self):
        self.assertTrue(g.ICON_PATH.exists())

    def test_links_locais_do_readme_existem(self):
        for readme in ("README.md", "README.pt-BR.md"):
            texto = (RAIZ / readme).read_text(encoding="utf-8")
            links = re.findall(r'(?:src="|\]\()([^")#]+)', texto)
            self.assertTrue(links, readme)
            for link in links:
                if not link.startswith(("http://", "https://")):
                    self.assertTrue((RAIZ / link).exists(), f"{readme}: {link}")

    def test_readme_tem_prints(self):
        for readme in ("README.md", "README.pt-BR.md"):
            self.assertIn("assets/prints/", (RAIZ / readme).read_text(encoding="utf-8"), readme)


def _ruff() -> list[str] | None:
    if shutil.which("ruff"):
        return ["ruff"]
    if shutil.which("uvx"):
        return ["uvx", "ruff"]
    return None


@unittest.skipIf(_ruff() is None, "ruff/uvx não encontrados")
class TestRuff(unittest.TestCase):
    """Lint e formatação fazem parte da suíte: a regra de rodar os testes cobre os dois."""

    def _rodar(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([*_ruff(), *args], cwd=RAIZ, capture_output=True, text=True)

    def test_lint(self):
        r = self._rodar("check", ".", "--output-format", "concise")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_formatacao(self):
        r = self._rodar("format", "--check", ".")
        self.assertEqual(r.returncode, 0, "rode `uvx ruff format .`\n" + r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
