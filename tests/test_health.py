def test_health_hace_ping_a_mysql(cliente) -> None:
    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}
