from __future__ import annotations

import unittest

from projecthandler.parser import PdfProjectParser


class PdfProjectParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = PdfProjectParser()

    def _word(
        self,
        text: str,
        x0: float,
        top: float,
        width: float = 24,
        height: float = 7,
        *,
        confidence: float | None = None,
    ) -> dict[str, object]:
        word: dict[str, object] = {
            "text": text,
            "x0": x0,
            "x1": x0 + width,
            "top": top,
            "bottom": top + height,
        }
        if confidence is not None:
            word["confidence"] = confidence
        return word

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

    def test_extracts_pole_coordinate_split_by_line_break(self) -> None:
        project = self.parser.parse_text("U1(1)N(2)U3(2)\nS1N S3R\n10-150\n0484323\n7820699")
        pole = next(entity for entity in project.entities if entity.entity_type == "postes")

        self.assertEqual(pole.label, "10-150")
        self.assertEqual(pole.attributes["coordenada"], "0484323 / 7820699")

    def test_extracts_pole_coordinate_split_by_colon_or_slash(self) -> None:
        colon_project = self.parser.parse_text("P4\nCM2(1)\nS1N\n11-300\n405403:7804399")
        slash_project = self.parser.parse_text("U4(1)\nS4R\n13-600\n0484354/7820724")

        colon_pole = next(entity for entity in colon_project.entities if entity.entity_type == "postes")
        slash_pole = next(entity for entity in slash_project.entities if entity.entity_type == "postes")

        self.assertEqual(colon_pole.attributes["coordenada"], "405403 / 7804399")
        self.assertEqual(slash_pole.attributes["coordenada"], "0484354 / 7820724")

    def test_does_not_reuse_next_pole_coordinate(self) -> None:
        project = self.parser.parse_text("11-300\n10-150\n0484323\n7820699")
        poles = {entity.label: entity for entity in project.entities if entity.entity_type == "postes"}

        self.assertNotIn("coordenada", poles["11-300"].attributes)
        self.assertEqual(poles["10-150"].attributes["coordenada"], "0484323 / 7820699")

    def test_extracts_pole_coordinates_by_pdf_layout_position(self) -> None:
        layout = {
            "words": [
                self._word("U1(1)", 45, 262),
                self._word("U3(2)", 65, 262),
                self._word("S1N", 49, 270),
                self._word("S3N", 65, 270),
                self._word("10-150", 53, 279),
                self._word("U4(1)", 280, 374),
                self._word("S4R", 281, 382),
                self._word("13-600", 276, 391),
                self._word("0484354", 273, 401, width=28),
                self._word("7820724", 273, 409, width=28),
                self._word("U1(1)N(2)U3(2)", 203, 501, width=45),
                self._word("S1NS3R", 212, 508, width=28),
                self._word("10-150", 214, 515),
                self._word("0484323", 212, 523, width=28),
                self._word("7820699", 212, 532, width=28),
            ],
            "objects": [],
        }

        poles = self.parser._extract_poles_from_layout(layout, "", 1)

        self.assertEqual([pole.label for pole in poles], ["10-150", "13-600", "10-150"])
        self.assertNotIn("coordenada", poles[0].attributes)
        self.assertEqual(poles[1].attributes["coordenada"], "0484354 / 7820724")
        self.assertEqual(poles[2].attributes["coordenada"], "0484323 / 7820699")

    def test_extracts_poles_from_noisy_ocr_layout(self) -> None:
        layout = {
            "words": [
                self._word("[11-30", 666, 706, width=37, confidence=58),
                self._word("405391:7804538", 632, 729, width=111, confidence=59),
                self._word("{11-304", 170, 1095, width=46, confidence=30),
                self._word("405400,7804452", 137, 1118, width=111, confidence=88),
                self._word("1-601", 338, 2839, width=36, confidence=38),
                self._word("405428:7804458", 302, 2861, width=111, confidence=20),
            ],
            "objects": [],
        }

        poles = self.parser._extract_poles_from_layout(layout, "", 1)

        self.assertEqual([pole.label for pole in poles], ["11-300", "11-300", "11-600"])
        self.assertEqual(poles[0].attributes["coordenada"], "405391 / 7804538")
        self.assertEqual(poles[1].attributes["coordenada"], "405400 / 7804452")
        self.assertEqual(poles[2].attributes["coordenada"], "405428 / 7804458")

    def test_extracts_metadata_from_ocr_label_variants(self) -> None:
        text = (
            "Impacto Ambiental: NAO DATA: 21/06/2026 "
            "Circuito: LUZU 07 Cidade: CORREGO DANTA - MG "
            "Dispositivo: 160992-100A-8T-C Bairro: AREA RURAL Scala: 1:1000 "
            "COORD: 23K 405177:7805444 Cliente: ANDRE LUIZ DE OLIVEIRA "
            "Levantamento: MARCOS CRUZ Telefone: (37)98822-1003 NS: 1253081412 "
            "Projeto: ANDRE CASTRO Servico: MODIFICAGAO RURAL / LIGAGAO NOVA "
            "Aprovagao: FORMATO A2 FOLHA: 1/1"
        )

        metadata = self.parser._extract_metadata(text)

        self.assertEqual(metadata["cidade"], "CORREGO DANTA - MG")
        self.assertEqual(metadata["bairro"], "AREA RURAL")
        self.assertEqual(metadata["escala"], "1:1000")
        self.assertEqual(metadata["ns"], "1253081412")
        self.assertEqual(metadata["servico"], "MODIFICAGAO RURAL / LIGAGAO NOVA")


if __name__ == "__main__":
    unittest.main()
