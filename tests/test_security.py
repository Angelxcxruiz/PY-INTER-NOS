from app.core.security import (
    cifrar,
    crear_jwt,
    descifrar,
    verificar_jwt,
)


def test_cifrado_fernet_es_simetrico() -> None:
    valor = "ABC23456"
    cifrado = cifrar(valor)

    assert cifrado != valor
    assert descifrar(cifrado) == valor


def test_jwt_incluye_sujeto_rol_y_expiracion() -> None:
    token = crear_jwt(
        {
            "sub": "11111111-1111-1111-1111-111111111111",
            "rol": "DOCENTE",
            "permisos": ["CREAR_CASOS"],
        },
        expiracion_minutos=15,
    )
    contenido = verificar_jwt(token)

    assert contenido["sub"] == "11111111-1111-1111-1111-111111111111"
    assert contenido["rol"] == "DOCENTE"
    assert "exp" in contenido
