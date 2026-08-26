from app.pilot_text import normalize_generated_title


def test_normalize_generated_title_repairs_only_the_known_plural_defect() -> None:
    assert normalize_generated_title("Aprendizagem com dados real") == "Aprendizagem com dados reais"
    assert normalize_generated_title("Aprendizagem com dados reai") == "Aprendizagem com dados reais"
    assert normalize_generated_title("Aprendizagem com dados reais") == "Aprendizagem com dados reais"
    assert normalize_generated_title("Dados realmente observados") == "Dados realmente observados"
