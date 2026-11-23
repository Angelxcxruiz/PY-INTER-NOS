from app.core.security import (
    cifrar,
    crear_jwt,
    descifrar,
    hash_contrasena,
    verificar_contrasena,
    verificar_jwt,
)

CLAVE = "AdminInterNos123!"


def test_hash_valido_verifica_true() -> None:
    hash_guardado = hash_contrasena(CLAVE)

    assert len(hash_guardado) == 97
    assert verificar_contrasena(hash_guardado, CLAVE) is True


def test_contrasena_distinta_da_false_sin_excepcion() -> None:
    assert verificar_contrasena(hash_contrasena(CLAVE), "OtraClave456") is False


def test_hash_nulo_o_vacio_da_false() -> None:
    assert verificar_contrasena(None, CLAVE) is False
    assert verificar_contrasena("", CLAVE) is False


def test_contrasena_nula_da_false() -> None:
    assert verificar_contrasena(hash_contrasena(CLAVE), None) is False


def test_hash_corrupto_o_ajeno_da_false_en_lugar_de_excepcion() -> None:
    hash_guardado = hash_contrasena(CLAVE)

    assert verificar_contrasena(hash_guardado[:-5] + "zzzzz", CLAVE) is False
    assert verificar_contrasena("abc", CLAVE) is False
    assert (
        verificar_contrasena("$2b$12$notargon2notargon2notargon2notargon2notargon2nota", CLAVE)
        is False
    )


def test_argumentos_invertidos_dan_false_y_no_excepcion() -> None:
    # (contraseña, hash) en lugar de (hash, contraseña): el error que originó este arreglo.
    assert verificar_contrasena(CLAVE, hash_contrasena(CLAVE)) is False


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
