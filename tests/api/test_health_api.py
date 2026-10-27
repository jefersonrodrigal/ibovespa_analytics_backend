def test_health_reports_connected_database(client):
    # /api/health verifica deliberadamente a conexão "de verdade" (a mesma config
    # de .env usada em produção), não o banco de testes injetado via dependency
    # override — é assim que um health check deve se comportar (reportar o estado
    # real do recurso configurado, não um banco trocado só para o teste).
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database_connected"] is True
    assert isinstance(body["last_successful_run_at"], (str, type(None)))
