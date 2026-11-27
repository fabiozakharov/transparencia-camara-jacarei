# Transparência Câmara de Jacareí

Coleta diária de dados públicos da Câmara Municipal de Jacareí (legislatura 2025–2028) para as fichas dos vereadores.

- `coletor/coletar.py` lê o site oficial (somente leitura) e grava os resultados em `dados/`.
- `.github/workflows/coletar.yml` roda o coletor todo dia às 6h17 (Brasília) e salva os dados no repositório. Também pode ser disparado à mão na aba **Actions**.

## Dados gerados

| Arquivo | Conteúdo |
|---|---|
| `dados/trabalhos.json` | Indicações, requerimentos, pedidos de informação e moções por vereador e por ano, contados pelos PDFs que a Câmara publica (um por item). |
| `dados/presencas.json` | Presenças e ausências por sessão, extraídas das atas em Word. Heurística, conferir. |
| `dados/atas_texto/` | Texto de cada ata, para conferência. |
| `dados/coleta.json` | Data da última coleta, totais e avisos (autores não reconhecidos, falhas). |

## Rodar localmente

```bash
pip install -r coletor/requirements.txt
python coletor/coletar.py
```
