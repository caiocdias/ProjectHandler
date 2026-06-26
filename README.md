# ProjectHandler

Aplicativo Python para carregar PDFs de projetos de rede de distribuição, extrair texto e instanciar entidades encontradas a partir do vocabulário importado da planilha de exemplos.

## Como executar

No Windows:

```powershell
setup.bat
ProjectHandler.bat
```

No Linux:

```sh
sh setup.sh
sh ProjectHandler.sh
```

Também é possível executar manualmente:

```powershell
python -m pip install -r requirements.txt
python run.py
```

Ou instalar em modo editável:

```powershell
python -m pip install -e .
projecthandler
```

## Funcionalidades atuais

- Janela desktop com header, footer, menu lateral de projetos carregados e área de detalhes.
- Botão para carregar um ou mais PDFs para a memória.
- Botão para abrir o PDF original do projeto selecionado.
- Visualização das entidades em cards, com tipo, instância, quantidade, página, atributos e contexto extraído.
- Extração de metadados do quadro do projeto, como NS, cidade, cliente, serviço, circuito, data e responsáveis quando esses campos aparecem no texto extraído.
- Instanciação inicial de entidades:
  - Postes
  - Estruturas MT
  - Estruturas BT
  - Cabos
  - Estruturas inferidas que aparecem no PDF, mas ainda não estão no vocabulário da planilha

## Vocabulário

O arquivo `src/projecthandler/data/entity_definitions.json` foi gerado a partir da planilha `ARQUIVOS PARA PROJETO.xlsx`. Para regerar:

```powershell
python scripts/import_entities_from_excel.py "C:\Users\Caio Cezar Dias\Downloads\ARQUIVOS PARA PROJETO.xlsx"
```

## Testes

```powershell
python -m unittest
```

## Observações técnicas

Esta primeira versão usa regras determinísticas e o texto extraído do PDF. Em PDFs de projeto, parte do conteúdo pode vir concatenado ou com pouca separação entre símbolos; por isso o parser normaliza acentos, espaços e parênteses em alguns tipos de entidade. A arquitetura separa UI e parser para permitir evoluir depois para OCR, leitura vetorial ou regras específicas de norma CEMIG.

