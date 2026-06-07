# Base de Dados do Sistema — NSA Pneutec ERP

Documento de referência para integração externa (ex: um sistema de **OEE** separado).
O ERP usa o **GitHub como banco de dados**: os arquivos abaixo ficam no repositório e
são lidos/gravados via API. Qualquer sistema externo pode **ler** esses arquivos
diretamente pela URL "raw" (somente leitura, sem autenticação) ou pela API do GitHub.

---

## 1. Tabela principal — `data/ordens.csv`

É o banco de pneus/OS. Um registro = um pneu (uma OS física). CSV com cabeçalho.

| Coluna         | Tipo   | Descrição                                                                 |
|----------------|--------|---------------------------------------------------------------------------|
| `NRORDEM`      | texto  | Nº da ordem/OS — **identificador único do pneu** (chave primária).        |
| `IDPEDIDOPNEU` | texto  | ID do pedido/coleta — **agrupa vários pneus** do mesmo pedido.            |
| `CLIENTE`      | texto  | Nome do cliente (nome completo como no ERP).                              |
| `NRSERIE`      | texto  | Número de série do pneu (pode estar vazio).                              |
| `DESENHO`      | texto  | Medida/desenho do pneu. Ex: `295/80R22,5 PM DVUM3 250`.                   |
| `STATUS`       | texto  | Estágio no processo. Valores: `Aguardando`, `Em Produção`, `Expedido`.   |
| `DATA_ENTRADA` | data   | `dd/mm/aaaa HH:MM:SS` (ou `dd/mm/aaaa`). Ver regra de preenchimento abaixo.|
| `DATA_SAIDA`   | data   | `dd/mm/aaaa HH:MM:SS`. Preenchida na expedição.                          |
| `LOCAL_PALLET` | texto  | Nome livre do pallet onde o pneu está no pátio (ex: `P-01`, `GAIOLA-A`).  |

### Ciclo de vida do `STATUS`
```
Aguardando  ──(bipe na entrada/produção)──►  Em Produção  ──(bipe na expedição)──►  Expedido
```

### Quando cada data é preenchida
- **`DATA_ENTRADA`**:
  - Na importação do CSV do ERP → recebe a data de emissão/coleta (`dd/mm/aaaa`).
  - No **Recebimento** (alocação em pallet) → recebe a data/hora da chegada ao pátio.
  - No **bipe de entrada na produção** → sobrescrita com a data/hora em que o pneu
    entrou na linha (`Em Produção`).
- **`DATA_SAIDA`**: preenchida no **bipe de expedição** (data/hora da saída).

> ⚠️ Como `DATA_ENTRADA` é reusada em etapas diferentes, para OEE o valor confiável de
> "entrou na linha" é a `DATA_ENTRADA` de registros com `STATUS` = `Em Produção` ou `Expedido`.

---

## 2. Arquivos de apoio (JSON)

### `data/trava_global.json` — trava Poka-Yoke da linha
```json
{ "id_travado": "367019" }   // IDPEDIDOPNEU travado no momento, ou null
```

### `data/plano_diario.json` — programação diária (linhas A/B/C)
```json
{
  "_schema": 2,
  "data": "04/06/2026",
  "linhas": {
    "A": [ { "idpedido": "364222", "cliente": "CORPUS SANEAMENTO", "qtd": "6" } ],
    "B": [ ... ],
    "C": [ ... ]
  }
}
```

---

## 3. Como ler os dados (somente leitura, sem token)

**URL raw (CSV):**
```
https://raw.githubusercontent.com/tiagoalexandre54/nsa-erp-pneutec/main/data/ordens.csv
```

**Python:**
```python
import pandas as pd
URL = "https://raw.githubusercontent.com/tiagoalexandre54/nsa-erp-pneutec/main/data/ordens.csv"
df = pd.read_csv(URL, dtype=str, keep_default_na=False)
```

JSONs: troque o final por `data/trava_global.json` ou `data/plano_diario.json`.

---

## 4. O que dá para extrair para OEE (e o que NÃO dá)

### ✅ Derivável da `ordens.csv`
| Métrica OEE                  | Como calcular                                                          |
|------------------------------|------------------------------------------------------------------------|
| **Pneus produzidos / dia**   | Contar registros com `STATUS ∈ {Em Produção, Expedido}` agrupados pela **data** de `DATA_ENTRADA`. |
| **Pneus expedidos / dia**    | Contar registros agrupados pela **data** de `DATA_SAIDA`.              |
| **Produção por cliente/pedido** | Agrupar por `CLIENTE` ou `IDPEDIDOPNEU`.                            |
| **Em estoque/pátio**         | `STATUS = Aguardando` com `LOCAL_PALLET` preenchido.                   |

**Exemplo — produzidos por dia:**
```python
prod = df[df['STATUS'].isin(['Em Produção', 'Expedido'])].copy()
prod['dia'] = pd.to_datetime(prod['DATA_ENTRADA'], format='%d/%m/%Y %H:%M:%S',
                             errors='coerce').dt.date
produzidos_por_dia = prod.dropna(subset=['dia']).groupby('dia').size()
```

### ❌ NÃO existe no sistema (precisa ser inserido no sistema de OEE)
Estes campos do OEE **não são rastreados** pelo ERP e teriam que ser lançados manualmente
(ou capturados por outra fonte) no seu sistema de OEE:
- **Defeitos / refugo** por dia (o ERP só tem aprovados implícitos = produzidos).
- **Colaboradores** presentes/ausentes.
- **Paradas** planejadas e não planejadas (horas).
- **Tempo disponível / operacional** (horas, turno).

### Fórmulas de OEE (referência, conforme a planilha atual)
```
Disponibilidade (A) = Tempo Operacional / Tempo Disponível
Desempenho      (P) = Pneus Produzidos / Meta Diária
Qualidade       (Q) = Pneus Aprovados / Pneus Produzidos
OEE                 = A × P × Q
```

---

## 5. Resumo da fronteira ERP × OEE
- O **ERP** entrega de forma confiável: **quantidade produzida e expedida por dia**,
  por cliente e por pedido (a partir do `STATUS` + datas).
- O **sistema de OEE** deve cuidar de: defeitos, mão de obra, paradas e tempos —
  combinando-os com os produzidos vindos do ERP para calcular A, P, Q e OEE.
