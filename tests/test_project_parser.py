from __future__ import annotations

import unittest

from projecthandler.parser import PdfProjectParser


class PdfProjectParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = PdfProjectParser()

    def test_extracts_project_metadata_and_entities_from_sample_text(self) -> None:
        text = (
            "U4(1) S4R U3(1) S3R N(2) 11-300 10-300 "
            "397650 7725800 A-4 CA N-(4 CA) ABN-35(70) "
            "Circuito: PIUD-209 Dispositivo: CH-413405-300A-8T-A "
            "Levantamento: PEDRO Projeto: LAYLA MENDES Aprovação: "
            "Cidade: CAPITOLIO Bairro: ÁREA RURAL Cliente: PEDRO HENRIQUE "
            "Telefone: (37) 999057324 Serviço: LIGAÇÃO NOVA FORMATO: A3 "
            "Impacto Ambiental: SIM DATA: 23/06/2026 Escala: 1:1000 NS: 1252773647 FOLHA: 1/ 1"
        )

        project = self.parser.parse_text(text)
        labels = [entity.label for entity in project.entities]

        self.assertEqual(project.metadata["ns"], "1252773647")
        self.assertEqual(project.metadata["cidade"], "CAPITOLIO")
        self.assertEqual(project.metadata["data"], "23/06/2026")
        self.assertIn("11-300", labels)
        self.assertIn("10-300", labels)
        self.assertIn("U4", labels)
        self.assertIn("S4R", labels)
        self.assertIn("A-4 CA", labels)
        self.assertIn("(N-4 CA)", labels)
        self.assertIn("ABN-35(70)", labels)

    def test_handles_concatenated_structure_codes(self) -> None:
        project = self.parser.parse_text("U3(2)N(2) S3RS1N U1(1) B-4 CAAB-4 CAA")
        labels = [entity.label for entity in project.entities]

        self.assertIn("U3", labels)
        self.assertIn("S3R", labels)
        self.assertIn("S1N", labels)
        self.assertIn("B-4 CAA", labels)
        self.assertTrue(any(entity.label == "N" and entity.quantity == 2 for entity in project.entities))


if __name__ == "__main__":
    unittest.main()
