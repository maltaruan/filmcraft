"""Regressão (25/10/2026, C0205): a conferência de ritmo do plano de câmera ignorava o corte seco e
avisava "mais de 7,5 s parado" num trecho que mudava de quadro no corte (16,2-25,3 s com corte em 18,52 s).
Rodar: python3 -m unittest discover -s ~/filmcraft/ysquad/testes -p 'regressao*.py'"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "receitas"))
from montar_video import parados  # noqa: E402


class RitmoDaCamera(unittest.TestCase):
    def test_corte_seco_conta_como_mudanca(self):
        # o começo do C0205: emenda J1 aos 4,68, passo aos 9,56, soco aos 16,2, corte seco aos 18,52, soco aos 25,3
        zooms = [[4.146, "J1: vai 100 -> 128 até o corte"], [4.68, "J1: volta 128 -> 100"], [9.56, "passo 100 -> 108"],
                 [16.22, "soco 108 -> 128 -> 128"], [25.29, "soco 100 -> 128 -> 105"]]
        self.assertEqual(parados(zooms, [4.68, 18.52], 30.0), [])

    def test_trecho_parado_de_verdade_avisa(self):
        self.assertEqual(parados([[2.0, "passo 100 -> 108"]], [], 12.0), [(2.0, 12.0)])

    def test_vai_da_emenda_nao_conta(self):
        # o "vai" anda até o corte; a mudança que conta é o próprio corte
        zooms = [[3.9, "J1: vai 100 -> 128 até o corte"], [4.43, "J1: volta 128 -> 100"]]
        self.assertEqual(parados(zooms, [4.43], 10.0), [])


if __name__ == "__main__":
    unittest.main()
