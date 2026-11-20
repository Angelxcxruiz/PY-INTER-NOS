from app.core.security import (
    generar_codigo,
    hash_codigo,
    normalizar_codigo,
)
from app.modules.sessions.validacion import stub_validador

ALFABETO_PERMITIDO = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")


def test_generar_codigo_tiene_formato_seguro() -> None:
    primero = generar_codigo(8)
    segundo = generar_codigo(8)

    assert len(primero) == 8
    assert len(segundo) == 8
    assert set(primero).issubset(ALFABETO_PERMITIDO)
    assert set(segundo).issubset(ALFABETO_PERMITIDO)
    assert primero != segundo


def test_normalizar_codigo_acepta_minusculas_espacios_y_guiones() -> None:
    assert normalizar_codigo(" ab-cd 234 ") == "ABCD234"


def test_hash_codigo_es_estable_y_distinguible() -> None:
    hash_primero = hash_codigo("ABCD2345")

    assert hash_primero == hash_codigo("abcd 2345")
    assert hash_primero != hash_codigo("ABCD2346")


def test_stub_validador_retorna_respuesta() -> None:
    validador = stub_validador(
        respuesta={
            "convocatoria_id": "convocatoria-1",
            "sesion_id": "sesion-1",
            "caso_id": "caso-1",
            "estudiante_id": "estudiante-1",
            "valido": True,
        }
    )

    resultado = validador("estudiante@unal.edu.co", "ABCD2345")

    assert resultado["valido"] is True
