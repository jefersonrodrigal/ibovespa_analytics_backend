def test_metodologia_returns_real_markdown_content(client):
    response = client.get("/api/metodologia")
    assert response.status_code == 200
    assert "Fontes de dados" in response.text
    assert "BCB" in response.text
