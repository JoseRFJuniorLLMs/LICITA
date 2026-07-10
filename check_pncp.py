import urllib.request, json

url = (
    "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
    "?dataInicial=20260703&dataFinal=20260709&pagina=1&tamanhoPagina=3"
    "&codigoModalidadeContratacao=6"
)
req = urllib.request.Request(url, headers={"Accept": "application/json"})
r = urllib.request.urlopen(req, timeout=20)
data = json.loads(r.read())
items = data.get("data", [])
print("Total itens:", len(items))
if items:
    it = items[0]
    org = it.get("orgaoEntidade", {})
    cnpj = org.get("cnpj", "")
    ano = it.get("anoCompra")
    seq = it.get("sequencialCompra")
    link_orig = it.get("linkSistemaOrigem")
    print("cnpj:", cnpj)
    print("anoCompra:", ano)
    print("sequencialCompra:", seq)
    print("linkSistemaOrigem:", link_orig)
    if cnpj and ano and seq:
        built = "https://pncp.gov.br/app/editais/{}/{}/{}".format(cnpj, ano, seq)
        print("link construido:", built)
