# Transparência Câmara de Jacareí

Coleta diária de dados públicos da Câmara Municipal de Jacareí (legislatura 2025–2028) para as fichas dos vereadores.

- `coletor/coletar.py` lê o site oficial (somente leitura) e grava os resultados em `dados/`.
- `.github/workflows/coletar.yml` roda o coletor todo dia às 6h17 (Brasília) e salva os dados no repositório. Também pode ser disparado à mão na aba **Actions**.

## Dados gerados

| Arquivo | Conteúdo |
|---|---|
| `dados/trabalhos.json` | Indicações, requerimentos, pedidos de informação e moções por vereador e por ano, contados pelos PDFs que a Câmara publica (um por item). |
| `dados/presencas.json` | Presença por sessão ordinária e extraordinária, lida da lista "compareceram ... os seguintes Vereadores" de cada ata. Faltas = vereadores em exercício que não estão na lista. |
| `dados/atas_texto/` | Texto de cada ata, para conferência. |
| `dados/coleta.json` | Data da última coleta, totais e avisos (autores não reconhecidos, falhas). |

## Rodar localmente

```bash
pip install -r coletor/requirements.txt
python coletor/coletar.py
```
| `dados/projetos.json` | Projetos de 2025 em diante (PLL, PDL, PLCL, PR, PLE, PLCE) com autoria, assunto, norma gerada e documentos, montados pelos títulos dos PDFs publicados. |
| `dados/projetos_por_vereador.json` | Lista de projetos de cada vereador (e da Mesa e do Prefeito). |
| `dados/votacoes.json` | Cada item votado nas sessões, com resultado e contagem de votos tirados das atas; votos nominais por vereador quando o boletim (PDF escaneado, lido por OCR) é reconhecido. |
| `dados/boletins_texto/` | Texto OCR dos boletins de votação, para conferência. |
| `dados/emendas.json` | Emendas impositivas desta legislatura: cada destino com órgão, valor e categoria (Saúde, Educação, Esporte, Cultura, Assistência social, Obras e meio ambiente, Outros), mais totais por vereador. |
